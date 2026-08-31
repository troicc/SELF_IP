#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import ROOT, load_json, run_upstream_renderer, sha256_file, sha256_text, validate_episode


def _verify_ref(item: dict[str, Any], expected_role: str) -> dict[str, Any]:
    if item.get("role") != expected_role:
        raise ValueError(f"reference role must be {expected_role}")
    path = ROOT / item["path"]
    if not path.is_file():
        raise ValueError(f"locked reference is missing: {item['path']}")
    actual = sha256_file(path)
    if actual != item.get("sha256"):
        raise ValueError(f"locked reference hash mismatch: {item['path']}")
    return {**item, "exists": True}


def build_requests(episode: dict[str, Any]) -> list[dict[str, Any]]:
    errors = validate_episode(episode, episode.get("episode_id", "episode"))
    if errors:
        raise ValueError("episode preflight failed:\n" + "\n".join(errors))
    lock_path = ROOT / "config" / "style-lock.json"
    if not lock_path.is_file():
        raise ValueError("dialogue-sketch-v1 is not locked; finish and score all benchmarks first")
    lock = load_json(lock_path)
    if lock.get("status") != "locked" or lock.get("production_name") != "dialogue-sketch-v1":
        raise ValueError("invalid production style lock")
    style_id = str(lock["upstream_style_id"])
    if style_id not in {"10", "14", "18"}:
        raise ValueError("locked style is not an approved candidate")

    styles = load_json(ROOT / "benchmarks" / "styles.yaml")
    candidate = next(item for item in styles["candidates"] if str(item["style_id"]) == style_id)
    style_ref = _verify_ref(lock["style_reference"], "style-only")
    individual_refs = {
        key: _verify_ref(value, "identity-only") for key, value in lock["character_references"].items()
    }
    pair_refs = {key: _verify_ref(value, "identity-only") for key, value in lock["pair_references"].items()}
    if style_ref["path"] in {item["path"] for item in individual_refs.values()} | {
        item["path"] for item in pair_refs.values()
    }:
        raise ValueError("style and character references may not share a path")

    requests: list[dict[str, Any]] = []
    for page in episode["pages"]:
        image = page["image"]
        variables = dict(candidate.get("renderer_vars", {}))
        if candidate["prompt_language"] == "en":
            if not image.get("subject_en") or not image.get("composition_en"):
                raise ValueError(
                    f"page {page['number']}: locked style {style_id} requires editor-approved subject_en and composition_en"
                )
            subject = image["subject_en"]
            composition = image["composition_en"]
        else:
            subject = image["subject"]
            composition = image["composition"]
        if style_id in {"14", "18"}:
            variables["构图"] = composition
            renderer_subject = subject
        else:
            renderer_subject = f"{subject}；构图安排：{composition}"
        prompt = run_upstream_renderer(style_id, renderer_subject, "3:4", variables)
        for line in page["copy"]:
            if line["text"] in prompt:
                raise ValueError(f"page {page['number']}: body copy leaked into image prompt")

        cast_refs = [individual_refs[character] for character in image["characters"]]
        character_set = set(image["characters"])
        if {"achi", "zhoushu"} <= character_set:
            cast_refs.append(pair_refs["achi_zhoushu"])
        if {"achi", "qinyi"} <= character_set:
            cast_refs.append(pair_refs["achi_qinyi"])
        negative = [
            f"Exactly {len(image['characters'])} people: {', '.join(image['characters'])}; no extra person or duplicate.",
            "No extra limb, fused limb, detached hand or impossible object grip.",
            "Preserve immutable face, relative height, fixed clothing and listed fixed props from identity-only references.",
            "No text, pseudo-text, letters, numbers, logo, sign, speech bubble, watermark or tool label anywhere.",
            "Do not copy people, clothing, pose or story content from the style-only anchor.",
            "Keep all reserved text regions free of faces, hands, key props and high-contrast marks.",
        ]
        requests.append(
            {
                "request_id": f"{episode['episode_id']}-P{page['number']:02d}",
                "production_style": "dialogue-sketch-v1",
                "style_id": style_id,
                "subject": subject,
                "composition": composition,
                "prompt": prompt,
                "prompt_sha256": sha256_text(prompt),
                "style_references": [style_ref],
                "character_references": cast_refs,
                "negative_constraints": negative,
                "aspect_ratio": "3:4",
                "reserved_text_regions": image["reserved_text_regions"],
                "necessary_props": image["necessary_props"],
                "user_visible_copy_in_prompt": False,
            }
        )
    return requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Build production image requests from the frozen style lock.")
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    episode = load_json(episode_path)
    requests = build_requests(episode)
    out = args.out or ROOT / "build" / "requests" / f"{episode['episode_id']}.jsonl"
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for item in requests:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    print(f"Wrote {len(requests)} locked production requests to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
