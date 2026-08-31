#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_benchmark_jobs import REFERENCE_LIMIT, execution_prompt
from common import ROOT, compile_benchmark_requests, load_json, sha256_file, sha256_text


CONFIG_PATH = ROOT / "benchmarks" / "style14-refinement.yaml"


def _asset_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    manifest = load_json(ROOT / config["identity_manifest"])
    if manifest.get("role") != "identity-only":
        raise ValueError("refinement manifest must be identity-only")
    assets = {item["path"]: item for item in manifest["assets"]}
    for relative, asset in assets.items():
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"missing refinement reference: {relative}")
        if sha256_file(path) != asset.get("sha256"):
            raise ValueError(f"refinement reference hash drift: {relative}")
        if asset.get("qa_status") != "accepted":
            raise ValueError(f"refinement reference is not accepted: {relative}")
    return assets


def _overlap(first: dict[str, float], second: dict[str, float]) -> bool:
    return not (
        first["x"] + first["width"] <= second["x"]
        or second["x"] + second["width"] <= first["x"]
        or first["y"] + first["height"] <= second["y"]
        or second["y"] + second["height"] <= first["y"]
    )


def build_refinement_jobs() -> list[dict[str, Any]]:
    config = load_json(CONFIG_PATH)
    if config.get("base_style_id") != "14" or config.get("lock_status") != "benchmarking":
        raise ValueError("style-14 refinement must remain a non-production benchmarking round")
    if config.get("style_recipe", {}).get("overrides_allowed") is not False:
        raise ValueError("refinement may not override the upstream style recipe")
    assets = _asset_map(config)
    base_requests = {
        request["scene_id"]: request
        for request in compile_benchmark_requests()
        if request["style_id"] == "14"
    }
    expected_scenes = {f"B{number:02d}" for number in range(1, 13)}
    if set(base_requests) != expected_scenes:
        raise ValueError("base style-14 requests do not cover all 12 scenes")

    jobs: list[dict[str, Any]] = []
    for scene_id in sorted(expected_scenes):
        base = base_requests[scene_id]
        reference_set_name = config["scene_reference_sets"][scene_id]
        identity_paths = config["reference_sets"][reference_set_name]
        stage = config["stage_regions"][config["scene_stage_sides"][scene_id]]
        if any(_overlap(stage, reserved) for reserved in base["reserved_text_regions"]):
            raise ValueError(f"{scene_id}: subject stage overlaps a reserved text region")
        character_references = []
        for relative in identity_paths:
            asset = assets[relative]
            character_references.append(
                {
                    "path": relative,
                    "role": "identity-only",
                    "reference_kind": asset["reference_kind"],
                    "character_ids": asset["characters"],
                    "exists": True,
                    "sha256": asset["sha256"],
                }
            )
        if len(base["style_references"] + character_references) > REFERENCE_LIMIT:
            raise ValueError(f"{scene_id}: refinement reference set exceeds adapter limit")

        x2 = stage["x"] + stage["width"]
        y2 = stage["y"] + stage["height"]
        stage_label = (
            f"x={stage['x']:.2f}..{x2:.2f}, y={stage['y']:.2f}..{y2:.2f}"
        )
        request = {
            **base,
            "character_references": character_references,
            "negative_constraints": [
                *base["negative_constraints"],
                (
                    "Invisible subject-stage constraint: every visible pixel belonging to people, hair, faces, "
                    f"hands, required props, furniture, floor marks or action marks must stay inside {stage_label}."
                ),
                "Do not draw the subject-stage boundary; everything outside it must remain quiet blank paper.",
                (
                    "Use only the expression named by the scene for each character. Do not copy the same smile, "
                    "eyebrow angle or gaze across characters, and do not add a smile to a neutral character."
                ),
                "Conditional prop references apply only when included in this job; do not invent omitted phones, keys, scissors, cups or bags.",
            ],
        }
        prompt = execution_prompt(request)
        for attempt in range(1, int(config["attempts_per_scene"]) + 1):
            ordered = request["style_references"] + character_references
            ordered_references = [
                {**reference, "index": index, "absolute_path": str((ROOT / reference["path"]).resolve())}
                for index, reference in enumerate(ordered, 1)
            ]
            output_path = f"{config['output_root']}/{scene_id}/attempt-{attempt:02d}.png"
            composed_output_path = f"{config['composed_output_root']}/{scene_id}/attempt-{attempt:02d}.png"
            jobs.append(
                {
                    "schema_version": "1.0.0",
                    "round_id": config["round_id"],
                    "status": "pending",
                    "calibration_only": True,
                    "production_style_locked": False,
                    "job_id": f"R14-{scene_id}-A{attempt:02d}",
                    "scene_id": scene_id,
                    "style_id": "14",
                    "attempt": attempt,
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                    "upstream_prompt_sha256": base["prompt_sha256"],
                    "style_references": request["style_references"],
                    "character_references": character_references,
                    "ordered_references": ordered_references,
                    "reference_count": len(ordered_references),
                    "aspect_ratio": base["aspect_ratio"],
                    "reserved_text_regions": base["reserved_text_regions"],
                    "subject_stage_region": stage,
                    "output_path": output_path,
                    "composed_output_path": composed_output_path,
                }
            )
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the style-14 identity/composition refinement round.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build" / "benchmarks" / "style14-refinement-jobs.jsonl",
    )
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    jobs = build_refinement_jobs()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Wrote {len(jobs)} style-14 refinement jobs to {out}")
    print(f"Maximum references used: {max(job['reference_count'] for job in jobs)}/{REFERENCE_LIMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
