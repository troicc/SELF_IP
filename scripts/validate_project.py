#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from benchmark_run import validate_run
from build_pilot_calibration_jobs import build_jobs as build_pilot_calibration_jobs
from common import (
    ROOT,
    SOURCE_DISCLOSURES,
    compile_benchmark_requests,
    current_vendor_commit,
    episode_paths,
    load_json,
    read_topics,
    validate_episode,
)
from refinement_run import validate_run as validate_refinement_run


REQUIRED_PATHS = [
    "AGENTS.md",
    "README.md",
    "ip/POSITIONING.md",
    "ip/WORLD_BIBLE.md",
    "ip/VOICE_BIBLE.md",
    "ip/EDITORIAL_GUARDRAILS.md",
    "ip/STYLE_CONTRACT.md",
    "ip/CAST_BIBLE.yaml",
    "topics/taxonomy.yaml",
    "topic-bank.csv",
    "config/README.md",
    "schemas/episode.schema.json",
    "benchmarks/scenes.yaml",
    "benchmarks/styles.yaml",
    "benchmarks/cast-reference-plan.yaml",
    "benchmarks/CALIBRATION.md",
    "benchmarks/reference-assets/identity-neutral/manifest.json",
    "benchmarks/reference-assets/identity-refinement/manifest.json",
    "benchmarks/SCORING_RUBRIC.md",
    "benchmarks/scorecard.csv",
    "benchmarks/style14-refinement.yaml",
    "benchmarks/refinement-qa/style14-v2-decisions.json",
    "benchmarks/refinement-runs/style14-v2.json",
    "benchmarks/contracts/B03-initial-v1.json",
    "benchmarks/contracts/B07-initial-v1.json",
    "benchmarks/contracts/B09-initial-v1.json",
    "benchmarks/contracts/B11-initial-v1.json",
    *[f"benchmarks/runs/B{number:02d}.json" for number in range(1, 13)],
    "templates/episode.template.yaml",
    "templates/card-layout.json",
    "templates/postflight-qa.template.json",
    "scripts/build_benchmark_jobs.py",
    "scripts/benchmark_run.py",
    "scripts/sync_scorecard_counts.py",
    "scripts/build_style14_refinement_jobs.py",
    "scripts/refinement_run.py",
    "scripts/build_pilot_calibration_jobs.py",
    "scripts/place_illustration_stage.py",
    "vendor/hand-drawn-styles/STYLES.md",
    "vendor/hand-drawn-styles/LICENSE",
]


def png_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def validate_repository() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).exists():
            errors.append(f"missing required path: {relative}")

    styles_files = [path for path in ROOT.rglob("STYLES.md") if ".git" not in path.parts]
    expected_styles = ROOT / "vendor" / "hand-drawn-styles" / "STYLES.md"
    if styles_files != [expected_styles]:
        listed = ", ".join(str(path.relative_to(ROOT)) for path in styles_files)
        errors.append(f"there must be exactly one upstream STYLES.md under vendor; found: {listed}")

    modules = (ROOT / ".gitmodules").read_text(encoding="utf-8") if (ROOT / ".gitmodules").exists() else ""
    if "https://github.com/threerocks/hand-drawn-styles.git" not in modules:
        errors.append(".gitmodules must point to the official threerocks/hand-drawn-styles upstream")
    license_text = (ROOT / "vendor" / "hand-drawn-styles" / "LICENSE").read_text(encoding="utf-8")
    if "MIT License" not in license_text or "Copyright (c) 2026 liulei" not in license_text:
        errors.append("upstream MIT license is missing or altered")

    try:
        load_json(ROOT / "schemas" / "episode.schema.json")
        load_json(ROOT / "templates" / "card-layout.json")
        taxonomy = load_json(ROOT / "topics" / "taxonomy.yaml")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"machine-readable JSON/YAML parse failure: {exc}")
        taxonomy = {}
    if set(taxonomy.get("relationships", {})) != {"family", "romance", "friendship", "self"}:
        errors.append("topic taxonomy must define all four relationship groups")

    cast = load_json(ROOT / "ip" / "CAST_BIBLE.yaml")
    characters = cast.get("characters", [])
    if {item.get("id") for item in characters} != {"achi", "zhoushu", "qinyi"}:
        errors.append("cast bible must define exactly achi, zhoushu and qinyi")
    required_character_fields = {
        "immutable_traits",
        "variable_traits",
        "facial_features",
        "body_proportions",
        "hairstyle",
        "fixed_clothing",
        "fixed_props",
        "gesture_habits",
        "language_habits",
        "flaws",
        "growth_arc",
        "forbidden_drift",
    }
    for character in characters:
        missing = sorted(required_character_fields - set(character))
        if missing:
            errors.append(f"cast {character.get('id')}: missing fields {', '.join(missing)}")
        for field in ("immutable_traits", "variable_traits", "gesture_habits", "flaws", "forbidden_drift"):
            if len(character.get(field, [])) < 3:
                errors.append(f"cast {character.get('id')}: {field} needs at least three concrete entries")

    required_topic_columns = {
        "topic_id",
        "relationship",
        "scene",
        "surface_conflict",
        "hidden_need",
        "hook",
        "visual_action",
        "mentor_mode",
        "ending_type",
        "source",
        "status",
        "metrics",
    }
    topics = read_topics()
    if len(topics) < 12:
        errors.append(f"topic bank needs at least 12 complete topics; found {len(topics)}")
    if topics and not required_topic_columns <= set(topics[0]):
        errors.append("topic bank is missing required columns")
    topic_ids = [row.get("topic_id") for row in topics]
    if len(topic_ids) != len(set(topic_ids)):
        errors.append("topic ids must be unique")
    if set(row.get("relationship") for row in topics) != {"family", "romance", "friendship", "self"}:
        errors.append("topic bank must cover all four relationship groups")
    for row in topics:
        topic_id = row.get("topic_id", "?")
        for column in required_topic_columns - {"metrics"}:
            if not str(row.get(column, "")).strip():
                errors.append(f"topic {topic_id}: empty required field {column}")
        if row.get("source") not in SOURCE_DISCLOSURES:
            errors.append(f"topic {topic_id}: unsupported source type")
        try:
            json.loads(row.get("metrics") or "{}")
        except json.JSONDecodeError:
            errors.append(f"topic {topic_id}: metrics must be JSON")

    episodes = []
    for path in episode_paths():
        episode = load_json(path)
        episodes.append(episode)
        errors.extend(validate_episode(episode, str(path.relative_to(ROOT))))
    if len(episodes) < 4:
        errors.append(f"at least four seven-page pilot scripts are required; found {len(episodes)}")
    if len({episode.get("relationship") for episode in episodes}) < 4:
        errors.append("the four pilot scripts must collectively cover family, romance, friendship and self")
    known_topics = set(topic_ids)
    for episode in episodes:
        if episode.get("topic_id") not in known_topics:
            errors.append(f"{episode.get('episode_id')}: topic_id is absent from topic bank")

    styles = load_json(ROOT / "benchmarks" / "styles.yaml")
    scenes = load_json(ROOT / "benchmarks" / "scenes.yaml")
    plan = load_json(ROOT / "benchmarks" / "cast-reference-plan.yaml")
    if [str(item.get("style_id")) for item in styles.get("candidates", [])] != ["10", "14", "18"]:
        errors.append("benchmark candidate styles must be exactly 10, 14 and 18")
    if len(scenes.get("scenes", [])) != 12:
        errors.append("benchmark must define exactly 12 standard scenes")
    if scenes.get("matrix", {}).get("runs_per_scene_style", 0) < 3:
        errors.append("benchmark requires at least three generations per scene-style unit")
    for style in styles.get("candidates", []):
        for ref in style.get("style_references", []):
            if ref.get("role") != "style-only":
                errors.append(f"style {style.get('style_id')}: style reference must be style-only")
    for style_plan in plan.get("styles", []):
        if set(style_plan.get("individual_sheets", {})) != {"achi", "zhoushu", "qinyi"}:
            errors.append(f"style {style_plan.get('style_id')}: incomplete individual reference plan")
        if set(style_plan.get("group_sheets", {})) != {"achi_zhoushu_qinyi"}:
            errors.append(f"style {style_plan.get('style_id')}: incomplete group transport reference plan")

    reference_manifest_path = ROOT / "benchmarks" / "reference-assets" / "identity-neutral" / "manifest.json"
    try:
        reference_manifest = load_json(reference_manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"identity reference manifest parse failure: {exc}")
        reference_manifest = {}
    expected_reference_characters = {
        "benchmarks/reference-assets/identity-neutral/achi.png": ["achi"],
        "benchmarks/reference-assets/identity-neutral/zhoushu.png": ["zhoushu"],
        "benchmarks/reference-assets/identity-neutral/qinyi.png": ["qinyi"],
        "benchmarks/reference-assets/identity-neutral/pair-achi-zhoushu.png": ["achi", "zhoushu"],
        "benchmarks/reference-assets/identity-neutral/pair-achi-qinyi.png": ["achi", "qinyi"],
        "benchmarks/reference-assets/identity-neutral/cast-trio.png": ["achi", "zhoushu", "qinyi"],
    }
    if reference_manifest.get("role") != "identity-only":
        errors.append("identity reference manifest role must be identity-only")
    if reference_manifest.get("status") != "accepted_for_benchmark":
        errors.append("identity reference manifest must be accepted_for_benchmark")
    if reference_manifest.get("asset_set_version") != "2.1.0":
        errors.append("identity reference asset set must use the reviewed 2.1.0 treatment")
    if reference_manifest.get("render_treatment") != "functional_flat_cleanup":
        errors.append("identity references must use the functional flat cleanup treatment")
    if reference_manifest.get("cast_bible_version") != cast.get("schema_version"):
        errors.append("identity reference manifest cast bible version is stale")
    manifest_assets = reference_manifest.get("assets", [])
    manifest_by_path = {item.get("path"): item for item in manifest_assets}
    if set(manifest_by_path) != set(expected_reference_characters):
        errors.append("identity reference manifest must contain exactly the six planned assets")
    for relative, expected_characters in expected_reference_characters.items():
        asset = manifest_by_path.get(relative, {})
        path = ROOT / relative
        if asset.get("characters") != expected_characters:
            errors.append(f"{relative}: identity reference character coverage is incorrect")
        if asset.get("qa_status") != "accepted":
            errors.append(f"{relative}: identity reference is not accepted")
        if not path.is_file():
            errors.append(f"missing identity reference asset: {relative}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != asset.get("sha256"):
            errors.append(f"{relative}: identity reference hash differs from manifest")
        dimensions = png_dimensions(path)
        expected_dimensions = (asset.get("width"), asset.get("height"))
        if dimensions != expected_dimensions:
            errors.append(f"{relative}: PNG dimensions differ from manifest")

    try:
        requests = compile_benchmark_requests()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"benchmark prompt compilation failed: {exc}")
        requests = []
    if len(requests) != 36:
        errors.append(f"benchmark compiler must produce 36 requests; produced {len(requests)}")
    for request in requests:
        required_request_fields = {
            "subject",
            "composition",
            "style_id",
            "style_references",
            "character_references",
            "negative_constraints",
            "aspect_ratio",
            "reserved_text_regions",
            "prompt",
        }
        if not required_request_fields <= set(request):
            errors.append(f"{request.get('request_id')}: incomplete standardized request")
            continue
        style_paths = {item["path"] for item in request["style_references"]}
        cast_paths = {item["path"] for item in request["character_references"]}
        if style_paths & cast_paths:
            errors.append(f"{request.get('request_id')}: style and cast references point to the same asset")
        if any(item.get("role") != "style-only" for item in request["style_references"]):
            errors.append(f"{request.get('request_id')}: invalid style reference role")
        if any(item.get("role") != "identity-only" for item in request["character_references"]):
            errors.append(f"{request.get('request_id')}: invalid character reference role")
        if len(request["style_references"] + request["character_references"]) > 5:
            errors.append(f"{request.get('request_id')}: reference count exceeds the generation adapter limit")
        if not request.get("ready_for_generation"):
            errors.append(f"{request.get('request_id')}: benchmark request is missing a reference asset")
        if "【" in request["prompt"] or "】" in request["prompt"]:
            errors.append(f"{request.get('request_id')}: unresolved upstream placeholder")

    score_path = ROOT / "benchmarks" / "scorecard.csv"
    with score_path.open("r", encoding="utf-8", newline="") as handle:
        score_rows = list(csv.DictReader(handle))
    expected_pairs = {(f"B{number:02d}", style) for number in range(1, 13) for style in ("10", "14", "18")}
    actual_pairs = {(row.get("scene_id"), row.get("style_id")) for row in score_rows}
    if len(score_rows) != 36 or actual_pairs != expected_pairs:
        errors.append("scorecard must contain exactly one row for each of the 36 scene-style units")

    for run_path in sorted((ROOT / "benchmarks" / "runs").glob("B*.json")):
        try:
            run = load_json(run_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{run_path.relative_to(ROOT)}: parse failure: {exc}")
            continue
        for error in validate_run(run):
            errors.append(f"{run_path.relative_to(ROOT)}: {error}")

    refinement_path = ROOT / "benchmarks" / "refinement-runs" / "style14-v2.json"
    try:
        refinement_run = load_json(refinement_path)
        for error in validate_refinement_run(refinement_run, verify_files=False):
            errors.append(f"{refinement_path.relative_to(ROOT)}: {error}")
        result = refinement_run.get("objective_result", {})
        if (result.get("successful_count"), result.get("attempt_count")) != (27, 36):
            errors.append("style-14 refinement result must record the reviewed 27/36 objective outcome")
        if result.get("hard_gate_passed") is not True:
            errors.append("style-14 refinement must pass its objective generation gate")
        if refinement_run.get("blind_review", {}).get("status") != "pending_two_independent_reviewers":
            errors.append("style-14 refinement must remain pending two independent reviewers")
    except (OSError, json.JSONDecodeError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"style-14 refinement validation failed: {exc}")

    ep003 = next((episode for episode in episodes if episode.get("episode_id") == "EP-003"), None)
    if ep003 is None:
        errors.append("EP-003 calibration pilot is missing")
    else:
        try:
            pilot_jobs = build_pilot_calibration_jobs(ep003)
            if len(pilot_jobs) != 7:
                errors.append(f"EP-003 calibration packet must contain seven page jobs; found {len(pilot_jobs)}")
        except (OSError, json.JSONDecodeError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"EP-003 calibration packet failed to compile: {exc}")

    if styles.get("upstream", {}).get("pinned_commit") != current_vendor_commit():
        errors.append("benchmarks/styles.yaml pinned commit does not match checked-out vendor commit")
    contract_files = list(ROOT.rglob("STYLE_CONTRACT.md"))
    if contract_files != [ROOT / "ip" / "STYLE_CONTRACT.md"]:
        errors.append("there must be exactly one business STYLE_CONTRACT.md")
    lock_path = ROOT / "config" / "style-lock.json"
    if lock_path.exists():
        lock = load_json(lock_path)
        if lock.get("production_name") != "dialogue-sketch-v1":
            errors.append("style lock must use production_name dialogue-sketch-v1")
        if str(lock.get("upstream_style_id")) not in {"10", "14", "18"}:
            errors.append("style lock selected an unsupported candidate")
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print(f"PROJECT VALIDATION FAILED ({len(errors)} issue(s))")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PROJECT VALIDATION PASSED")
    print("  cast: 3 complete characters")
    print("  identity references: 5 maintained sheets + 1 transport pack with verified hashes")
    print("  topics: 12 complete pilot topics")
    print("  episodes: 4 seven-page pilot scripts")
    print("  benchmark: 12 scenes × 3 styles = 36 standardized requests")
    print("  benchmark attempts: 108 objectively reviewed; historical prompt revisions are pinned")
    print("  style-14 refinement: 27/36 objective successes; blind review still pending")
    print("  style state: benchmarking (production remains fail-closed until two-reviewer lock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
