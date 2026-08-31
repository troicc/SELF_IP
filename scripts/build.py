#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_PLATES = {"quiet", "achi-talk", "zhoushu-talk", "together"}
ALLOWED_KINDS = {"cover", "dialogue", "action", "landing"}
ALLOWED_SPEAKERS = {"阿迟", "周叔", "旁白"}
BANNED_PHRASES = {
    "高敏感人格",
    "回避型",
    "原生家庭决定",
    "真正爱你的人",
    "你应该学会",
    "建立边界感",
    "情绪价值",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def visual_units(text: str) -> float:
    return sum(0.55 if ord(char) < 128 else 1.0 for char in text.replace("\n", ""))


def wrap_text(text: str, max_units: float) -> list[str]:
    if "\n" in text:
        result: list[str] = []
        for part in text.splitlines():
            result.extend(wrap_text(part, max_units))
        return result
    punctuation = set("，。！？：；、）》】）’”」』…")
    lines: list[str] = []
    current = ""
    units = 0.0
    for char in text.strip():
        weight = 0.55 if ord(char) < 128 else 1.0
        if current and units + weight > max_units:
            if char in punctuation:
                current += char
            lines.append(current)
            current = ""
            units = 0.0
        current += char
        units += weight
    if current:
        lines.append(current)
    return lines or [""]


def validate_episode(episode: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pages = episode.get("pages")
    if not isinstance(pages, list) or len(pages) != 5:
        return ["episode must contain exactly five pages"]
    if pages[0].get("kind") != "cover":
        errors.append("page 1 must be cover")
    if pages[-1].get("kind") != "landing":
        errors.append("page 5 must be landing")

    important_lines = 0
    all_text: list[str] = []
    for index, page in enumerate(pages, 1):
        kind = page.get("kind")
        plate = page.get("plate")
        if kind not in ALLOWED_KINDS:
            errors.append(f"page {index}: unsupported kind {kind!r}")
        if plate not in ALLOWED_PLATES:
            errors.append(f"page {index}: unsupported plate {plate!r}")

        if kind == "cover":
            text = str(page.get("text", "")).strip()
            all_text.append(text)
            if not text:
                errors.append("page 1: missing cover text")
            if visual_units(text) > 30:
                errors.append("page 1: cover is longer than 30 visual units")
        elif kind in {"dialogue", "action"}:
            lines = page.get("lines")
            if not isinstance(lines, list) or not 1 <= len(lines) <= 2:
                errors.append(f"page {index}: dialogue/action page needs one or two lines")
                continue
            page_units = 0.0
            for line in lines:
                speaker = line.get("speaker")
                text = str(line.get("text", "")).strip()
                all_text.append(text)
                if speaker not in ALLOWED_SPEAKERS:
                    errors.append(f"page {index}: unknown speaker {speaker!r}")
                if not text:
                    errors.append(f"page {index}: empty dialogue")
                if visual_units(text) > 34:
                    errors.append(f"page {index}: one text block is longer than 34 visual units")
                page_units += visual_units(text)
            if page_units > 58:
                errors.append(f"page {index}: page copy is too dense")
            if kind == "action":
                important_lines += 1
                if not any("？" in str(line.get("text", "")) or "吗" in str(line.get("text", "")) for line in lines):
                    errors.append("page 4: action page must contain a concrete ask or sentence to say")
        elif kind == "landing":
            for key in ("story", "takeaway", "question"):
                text = str(page.get(key, "")).strip()
                all_text.append(text)
                if not text:
                    errors.append(f"page 5: missing {key}")
            if visual_units(str(page.get("takeaway", ""))) > 28:
                errors.append("page 5: takeaway is too long")

    if important_lines != 1:
        errors.append("episode must contain exactly one action page")
    joined = "\n".join(all_text)
    for phrase in sorted(BANNED_PHRASES):
        if phrase in joined:
            errors.append(f"copy contains banned abstract phrase: {phrase}")
    return errors


def prompt_for_plate(plate_id: str, visual: dict[str, Any]) -> str:
    plate = visual["plates"][plate_id]
    identities = [visual["identity"][character] for character in plate["characters"]]
    return ". ".join(
        [
            visual["style"],
            "Characters: " + "; ".join(identities),
            "Composition: " + plate["direction"],
            "Background: " + visual["background"],
            "Hard exclusions: " + visual["global_negative"],
        ]
    ) + "."


def image_path_for(assets_dir: Path, plate_id: str) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        path = assets_dir / f"{plate_id}{suffix}"
        if path.is_file():
            return path
    return None


def embedded_image(path: Path, x: int, y: int, width: int, height: int) -> str:
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[suffix]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<image href="data:{mime};base64,{encoded}" x="{x}" y="{y}" '
        f'width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet"/>'
    )


def text_element(
    lines: Iterable[str],
    x: int,
    y: int,
    size: int,
    line_height: float,
    color: str,
    font_family: str,
    weight: int = 400,
    anchor: str = "start",
) -> str:
    fragments = [
        f'<text x="{x}" y="{y}" fill="{html.escape(color)}" font-size="{size}" '
        f'font-family="{html.escape(font_family, quote=True)}" font-weight="{weight}" text-anchor="{anchor}">'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * line_height
        fragments.append(f'<tspan x="{x}" dy="{dy:.1f}">{html.escape(line)}</tspan>')
    fragments.append("</text>")
    return "\n".join(fragments)


def proof_placeholder(theme: dict[str, Any], plate: str, x: int, y: int, width: int, height: int) -> str:
    font = theme["font_family"]
    proof = theme["colors"]["proof"]
    return "\n".join(
        [
            f'<line x1="{x + 80}" y1="{y + height // 2}" x2="{x + width - 80}" y2="{y + height // 2}" stroke="{proof}" stroke-width="2" stroke-dasharray="8 12"/>',
            text_element([f"{plate} · 插画占位，不进入正式发布"], x + width // 2, y + height // 2 - 24, 22, 1.2, proof, font, 400, "middle"),
        ]
    )


def art_fragment(theme: dict[str, Any], image: Path | None, plate: str, x: int, y: int, width: int, height: int) -> str:
    return embedded_image(image, x, y, width, height) if image else proof_placeholder(theme, plate, x, y, width, height)


def page_dots(page_number: int, theme: dict[str, Any]) -> str:
    accent = theme["colors"]["accent"]
    muted = theme["colors"]["proof"]
    items = []
    start_x = 486
    for index in range(1, 6):
        radius = 7 if index == page_number else 4
        color = accent if index == page_number else muted
        items.append(f'<circle cx="{start_x + (index - 1) * 27}" cy="1370" r="{radius}" fill="{color}"/>')
    return "\n".join(items)


def render_card(episode: dict[str, Any], page: dict[str, Any], page_number: int, theme: dict[str, Any], image: Path | None) -> str:
    width = int(theme["canvas"]["width"])
    height = int(theme["canvas"]["height"])
    colors = theme["colors"]
    font = theme["font_family"]
    fragments = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{colors["paper"]}"/>',
        text_element(["坐一会儿再走"], 76, 70, 22, 1.0, colors["muted"], font, 500),
        f'<line x1="76" y1="94" x2="154" y2="94" stroke="{colors["accent"]}" stroke-width="5" stroke-linecap="round"/>',
    ]

    kind = page["kind"]
    if kind == "cover":
        title_lines = wrap_text(page["text"], 12)
        fragments.append(text_element(title_lines, 76, 190, 72, 1.18, colors["ink"], font, 700))
        fragments.append(art_fragment(theme, image, page["plate"], 54, 410, 972, 780))
        fragments.append(text_element(["阿迟 × 周叔"], 76, 1280, 27, 1.0, colors["muted"], font, 500))
    elif kind in {"dialogue", "action"}:
        fragments.append(art_fragment(theme, image, page["plate"], 70, 115, 940, 690))
        y = 880
        for line in page["lines"]:
            speaker = line["speaker"]
            speaker_color = colors["achi"] if speaker == "阿迟" else colors["zhoushu"] if speaker == "周叔" else colors["muted"]
            fragments.append(text_element([speaker], 78, y, 23, 1.0, speaker_color, font, 700))
            fragments.append(f'<line x1="78" y1="{y + 20}" x2="130" y2="{y + 20}" stroke="{speaker_color}" stroke-width="4" stroke-linecap="round"/>')
            copy_lines = wrap_text(line["text"], 18)
            if kind == "action" and speaker == "阿迟":
                fragments.append(f'<line x1="78" y1="{y + 54}" x2="78" y2="{y + 54 + len(copy_lines) * 66}" stroke="{colors["accent"]}" stroke-width="6" stroke-linecap="round"/>')
                text_x = 112
                weight = 700
            else:
                text_x = 78
                weight = 500
            fragments.append(text_element(copy_lines, text_x, y + 75, 49, 1.28, colors["ink"], font, weight))
            y += 92 + len(copy_lines) * 63
    elif kind == "landing":
        fragments.append(art_fragment(theme, image, page["plate"], 95, 110, 890, 520))
        story_lines = wrap_text(page["story"], 19)
        fragments.append(text_element(story_lines, 78, 730, 40, 1.35, colors["muted"], font, 400))
        takeaway_lines = wrap_text(page["takeaway"], 10)
        fragments.append(text_element(takeaway_lines, 78, 980, 64, 1.22, colors["ink"], font, 700))
        fragments.append(f'<line x1="78" y1="{980 + len(takeaway_lines) * 78 + 12}" x2="265" y2="{980 + len(takeaway_lines) * 78 + 12}" stroke="{colors["accent"]}" stroke-width="7" stroke-linecap="round"/>')
        question_lines = wrap_text(page["question"], 21)
        fragments.append(text_element(question_lines, 78, 1260, 31, 1.32, colors["muted"], font, 500))
        fragments.append(text_element([episode.get("source", "")], 1004, 1374, 16, 1.0, colors["muted"], font, 400, "end"))

    fragments.append(page_dots(page_number, theme))
    fragments.append("</svg>")
    return "\n".join(fragments) + "\n"


def build(episode_path: Path, out_dir: Path | None = None, assets_dir: Path | None = None) -> Path:
    episode = load_json(episode_path)
    errors = validate_episode(episode)
    if errors:
        raise ValueError("episode validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    visual = load_json(ROOT / "visual" / "plates.json")
    theme = load_json(ROOT / "templates" / "theme.json")
    episode_id = episode["episode_id"]
    out_dir = out_dir or ROOT / "build" / episode_id
    assets_dir = assets_dir or ROOT / "assets" / "plates"
    cards_dir = out_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    used_plates = list(dict.fromkeys(page["plate"] for page in episode["pages"]))
    prompt_rows = []
    for plate_id in used_plates:
        prompt_rows.append(
            {
                "plate": plate_id,
                "prompt": prompt_for_plate(plate_id, visual),
                "aspect_ratio": visual["canvas"],
                "reference_images": [
                    "assets/references/achi.png",
                    "assets/references/zhoushu.png",
                    "assets/references/achi-zhoushu.png",
                ],
                "output_path": f"assets/plates/{plate_id}.png",
                "reuse_policy": "generate once, then reuse across episodes",
            }
        )
    with (out_dir / "prompts.jsonl").open("w", encoding="utf-8") as handle:
        for row in prompt_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest_pages = []
    for number, page in enumerate(episode["pages"], 1):
        image = image_path_for(assets_dir, page["plate"])
        svg = render_card(episode, page, number, theme, image)
        target = cards_dir / f"{episode_id}-{number:02d}.svg"
        target.write_text(svg, encoding="utf-8")
        manifest_pages.append(
            {
                "page": number,
                "kind": page["kind"],
                "plate": page["plate"],
                "has_art": image is not None,
                "card": str(target.relative_to(out_dir)),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )

    (out_dir / "caption.txt").write_text(episode.get("caption", "").strip() + "\n", encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "title": episode["title"],
                "format": "five-card-fixed-plate-v1",
                "pages": manifest_pages,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a five-card fixed-character story episode.")
    parser.add_argument("episode", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--assets", type=Path)
    args = parser.parse_args()

    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    out_dir = args.out if args.out is None or args.out.is_absolute() else ROOT / args.out
    assets_dir = args.assets if args.assets is None or args.assets.is_absolute() else ROOT / args.assets
    result = build(episode_path, out_dir, assets_dir)
    print(f"Built {result.relative_to(ROOT) if result.is_relative_to(ROOT) else result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
