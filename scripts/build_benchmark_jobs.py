#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import ROOT, compile_benchmark_requests, sha256_text


REFERENCE_LIMIT = 5


def _role_line(reference: dict[str, Any], index: int) -> str:
    if reference["role"] == "style-only":
        return (
            f"Image {index}: STYLE-ONLY reference. Use only its visual language. "
            "Never copy its people, identity, clothes, pose, composition or story."
        )
    characters = "+".join(reference.get("character_ids", []))
    kind = reference.get("reference_kind", "identity-reference")
    return (
        f"Image {index}: IDENTITY-ONLY {kind} for {characters}. Preserve identity facts, fixed clothes/props "
        "and relative scale. Never copy its linework, coloring, lighting, texture or finish."
    )


def execution_prompt(request: dict[str, Any]) -> str:
    ordered = request["style_references"] + request["character_references"]
    role_lines = "\n".join(_role_line(reference, index) for index, reference in enumerate(ordered, 1))
    constraints = "\n".join(f"- {item}" for item in request["negative_constraints"])
    regions = json.dumps(request["reserved_text_regions"], ensure_ascii=False, separators=(",", ":"))
    return (
        "REFERENCE ROLE CONTRACT — mandatory and separate:\n"
        f"{role_lines}\n"
        "The style-only and identity-only roles may not substitute for each other. Render every character "
        "completely in the style-only visual language while preserving identity facts from identity-only references.\n\n"
        "Use the following upstream-rendered style prompt verbatim as the only style recipe:\n"
        "--- BEGIN UPSTREAM PROMPT ---\n"
        f"{request['prompt']}\n"
        "--- END UPSTREAM PROMPT ---\n\n"
        "Scene-level hard constraints:\n"
        f"{constraints}\n"
        "- No text, letters, numbers, pseudo-writing, signature, logo, watermark or model mark anywhere.\n"
        f"- Keep these reserved text regions visually quiet and empty: {regions}.\n"
        f"- Output aspect ratio: {request['aspect_ratio']}."
    )


def build_jobs(requests: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    requests = requests if requests is not None else compile_benchmark_requests()
    jobs: list[dict[str, Any]] = []
    for request in requests:
        if not request["ready_for_generation"]:
            raise ValueError(f"{request['request_id']}: request is missing a reference asset")
        ordered_source = request["style_references"] + request["character_references"]
        if len(ordered_source) > REFERENCE_LIMIT:
            raise ValueError(
                f"{request['request_id']}: {len(ordered_source)} references exceed adapter limit {REFERENCE_LIMIT}"
            )
        style_paths = {item["path"] for item in request["style_references"]}
        identity_paths = {item["path"] for item in request["character_references"]}
        if style_paths & identity_paths:
            raise ValueError(f"{request['request_id']}: style and identity references overlap")

        ordered_references = []
        for index, reference in enumerate(ordered_source, 1):
            ordered_references.append(
                {
                    **reference,
                    "index": index,
                    "absolute_path": str((ROOT / reference["path"]).resolve()),
                }
            )
        prompt = execution_prompt(request)
        for attempt in range(1, request["expected_attempts"] + 1):
            jobs.append(
                {
                    "schema_version": "1.0.0",
                    "adapter_contract": "separate-reference-roles-v1",
                    "job_id": f"{request['request_id']}-A{attempt:02d}",
                    "request_id": request["request_id"],
                    "scene_id": request["scene_id"],
                    "style_id": request["style_id"],
                    "attempt": attempt,
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                    "upstream_prompt_sha256": request["prompt_sha256"],
                    "style_references": request["style_references"],
                    "character_references": request["character_references"],
                    "ordered_references": ordered_references,
                    "reference_count": len(ordered_references),
                    "aspect_ratio": request["aspect_ratio"],
                    "reserved_text_regions": request["reserved_text_regions"],
                    "output_path": (
                        f"benchmarks/outputs/style-{request['style_id']}/{request['scene_id']}/"
                        f"attempt-{attempt:02d}.png"
                    ),
                    "status": "pending",
                }
            )
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand 36 benchmark requests into executable attempt jobs.")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "benchmarks" / "jobs.jsonl")
    args = parser.parse_args()

    jobs = build_jobs()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n")
    counts = Counter(job["style_id"] for job in jobs)
    print(f"Wrote {len(jobs)} benchmark jobs to {args.out}")
    print("Jobs by style: " + ", ".join(f"{style}={counts[style]}" for style in ("10", "14", "18")))
    print(f"Reference adapter limit: {REFERENCE_LIMIT}; maximum used: {max(job['reference_count'] for job in jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
