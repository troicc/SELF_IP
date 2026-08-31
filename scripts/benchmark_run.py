#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import struct
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from build_benchmark_jobs import build_jobs
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
COMPLETED_STATUSES = {"completed_pending_blind_review", "completed"}
ALLOWED_STATUSES = {"qa_pending", *COMPLETED_STATUSES}
HISTORICAL_CONTRACT_PATTERN = re.compile(r"benchmarks/contracts/[A-Za-z0-9._-]+\.json")


def png_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


@lru_cache(maxsize=12)
def _jobs_for_scene(scene_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(sorted(
        (job for job in build_jobs() if job["scene_id"] == scene_id),
        key=lambda job: (int(job["style_id"]), job["attempt"]),
    ))


def _historical_prompt_hashes(run: dict[str, Any], scene_id: str, errors: list[str]) -> dict[str, str] | None:
    relative = run.get("source_prompt_contract")
    if relative is None:
        return None
    if not isinstance(relative, str) or not HISTORICAL_CONTRACT_PATTERN.fullmatch(relative):
        errors.append("source_prompt_contract must be a JSON file under benchmarks/contracts")
        return {}
    contract_path = ROOT / relative
    if not contract_path.is_file():
        errors.append(f"source prompt contract is missing: {relative}")
        return {}
    contract = load_json(contract_path)
    if contract.get("scene_id") != scene_id:
        errors.append("source prompt contract scene_id differs from run")
    if contract.get("status") != "superseded":
        errors.append("historical source prompt contract must be explicitly superseded")
    if not str(contract.get("superseded_reason", "")).strip():
        errors.append("historical source prompt contract needs a superseded_reason")
    hashes = contract.get("job_prompt_sha256_by_style")
    if not isinstance(hashes, dict) or set(hashes) != {"10", "14", "18"}:
        errors.append("historical source prompt contract needs hashes for styles 10, 14 and 18")
        return {}
    for style, value in hashes.items():
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            errors.append(f"historical source prompt contract has invalid style-{style} hash")
    return hashes


def build_run(scene_id: str) -> dict[str, Any]:
    jobs = _jobs_for_scene(scene_id)
    if not jobs:
        raise ValueError(f"unknown benchmark scene: {scene_id}")
    attempts: list[dict[str, Any]] = []
    generated = Counter()
    for job in jobs:
        output_path = ROOT / job["output_path"]
        dimensions = png_dimensions(output_path) if output_path.is_file() else None
        if output_path.is_file():
            generated[job["style_id"]] += 1
        attempts.append(
            {
                "job_id": job["job_id"],
                "style_id": job["style_id"],
                "attempt": job["attempt"],
                "prompt_sha256": job["prompt_sha256"],
                "output_path": job["output_path"],
                "output_sha256": sha256_file(output_path) if output_path.is_file() else None,
                "width": dimensions[0] if dimensions else None,
                "height": dimensions[1] if dimensions else None,
                "checks": {field: None for field in CHECK_FIELDS},
                "successful": None,
                "notes": [],
            }
        )
    return {
        "schema_version": "1.0.0",
        "scene_id": scene_id,
        "status": "qa_pending",
        "generated_at": "",
        "reviewed_at": "",
        "reviewed_by": "",
        "source_job_manifest": "build/benchmarks/jobs.jsonl",
        "attempts": attempts,
        "unit_counts": {
            style: {"attempt_count": generated[style], "successful_count": None}
            for style in ("10", "14", "18")
        },
        "blind_review": {
            "status": "pending",
            "scores_recorded_in": "benchmarks/scorecard.csv",
        },
        "operator_notes": [],
    }


def validate_run(run: dict[str, Any], verify_files: bool = False) -> list[str]:
    errors: list[str] = []
    scene_id = str(run.get("scene_id", ""))
    if not re.fullmatch(r"B(?:0[1-9]|1[0-2])", scene_id):
        return [f"invalid scene_id: {scene_id!r}"]
    status = run.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append(f"unsupported status: {status!r}")
    completed = status in COMPLETED_STATUSES
    if completed:
        for field in ("generated_at", "reviewed_at", "reviewed_by"):
            if not str(run.get(field, "")).strip():
                errors.append(f"completed run requires {field}")

    expected_jobs = {job["job_id"]: job for job in _jobs_for_scene(scene_id)}
    historical_prompt_hashes = _historical_prompt_hashes(run, scene_id, errors)
    attempts = run.get("attempts", [])
    if not isinstance(attempts, list):
        return errors + ["attempts must be an array"]
    ids = [attempt.get("job_id") for attempt in attempts if isinstance(attempt, dict)]
    if len(ids) != len(set(ids)):
        errors.append("attempt job_ids must be unique")
    if set(ids) != set(expected_jobs):
        errors.append(f"attempts must cover exactly the nine jobs for {scene_id}")

    observed_counts: dict[str, dict[str, int]] = {
        style: {"attempt_count": 0, "successful_count": 0}
        for style in ("10", "14", "18")
    }
    for attempt in attempts:
        if not isinstance(attempt, dict):
            errors.append("each attempt must be an object")
            continue
        job_id = attempt.get("job_id")
        job = expected_jobs.get(job_id)
        if not job:
            continue
        label = str(job_id)
        if str(attempt.get("style_id")) != str(job["style_id"]):
            errors.append(f"{label}: style_id differs from job")
        if attempt.get("attempt") != job["attempt"]:
            errors.append(f"{label}: attempt number differs from job")
        expected_prompt_hash = job["prompt_sha256"]
        prompt_contract_label = "current job contract"
        if historical_prompt_hashes is not None:
            expected_prompt_hash = historical_prompt_hashes.get(str(job["style_id"]))
            prompt_contract_label = "declared historical job contract"
        if attempt.get("prompt_sha256") != expected_prompt_hash:
            errors.append(f"{label}: prompt hash differs from {prompt_contract_label}")
        if attempt.get("output_path") != job["output_path"]:
            errors.append(f"{label}: output path differs from job")

        output_hash = attempt.get("output_sha256")
        width = attempt.get("width")
        height = attempt.get("height")
        has_output_metadata = bool(
            isinstance(output_hash, str)
            and re.fullmatch(r"[0-9a-f]{64}", output_hash)
            and isinstance(width, int)
            and isinstance(height, int)
            and width > 0
            and height > 0
        )
        if completed and not has_output_metadata:
            errors.append(f"{label}: completed attempt needs PNG hash and dimensions")
        if has_output_metadata and width * 4 != height * 3:
            errors.append(f"{label}: dimensions are not exactly 3:4")
        if has_output_metadata:
            observed_counts[str(job["style_id"])]["attempt_count"] += 1

        checks = attempt.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(CHECK_FIELDS):
            errors.append(f"{label}: objective check fields are incomplete or unexpected")
            continue
        check_values = [checks[field] for field in CHECK_FIELDS]
        if completed and not all(isinstance(value, bool) for value in check_values):
            errors.append(f"{label}: completed run requires explicit booleans for every check")
            continue
        derived_success = all(value is True for value in check_values)
        successful = attempt.get("successful")
        if completed and successful is not derived_success:
            errors.append(f"{label}: successful must equal the conjunction of all objective checks")
        if successful is True:
            observed_counts[str(job["style_id"])]["successful_count"] += 1
        notes = attempt.get("notes")
        if not isinstance(notes, list) or not all(isinstance(note, str) and note.strip() for note in notes):
            errors.append(f"{label}: notes must be an array of nonempty strings")

        if verify_files:
            output_path = ROOT / job["output_path"]
            if not output_path.is_file():
                errors.append(f"{label}: output file is missing")
            else:
                actual_dimensions = png_dimensions(output_path)
                if actual_dimensions != (width, height):
                    errors.append(f"{label}: PNG dimensions differ from run record")
                if sha256_file(output_path) != output_hash:
                    errors.append(f"{label}: PNG hash differs from run record")

    unit_counts = run.get("unit_counts")
    if not isinstance(unit_counts, dict) or set(unit_counts) != {"10", "14", "18"}:
        errors.append("unit_counts must contain styles 10, 14 and 18")
    else:
        for style, observed in observed_counts.items():
            recorded = unit_counts.get(style)
            if not isinstance(recorded, dict):
                errors.append(f"unit_counts.{style} must be an object")
                continue
            if recorded.get("attempt_count") != observed["attempt_count"]:
                errors.append(f"unit_counts.{style}.attempt_count differs from attempt records")
            if completed and recorded.get("successful_count") != observed["successful_count"]:
                errors.append(f"unit_counts.{style}.successful_count differs from objective checks")
        if completed and any(values["attempt_count"] < 3 for values in observed_counts.values()):
            errors.append("completed run requires at least three generated attempts per style")

    blind_review = run.get("blind_review", {})
    if blind_review.get("status") not in {"pending", "completed"}:
        errors.append("blind_review.status must be pending or completed")
    if blind_review.get("scores_recorded_in") != "benchmarks/scorecard.csv":
        errors.append("blind review scores must be recorded in benchmarks/scorecard.csv")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize or validate objective benchmark attempt QA.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a QA worksheet from generated outputs.")
    init_parser.add_argument("--scene", required=True)
    init_parser.add_argument("--out", type=Path)

    validate_parser = subparsers.add_parser("validate", help="Validate one completed or pending run record.")
    validate_parser.add_argument("--run", type=Path, required=True)
    validate_parser.add_argument("--verify-files", action="store_true")

    args = parser.parse_args()
    if args.command == "init":
        out = args.out or ROOT / "benchmarks" / "runs" / f"{args.scene}.json"
        if not out.is_absolute():
            out = ROOT / out
        if out.exists():
            raise SystemExit(f"Refusing to overwrite existing run record: {out}")
        run = build_run(args.scene)
        dump_json(out, run)
        print(f"Wrote benchmark QA worksheet to {out}")
        return 0

    run_path = args.run if args.run.is_absolute() else ROOT / args.run
    run = load_json(run_path)
    errors = validate_run(run, verify_files=args.verify_files)
    if errors:
        print(f"BENCHMARK RUN VALIDATION FAILED ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("BENCHMARK RUN VALIDATION PASSED")
    print(f"  scene: {run['scene_id']}")
    for style in ("10", "14", "18"):
        counts = run["unit_counts"][style]
        successful = counts["successful_count"]
        successful_label = "pending" if successful is None else str(successful)
        print(f"  style {style}: {successful_label}/{counts['attempt_count']} successful")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
