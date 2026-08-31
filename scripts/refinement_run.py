#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from typing import Any

from build_style14_refinement_jobs import build_refinement_jobs
from common import ROOT, dump_json, load_json, sha256_file


CHECK_FIELDS = (
    "correct_character_count",
    "usable_anatomy",
    "fixed_identity_and_clothing",
    "required_props_complete",
    "no_text_or_pseudotext",
    "header_safe_region_clear",
    "dialogue_safe_region_clear",
    "no_duplicate_or_extra_elements",
    "scene_specific_constraints_met",
)
DECISIONS_PATH = ROOT / "benchmarks" / "refinement-qa" / "style14-v2-decisions.json"
DEFAULT_OUT = ROOT / "benchmarks" / "refinement-runs" / "style14-v2.json"


def png_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def _file_record(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise ValueError(f"missing refinement output: {relative}")
    dimensions = png_dimensions(path)
    if dimensions is None:
        raise ValueError(f"not a valid PNG: {relative}")
    return {
        "path": relative,
        "sha256": sha256_file(path),
        "width": dimensions[0],
        "height": dimensions[1],
    }


def _decision_map(decisions: dict[str, Any], job_ids: set[str]) -> dict[str, dict[str, Any]]:
    passed = decisions.get("passed_job_ids", [])
    failed = decisions.get("failed_jobs", {})
    if not isinstance(passed, list) or not isinstance(failed, dict):
        raise ValueError("decision file needs passed_job_ids and failed_jobs")
    if len(passed) != len(set(passed)):
        raise ValueError("passed_job_ids contains duplicates")
    overlap = set(passed) & set(failed)
    if overlap:
        raise ValueError(f"jobs cannot be both passed and failed: {sorted(overlap)}")
    observed = set(passed) | set(failed)
    if observed != job_ids:
        missing = sorted(job_ids - observed)
        extra = sorted(observed - job_ids)
        raise ValueError(f"decisions must cover all jobs; missing={missing}, extra={extra}")

    mapped: dict[str, dict[str, Any]] = {}
    for job_id in passed:
        mapped[job_id] = {"false_checks": [], "notes": []}
    for job_id, result in failed.items():
        false_checks = result.get("false_checks", [])
        notes = result.get("notes", [])
        if not false_checks or any(field not in CHECK_FIELDS for field in false_checks):
            raise ValueError(f"{job_id}: failed job needs known false_checks")
        if not notes or not all(isinstance(note, str) and note.strip() for note in notes):
            raise ValueError(f"{job_id}: failed job needs nonempty notes")
        mapped[job_id] = {"false_checks": false_checks, "notes": notes}
    return mapped


def build_run() -> dict[str, Any]:
    decisions = load_json(DECISIONS_PATH)
    jobs = build_refinement_jobs()
    job_ids = {job["job_id"] for job in jobs}
    decision_map = _decision_map(decisions, job_ids)
    attempts: list[dict[str, Any]] = []
    for job in jobs:
        decision = decision_map[job["job_id"]]
        checks = {field: field not in decision["false_checks"] for field in CHECK_FIELDS}
        attempts.append(
            {
                "job_id": job["job_id"],
                "scene_id": job["scene_id"],
                "style_id": job["style_id"],
                "attempt": job["attempt"],
                "prompt_sha256": job["prompt_sha256"],
                "raw_output": _file_record(job["output_path"]),
                "composed_output": _file_record(job["composed_output_path"]),
                "checks": checks,
                "successful": all(checks.values()),
                "notes": decision["notes"],
            }
        )
    successful_count = sum(item["successful"] for item in attempts)
    attempt_count = len(attempts)
    rate = successful_count / attempt_count
    return {
        "schema_version": "1.0.0",
        "round_id": "style14-v2",
        "status": "completed_objective_qa_pending_blind_review",
        "calibration_only": True,
        "production_style_locked": False,
        "reviewed_at": decisions["reviewed_at"],
        "reviewed_by": decisions["reviewed_by"],
        "review_scope": decisions["review_scope"],
        "source_job_manifest": "build/benchmarks/style14-refinement-jobs.jsonl",
        "source_decisions": "benchmarks/refinement-qa/style14-v2-decisions.json",
        "attempts": attempts,
        "objective_result": {
            "attempt_count": attempt_count,
            "successful_count": successful_count,
            "generation_success_rate": round(rate, 6),
            "hard_gate_minimum": 0.72,
            "hard_gate_passed": rate >= 0.72,
        },
        "blind_review": {
            "status": "pending_two_independent_reviewers",
            "axes": [
                "character_consistency",
                "emotion_expression",
                "negative_space",
                "interaction_naturalness",
                "generation_success",
                "distinctiveness",
            ],
        },
    }


def validate_run(run: dict[str, Any], verify_files: bool) -> list[str]:
    errors: list[str] = []
    jobs = {job["job_id"]: job for job in build_refinement_jobs()}
    attempts = run.get("attempts", [])
    if not isinstance(attempts, list) or {item.get("job_id") for item in attempts} != set(jobs):
        return ["attempts must cover exactly the 36 current refinement jobs"]
    successful_count = 0
    for item in attempts:
        job_id = item["job_id"]
        job = jobs[job_id]
        if item.get("prompt_sha256") != job["prompt_sha256"]:
            errors.append(f"{job_id}: prompt hash drift")
        checks = item.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(CHECK_FIELDS):
            errors.append(f"{job_id}: invalid objective checks")
            continue
        if not all(isinstance(checks[field], bool) for field in CHECK_FIELDS):
            errors.append(f"{job_id}: every check must be boolean")
            continue
        derived = all(checks.values())
        if item.get("successful") is not derived:
            errors.append(f"{job_id}: successful does not match checks")
        successful_count += int(derived)
        for key, expected_path in (
            ("raw_output", job["output_path"]),
            ("composed_output", job["composed_output_path"]),
        ):
            record = item.get(key, {})
            if record.get("path") != expected_path:
                errors.append(f"{job_id}: {key} path drift")
                continue
            if not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
                errors.append(f"{job_id}: {key} hash missing")
            if key == "composed_output" and record.get("width", 0) * 4 != record.get("height", 0) * 3:
                errors.append(f"{job_id}: composed output is not 3:4")
            if verify_files:
                path = ROOT / expected_path
                if not path.is_file():
                    errors.append(f"{job_id}: {key} file missing")
                elif sha256_file(path) != record.get("sha256"):
                    errors.append(f"{job_id}: {key} file hash drift")
                elif png_dimensions(path) != (record.get("width"), record.get("height")):
                    errors.append(f"{job_id}: {key} dimensions drift")
    result = run.get("objective_result", {})
    if result.get("attempt_count") != 36 or result.get("successful_count") != successful_count:
        errors.append("objective_result counts do not match attempts")
    expected_rate = round(successful_count / 36, 6)
    if result.get("generation_success_rate") != expected_rate:
        errors.append("objective_result rate does not match attempts")
    if result.get("hard_gate_passed") is not (expected_rate >= 0.72):
        errors.append("objective_result hard gate result is inconsistent")
    if run.get("production_style_locked") is not False:
        errors.append("refinement objective QA may not lock production style")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate style-14 refinement objective QA.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--run", type=Path, default=DEFAULT_OUT)
    validate_parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args()

    if args.command == "build":
        out = args.out if args.out.is_absolute() else ROOT / args.out
        run = build_run()
        dump_json(out, run)
        result = run["objective_result"]
        print(f"Wrote refinement QA run to {out}")
        print(f"Objective success: {result['successful_count']}/{result['attempt_count']} ({result['generation_success_rate']:.1%})")
        return 0

    run_path = args.run if args.run.is_absolute() else ROOT / args.run
    errors = validate_run(load_json(run_path), verify_files=args.verify_files)
    if errors:
        print(f"REFINEMENT RUN VALIDATION FAILED ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("REFINEMENT RUN VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
