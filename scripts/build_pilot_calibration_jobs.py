#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_benchmark_jobs import REFERENCE_LIMIT, execution_prompt
from common import ROOT, load_json, run_upstream_renderer, sha256_file, sha256_text, validate_episode


IDENTITY_MANIFEST = ROOT / "benchmarks" / "reference-assets" / "identity-refinement" / "manifest.json"
STYLE_REFERENCE = "vendor/hand-drawn-styles/examples/14-nordic-storybook.png"


PAGE_REFERENCE_PATHS = {
    1: ["benchmarks/reference-assets/identity-refinement/achi-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png"],
    2: ["benchmarks/reference-assets/identity-refinement/achi-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/achi-phone.png"],
    3: ["benchmarks/reference-assets/identity-refinement/pair-achi-zhoushu-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/achi-phone.png", "benchmarks/reference-assets/identity-refinement/zhoushu-thermos.png"],
    4: ["benchmarks/reference-assets/identity-refinement/cast-trio-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/zhoushu-thermos.png"],
    5: ["benchmarks/reference-assets/identity-refinement/cast-trio-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/achi-phone.png", "benchmarks/reference-assets/identity-refinement/zhoushu-thermos.png"],
    6: ["benchmarks/reference-assets/identity-refinement/cast-trio-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/achi-phone.png", "benchmarks/reference-assets/identity-refinement/zhoushu-thermos.png"],
    7: ["benchmarks/reference-assets/identity-refinement/cast-trio-core.png", "benchmarks/reference-assets/identity-refinement/achi-bag.png", "benchmarks/reference-assets/identity-refinement/achi-phone.png", "benchmarks/reference-assets/identity-refinement/zhoushu-thermos.png"],
}


def _stage_for_page(page_number: int) -> dict[str, float]:
    if page_number == 7:
        return {"x": 0.04, "y": 0.28, "width": 0.92, "height": 0.44}
    return {"x": 0.04, "y": 0.34, "width": 0.92, "height": 0.62}


def _asset_map() -> dict[str, dict[str, Any]]:
    manifest = load_json(IDENTITY_MANIFEST)
    if manifest.get("role") != "identity-only":
        raise ValueError("pilot calibration requires an identity-only manifest")
    result: dict[str, dict[str, Any]] = {}
    for asset in manifest["assets"]:
        relative = asset["path"]
        path = ROOT / relative
        if not path.is_file() or sha256_file(path) != asset["sha256"]:
            raise ValueError(f"identity reference missing or drifted: {relative}")
        if asset.get("qa_status") != "accepted":
            raise ValueError(f"identity reference is not accepted: {relative}")
        result[relative] = asset
    return result


def _overlap(first: dict[str, float], second: dict[str, float]) -> bool:
    return not (
        first["x"] + first["width"] <= second["x"]
        or second["x"] + second["width"] <= first["x"]
        or first["y"] + first["height"] <= second["y"]
        or second["y"] + second["height"] <= first["y"]
    )


def build_jobs(episode: dict[str, Any]) -> list[dict[str, Any]]:
    errors = validate_episode(episode, episode.get("episode_id", "episode"))
    if errors:
        raise ValueError("episode preflight failed:\n" + "\n".join(errors))
    if episode.get("episode_id") != "EP-003":
        raise ValueError("the current calibration packet is deliberately scoped to EP-003")
    assets = _asset_map()
    styles = load_json(ROOT / "benchmarks" / "styles.yaml")
    style_candidate = next(item for item in styles["candidates"] if item["style_id"] == "14")
    style_path = ROOT / STYLE_REFERENCE
    style_reference = {
        "path": STYLE_REFERENCE,
        "role": "style-only",
        "instruction": "Use only the upstream style-14 visual language; never copy its people, pose, clothing or story.",
        "exists": True,
        "sha256": sha256_file(style_path),
    }
    jobs: list[dict[str, Any]] = []
    for page in episode["pages"]:
        page_number = page["number"]
        image = page["image"]
        stage = _stage_for_page(page_number)
        if any(_overlap(stage, region) for region in image["reserved_text_regions"]):
            raise ValueError(f"page {page_number}: illustration stage overlaps copy region")
        renderer_vars = dict(style_candidate.get("renderer_vars", {}))
        renderer_vars["构图"] = image["composition_en"]
        prompt = run_upstream_renderer(
            "14",
            image["subject_en"],
            "3:4",
            renderer_vars,
        )
        for copy_line in page["copy"]:
            if copy_line["text"] in prompt:
                raise ValueError(f"page {page_number}: final Chinese copy leaked into art prompt")
        character_references: list[dict[str, Any]] = []
        for relative in PAGE_REFERENCE_PATHS[page_number]:
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
        if 1 + len(character_references) > REFERENCE_LIMIT:
            raise ValueError(f"page {page_number}: reference count exceeds {REFERENCE_LIMIT}")
        x2 = stage["x"] + stage["width"]
        y2 = stage["y"] + stage["height"]
        request = {
            "prompt": prompt,
            "style_references": [style_reference],
            "character_references": character_references,
            "negative_constraints": [
                f"Exactly {len(image['characters'])} visible people: {', '.join(image['characters'])}; no absent friend, waiter, extra diner, duplicate, portrait or background silhouette.",
                f"Required visible objects and only these scene objects: {', '.join(image['necessary_props'])}.",
                f"Dominant visible action: {image['visual_action']}",
                "One dominant natural action only; no symbolic prop choreography, reaching across another person's place setting or staged simultaneous gestures.",
                "No extra limb, fused limb, detached hand, hidden hand holding an object, impossible grip or cropped body part.",
                "Preserve each supplied identity, fixed clothing, relative scale and only the conditional props included in this request.",
                "Never swap prop ownership: the worn coral-orange shoulder bag and dark-navy phone belong only to Achi; the short blue-sleeved thermos belongs only to Zhoushu.",
                "Do not add tableware, signs, decorations or furniture beyond the necessary scene objects.",
                "Phone screens and paper sleeves contain no readable or pseudo-readable marks.",
                "Do not draw speech balloons, captions, empty balloons or lettering containers.",
                f"Every person, prop, table, chair, bowl, hand and floor mark stays inside x={stage['x']:.2f}..{x2:.2f}, y={stage['y']:.2f}..{y2:.2f}; the boundary itself is invisible.",
            ],
            "reserved_text_regions": image["reserved_text_regions"],
            "aspect_ratio": "3:4",
        }
        full_prompt = execution_prompt(request)
        ordered = request["style_references"] + character_references
        job_id = f"CAL-{episode['episode_id']}-P{page_number:02d}"
        jobs.append(
            {
                "schema_version": "1.0.0",
                "job_id": job_id,
                "episode_id": episode["episode_id"],
                "page": page_number,
                "status": "calibration_only_pending",
                "calibration_only": True,
                "production_style_locked": False,
                "style_id": "14",
                "prompt": full_prompt,
                "prompt_sha256": sha256_text(full_prompt),
                "upstream_prompt_sha256": sha256_text(prompt),
                "style_references": [style_reference],
                "character_references": character_references,
                "ordered_references": [
                    {**reference, "index": index, "absolute_path": str((ROOT / reference["path"]).resolve())}
                    for index, reference in enumerate(ordered, 1)
                ],
                "reference_count": len(ordered),
                "aspect_ratio": "3:4",
                "reserved_text_regions": image["reserved_text_regions"],
                "subject_stage_region": stage,
                "necessary_props": image["necessary_props"],
                "output_path": f"build/pilots/{episode['episode_id']}/art-raw/page-{page_number:02d}.png",
                "composed_output_path": f"build/pilots/{episode['episode_id']}/art/page-{page_number:02d}.png",
            }
        )
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a style-14 calibration packet for one seven-page pilot.")
    parser.add_argument("--episode", type=Path, default=ROOT / "episodes" / "EP-003.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "pilots" / "EP-003" / "jobs.jsonl")
    args = parser.parse_args()
    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    out = args.out if args.out.is_absolute() else ROOT / args.out
    jobs = build_jobs(load_json(episode_path))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Wrote {len(jobs)} calibration jobs to {out}")
    print(f"Maximum references used: {max(job['reference_count'] for job in jobs)}/{REFERENCE_LIMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
