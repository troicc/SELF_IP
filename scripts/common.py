from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BEATS = [
    "cover_question",
    "concrete_event",
    "emotional_deepening",
    "rename_problem",
    "pushback",
    "small_action_or_open",
    "landing_and_question",
]
SOURCE_DISCLOSURES = {
    "original_fiction": "本故事为原创虚构，人物与情节均为创作。",
    "authorized_anonymous_adaptation": "本故事经授权匿名改编，识别性细节已作虚构化处理。",
}
AI_MARKERS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bAIGC\b",
        r"\bAI[ -]?(?:generated|assisted|created)\b",
        r"generated (?:by|with) AI",
        r"made with AI",
        r"AI\s*辅助",
        r"AI\s*生成",
        r"人工智能\s*生成",
        r"模型\s*生成",
        r"OpenAI",
        r"Midjourney",
        r"gpt-image",
    )
]
DIAGNOSIS_MARKERS = [
    "回避型人格",
    "焦虑型依恋",
    "安全型依恋",
    "自恋型人格",
    "人格障碍",
    "NPD",
    "你就是高敏感",
    "高敏感人格",
    "原生家庭决定",
    "情绪价值",
]
POLARIZATION_MARKERS = [
    "真正爱你的人",
    "不回复就是不在乎",
    "不联系就是不爱",
    "男人都",
    "女人都",
    "老一辈都",
    "年轻人都",
    "必须断联",
    "趁早远离",
]
FLAT_VILLAIN_MARKERS = ["烂人", "渣男", "渣女", "根本不配", "这种人都", "他就是坏", "她就是坏"]
FALSE_EXPERIENCE_MARKERS = ["真人真事", "亲身经历", "我朋友的真实故事", "真实投稿"]
POSTFLIGHT_FIELDS = [
    "character_identity_ok",
    "clothing_ok",
    "props_ok",
    "people_count_ok",
    "anatomy_ok",
    "text_safe_regions_clear",
    "no_readable_or_gibberish_text",
    "no_ai_assistance_label_or_watermark",
]


def load_json(path: Path) -> Any:
    """Load JSON or a JSON-syntax YAML 1.2 document."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def visible_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def user_visible_strings(episode: dict[str, Any]) -> list[str]:
    strings = [episode.get("title", ""), episode.get("comment_question", "")]
    strings.append(episode.get("source", {}).get("disclosure", ""))
    for page in episode.get("pages", []):
        strings.extend(line.get("text", "") for line in page.get("copy", []))
    return [value for value in strings if isinstance(value, str)]


def find_markers(values: Iterable[str], patterns: Iterable[re.Pattern[str]]) -> list[str]:
    found: list[str] = []
    for value in values:
        for pattern in patterns:
            if pattern.search(value):
                found.append(pattern.pattern)
    return sorted(set(found))


def validate_episode(episode: dict[str, Any], label: str = "episode") -> list[str]:
    errors: list[str] = []
    required = {
        "episode_id",
        "topic_id",
        "title",
        "version",
        "relationship",
        "source",
        "cast",
        "scene_anchor",
        "conflict",
        "ending",
        "pages",
        "comment_question",
    }
    missing = sorted(required - set(episode))
    if missing:
        return [f"{label}: missing required keys: {', '.join(missing)}"]

    episode_id = episode.get("episode_id", "")
    if not re.fullmatch(r"EP-\d{3}", str(episode_id)):
        errors.append(f"{label}: invalid episode_id {episode_id!r}")
    if not re.fullmatch(r"T\d{3}", str(episode.get("topic_id", ""))):
        errors.append(f"{label}: invalid topic_id {episode.get('topic_id')!r}")
    if episode.get("relationship") not in {"family", "romance", "friendship", "self"}:
        errors.append(f"{label}: invalid relationship")

    source = episode.get("source", {})
    source_type = source.get("type")
    if source_type not in SOURCE_DISCLOSURES:
        errors.append(f"{label}: unsupported source type {source_type!r}")
    elif source.get("disclosure") != SOURCE_DISCLOSURES[source_type]:
        errors.append(f"{label}: source disclosure does not match source type")
    if source_type == "authorized_anonymous_adaptation" and not source.get("authorization_record"):
        errors.append(f"{label}: authorized adaptation needs a controlled authorization_record pointer")

    cast = episode.get("cast", [])
    if not cast or len(cast) != len(set(cast)) or not set(cast) <= {"achi", "zhoushu", "qinyi"}:
        errors.append(f"{label}: cast must contain unique known character ids")

    anchor = episode.get("scene_anchor", {})
    dimensions = [anchor.get(key) for key in ("time", "place", "object", "observable_action")]
    if sum(bool(value and str(value).strip()) for value in dimensions) < 3:
        errors.append(f"{label}: concrete scene needs at least three populated dimensions")

    conflict = episode.get("conflict", {})
    for key in ("surface", "hidden_need", "non_malicious_alternative"):
        if visible_length(str(conflict.get(key, ""))) < 4:
            errors.append(f"{label}: conflict.{key} is too vague")

    ending = episode.get("ending", {})
    if ending.get("type") not in {
        "small_action",
        "rephrased_request",
        "open_unresolved",
        "boundary_without_verdict",
        "repair_attempt",
    }:
        errors.append(f"{label}: unsupported ending type")
    if not ending.get("action") and not ending.get("open_state"):
        errors.append(f"{label}: ending needs an action or an honest open_state")

    pages = episode.get("pages", [])
    if len(pages) != 7:
        errors.append(f"{label}: exactly seven pages are required")
    else:
        beats = [page.get("beat") for page in pages]
        if beats != EXPECTED_BEATS:
            errors.append(f"{label}: page beats must be {EXPECTED_BEATS}")
        numbers = [page.get("number") for page in pages]
        if numbers != list(range(1, 8)):
            errors.append(f"{label}: page numbers must be 1..7")

    for page in pages:
        page_no = page.get("number", "?")
        copy_lines = page.get("copy", [])
        if not copy_lines:
            errors.append(f"{label} page {page_no}: at least one copy line is required")
        total = 0
        for line in copy_lines:
            text = str(line.get("text", ""))
            length = visible_length(text)
            total += length
            if length > 30:
                errors.append(f"{label} page {page_no}: one copy line exceeds 30 visible characters")
            if line.get("speaker") not in {"旁白", "阿迟", "周叔", "琴姨"}:
                errors.append(f"{label} page {page_no}: unknown speaker")
        if page_no == 1 and total > 24:
            errors.append(f"{label} page 1: cover copy exceeds 24 visible characters")
        if total > 58:
            errors.append(f"{label} page {page_no}: copy exceeds 58 visible characters")

        image = page.get("image", {})
        image_cast = image.get("characters", [])
        if not image_cast or not set(image_cast) <= set(cast):
            errors.append(f"{label} page {page_no}: image characters must be a nonempty subset of cast")
        for key in ("subject", "composition", "visual_action"):
            if visible_length(str(image.get(key, ""))) < 4:
                errors.append(f"{label} page {page_no}: image.{key} is too vague")
        regions = image.get("reserved_text_regions", [])
        if not regions:
            errors.append(f"{label} page {page_no}: at least one reserved text region is required")
        region_ids: set[str] = set()
        for region in regions:
            region_id = region.get("id")
            region_ids.add(region_id)
            try:
                x = float(region["x"])
                y = float(region["y"])
                width = float(region["width"])
                height = float(region["height"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"{label} page {page_no}: invalid reserved region")
                continue
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
                errors.append(f"{label} page {page_no}: reserved region exceeds normalized canvas")
        for line in copy_lines:
            if line.get("region_id") and line.get("region_id") not in region_ids:
                errors.append(f"{label} page {page_no}: copy points to missing region {line.get('region_id')!r}")

        image_text = " ".join(str(image.get(key, "")) for key in ("subject", "composition", "visual_action"))
        for line in copy_lines:
            text = str(line.get("text", "")).strip()
            if len(text) >= 6 and text in image_text:
                errors.append(f"{label} page {page_no}: body copy leaked verbatim into image brief")

    visible = user_visible_strings(episode)
    ai_hits = find_markers(visible, AI_MARKERS)
    if ai_hits:
        errors.append(f"{label}: user-visible AI assistance marker is forbidden: {', '.join(ai_hits)}")
    joined = "\n".join(visible)
    for marker in DIAGNOSIS_MARKERS:
        if marker.lower() in joined.lower():
            errors.append(f"{label}: diagnosis/terminology marker is forbidden: {marker}")
    for marker in POLARIZATION_MARKERS:
        if marker in joined:
            errors.append(f"{label}: polarization marker is forbidden: {marker}")
    for marker in FLAT_VILLAIN_MARKERS:
        if marker in joined:
            errors.append(f"{label}: flat-villain marker is forbidden: {marker}")
    for marker in FALSE_EXPERIENCE_MARKERS:
        if marker in joined:
            errors.append(f"{label}: false lived-experience marker is forbidden: {marker}")

    correction_cues = ("不一定", "说轻了", "说快了", "也可能不是", "只走得到", "还没想好", "替人家说完", "我那比喻")
    if not any(cue in joined for cue in correction_cues):
        errors.append(f"{label}: no elder uncertainty, correction or limitation is visible")
    if len(pages) >= 5 and not any(line.get("speaker") == "阿迟" for line in pages[4].get("copy", [])):
        errors.append(f"{label}: page 5 must let Achi push back or question")
    if len(pages) == 7:
        page7_texts = [line.get("text", "") for line in pages[6].get("copy", [])]
        if episode.get("comment_question") not in page7_texts:
            errors.append(f"{label}: page 7 must contain the exact comment_question")

    return errors


def validate_postflight(episode: dict[str, Any], qa: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if qa.get("episode_id") != episode.get("episode_id"):
        errors.append(f"{label}: QA episode_id does not match episode")
    if not str(qa.get("reviewer", "")).strip():
        errors.append(f"{label}: reviewer is required")
    if not str(qa.get("reviewed_at", "")).strip():
        errors.append(f"{label}: reviewed_at is required")
    pages = qa.get("pages", [])
    if len(pages) != 7:
        errors.append(f"{label}: postflight must contain exactly seven page reviews")
        return errors
    if [item.get("page") for item in pages] != list(range(1, 8)):
        errors.append(f"{label}: postflight page numbers must be 1..7")
    for item in pages:
        page = item.get("page", "?")
        for field in POSTFLIGHT_FIELDS:
            if item.get(field) is not True:
                errors.append(f"{label} page {page}: {field} must be explicitly true")
    return errors


def episode_paths() -> list[Path]:
    return sorted((ROOT / "episodes").glob("EP-*.yaml"))


def read_topics() -> list[dict[str, str]]:
    with (ROOT / "topic-bank.csv").open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def current_vendor_commit() -> str:
    vendor = ROOT / "vendor" / "hand-drawn-styles"
    result = subprocess.run(
        ["git", "-C", str(vendor), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_upstream_renderer(
    style_id: str,
    subject: str,
    aspect_ratio: str,
    variables: dict[str, str],
) -> str:
    renderer = ROOT / "vendor" / "hand-drawn-styles" / "scripts" / "render_prompt.py"
    command = [
        sys.executable,
        str(renderer),
        "--style",
        str(style_id),
        "--subject",
        subject,
        "--aspect",
        aspect_ratio,
        "--format",
        "text",
    ]
    for name, value in variables.items():
        if name == "文字":
            command.extend(["--text", value])
        else:
            command.extend(["--var", f"{name}={value}"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    prompt = result.stdout.strip()
    if "【" in prompt or "】" in prompt:
        raise ValueError(f"upstream renderer left a placeholder for style {style_id}")
    return prompt


def _candidate_map(styles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["style_id"]): item for item in styles["candidates"]}


def _reference_plan_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["style_id"]): item for item in plan["styles"]}


def character_references(style_id: str, characters: list[str], plan: dict[str, Any]) -> list[dict[str, Any]]:
    style_plan = _reference_plan_map(plan)[str(style_id)]
    refs: list[dict[str, Any]] = []
    character_set = set(characters)
    if character_set == {"achi", "zhoushu", "qinyi"}:
        relative = style_plan["group_sheets"]["achi_zhoushu_qinyi"]
        path = ROOT / relative
        refs.append(
            {
                "path": relative,
                "role": "identity-only",
                "reference_kind": "transport-group",
                "character_ids": ["achi", "zhoushu", "qinyi"],
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    else:
        for character_id in characters:
            relative = style_plan["individual_sheets"][character_id]
            path = ROOT / relative
            refs.append(
                {
                    "path": relative,
                    "role": "identity-only",
                    "reference_kind": "individual",
                    "character_ids": [character_id],
                    "exists": path.is_file(),
                    "sha256": sha256_file(path) if path.is_file() else None,
                }
            )
    pair_specs = [
        ("achi_zhoushu", ["achi", "zhoushu"]),
        ("achi_qinyi", ["achi", "qinyi"]),
    ]
    for key, ids in pair_specs:
        if set(ids) <= character_set:
            relative = style_plan["pair_sheets"][key]
            path = ROOT / relative
            refs.append(
                {
                    "path": relative,
                    "role": "identity-only",
                    "reference_kind": "pair",
                    "character_ids": ids,
                    "exists": path.is_file(),
                    "sha256": sha256_file(path) if path.is_file() else None,
                }
            )
    return refs


def style_references(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in candidate["style_references"]:
        relative = item["path"]
        path = ROOT / relative
        refs.append(
            {
                **item,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return refs


def compile_benchmark_requests() -> list[dict[str, Any]]:
    styles = load_json(ROOT / "benchmarks" / "styles.yaml")
    scenes = load_json(ROOT / "benchmarks" / "scenes.yaml")
    plan = load_json(ROOT / "benchmarks" / "cast-reference-plan.yaml")
    pinned = styles["upstream"]["pinned_commit"]
    actual = current_vendor_commit()
    if actual != pinned:
        raise ValueError(f"vendor commit mismatch: expected {pinned}, got {actual}")

    candidates = _candidate_map(styles)
    requests: list[dict[str, Any]] = []
    for scene in scenes["scenes"]:
        for style_id in scenes["matrix"]["style_ids"]:
            candidate = candidates[str(style_id)]
            language = candidate["prompt_language"]
            subject = scene["subject_zh"] if language == "zh" else scene["subject_en"]
            composition = scene["composition_zh"] if language == "zh" else scene["composition_en"]
            variables = dict(candidate.get("renderer_vars", {}))
            if str(style_id) in {"14", "18"}:
                variables["构图"] = composition
            if str(style_id) == "10":
                subject_for_renderer = f"{subject}；构图安排：{composition}"
            else:
                subject_for_renderer = subject
            prompt = run_upstream_renderer(
                style_id=str(style_id),
                subject=subject_for_renderer,
                aspect_ratio=scene["aspect_ratio"],
                variables=variables,
            )
            style_refs = style_references(candidate)
            cast_refs = character_references(str(style_id), scene["characters"], plan)
            negative = list(scenes["common_negative_constraints"]) + list(scene.get("negative_constraints", []))
            requests.append(
                {
                    "request_id": f"{scene['scene_id']}-S{style_id}",
                    "scene_id": scene["scene_id"],
                    "scene_title": scene["title"],
                    "subject": subject,
                    "composition": composition,
                    "visual_action": scene["visual_action"],
                    "necessary_props": scene["necessary_props"],
                    "style_id": str(style_id),
                    "style_alias": candidate["alias"],
                    "prompt": prompt,
                    "prompt_sha256": sha256_text(prompt),
                    "style_references": style_refs,
                    "character_references": cast_refs,
                    "negative_constraints": negative,
                    "aspect_ratio": scene["aspect_ratio"],
                    "reserved_text_regions": scene["reserved_text_regions"],
                    "expected_attempts": scenes["matrix"]["runs_per_scene_style"],
                    "ready_for_generation": all(item["exists"] for item in style_refs + cast_refs),
                    "upstream": {
                        "repository": styles["upstream"]["repository"],
                        "commit": actual,
                        "renderer": styles["upstream"]["renderer"],
                        "recipe_source": styles["upstream"]["recipe_source"],
                    },
                }
            )
    return requests
