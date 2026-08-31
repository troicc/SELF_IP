#!/usr/bin/env python3
"""Build a five-card, fixed-character dialogue episode.

The production model is intentionally small:
- exactly five cards;
- two recurring characters;
- four reusable half-body illustration plates;
- local typography, never model-generated Chinese text.
"""

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
    """Approximate rendered width: Chinese=1, ASCII=0.55."""
    return sum(0.55 if ord(char) < 128 else 1.0 for char in text.replace("\n", ""))


def wrap_text(text: str, max_units: float) -> list[str]:
    """Wrap copy without introducing dependencies or model-side typography."""
    if "\n" in text:
        wrapped: list[str] = []
        for paragraph in text.splitlines():
            wrapped.extend(wrap_text(paragraph, max_units))
        return wrapped

    lines: list[str] = []
    current = ""
    units = 0.0
    for char in text.strip():
        weight = 0.55 if ord(char) < 128 else 1.0
        if current and units + weight > max_units:
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

    action_pages = 0
    all_copy: list[str] = []
    for page_number, page in enumerate(pages, 1):
        kind = page.get("kind")
        plate = page.get("plate")
        if kind not in ALLOWED_KINDS:
            errors.append(f"page {page_number}: unsupported kind {kind!r}")
        if plate not in ALLOWED_PLATES:
            errors.append(f"page {page_number}: unsupported plate {plate!r}")

        if kind == "cover":
            copy = str(page.get("text", "")).strip()
            all_copy.append(copy)
            if not copy:
                errors.append("page 1: missing cover text")
            if visual_units(copy) > 30:
                errors.append("page 1: cover exceeds 30 visual units")

        elif kind in {"dialogue", "action"}:
            lines = page.get("lines")
            if not isinstance(lines, list) or not 1 <= len(lines) <= 2:
                errors.append(f"page {page_number}: needs one or two dialogue blocks")
                continue

            page_units = 0.0
            for item in lines:
                speaker = item.get("speaker")
                copy = str(item.get("text", "")).strip()
                all_copy.append(copy)
                if speaker not in ALLOWED_SPEAKERS:
                    errors.append(f"page {page_number}: unknown speaker {speaker!r}")
                if not copy:
                    errors.append(f"page {page_number}: empty dialogue")
                if visual_units(copy) > 34:
                    errors.append(f"page {page_number}: one block exceeds 34 visual units")
                page_units += visual_units(copy)
            if page_units > 58:
                errors.append(f"page {page_number}: copy is too dense")

            if kind == "action":
                action_pages += 1
                has_concrete_phrase = any(
                    "？" in str(item.get("text", ""))
                    or "吗" in str(item.get("text", ""))
                    or "能不能" in str(item.get("text", ""))
                    for item in lines
                )
                if not has_concrete_phrase:
                    errors.append("page 4: action page needs a sentence that can be said directly")

        elif kind == "landing":
            for key in ("story", "takeaway", "question"):
                copy = str(page.get(key, "")).strip()
                all_copy.append(copy)
                if not copy:
                    errors.append(f"page 5: missing {key}")
            if visual_units(str(page.get("takeaway", ""))) > 28:
                errors.append("page 5: takeaway exceeds 28 visual units")

    if action_pages != 1:
        errors.append("episode must contain exactly one action page")

    joined = "\n".join(all_copy)
    for phrase in sorted(BANNED_PHRASES):
        if phrase in joined:
            errors.append(f"copy contains banned abstraction: {phrase}")
    return errors


def prompt_for_plate(plate_id: str, visual: dict[str, Any]) -> str:
    plate = visual["plates"][plate_id]
    identities = [visual["identity"][name] for name in plate["characters"]]
    return ". ".join(
        [
            visual["style"],
            "Characters: " + "; ".join(identities),
            "Composition: " + plate["direction"],
            "Background: " + visual["background"],
            "Hard exclusions: " + visual["global_negative"],
        ]
    ) + "."


def find_plate(assets_dir: Path, plate_id: str) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = assets_dir / f"{plate_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def embed_image(path: Path, x: int, y: int, width: int, height: int) -> str:
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<image href="data:{mime};base64,{encoded}" x="{x}" y="{y}" '
        f'width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet"/>'
    )


def svg_text(
    lines: Iterable[str],
    *,
    x: int,
    y: int,
    size: int,
    color: str,
    font_family: str,
    weight: int = 400,
    leading: float = 1.25,
    anchor: str = "start",
) -> str:
    output = [
        f'<text x="{x}" y="{y}" fill="{html.escape(color)}" font-size="{size}" '
        f'font-family="{html.escape(font_family, quote=True)}" font-weight="{weight}" '
        f'text-anchor="{anchor}">'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * leading
        output.append(f'<tspan x="{x}" dy="{dy:.1f}">{html.escape(line)}</tspan>')
    output.append("</text>")
    return "\n".join(output)


def art_fragment(
    theme: dict[str, Any],
    image: Path | None,
    plate_id: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> str:
    if image:
        return embed_image(image, x, y, width, height)

    proof = theme["colors"]["proof"]
    font = theme["font_family"]
    return "\n".join(
        [
            f'<line x1="{x + 80}" y1="{y + height // 2}" '
            f'x2="{x + width - 80}" y2="{y + height // 2}" '
            f'stroke="{proof}" stroke-width="2" stroke-dasharray="9 13"/>',
            svg_text(
                [f"{plate_id} · 插画占位，不作为成品"],
                x=x + width // 2,
                y=y + height // 2 - 24,
                size=22,
                color=proof,
                font_family=font,
                anchor="middle",
            ),
        ]
    )


def progress_dots(page_number: int, theme: dict[str, Any]) -> str:
    colors = theme["colors"]
    dots = []
    for index in range(1, 6):
        dots.append(
            f'<circle cx="{486 + (index - 1) * 27}" cy="1370" '
            f'r="{7 if index == page_nuber else 4}" '
            f'fill="{colors["accent"] if index == page_nuber else colors["proof"]}"/>'
        )
    return "\n".join(dots)


def render_card(
    episode: dict[str, Any],
    page: dict[str, Any],
    page_number: int,
    theme: dict[str, Any],
    image: Path | None,
) -> str:
    colors = theme["colors"]
    font = theme["font_family"]
    output = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1080\" height=\"1440\" viewBox=\"0 0 1080 1440\">",
        f'<rect width="1080" height="1440" fill="{colors["paper"]}"/>',
        svg_text(
            ["坐一会儿再走"],
            x=76,
            y=70,
            size=22,
            color=colors["muted"],
            font_family=font,
            weight=500,
         ),
        f'<line x1="76" y1="94" x2="154" y2="94" stroke="{colors["accent"]}" '
        'stroke-width="5" stroke-linecap="round"/>',
    ]

    kind = page["kind"]
    if kind == "cover":
        output.extend(
            [
                svg_text(
                    wrap_text(page["text"], 12),
                    x=76,
                    y=190,
                    size=72,
                    color=colors["ink"],
                    font_family=font,
                    weight=700,
                    leading=1.18,
                ),
                art_fragment(
                    theme, image, page["plate"], x=54, y=410, width=972, height=780
                ),
                svg_text(
                  ["阿迟 × 周叔"],
                    x=76,
                    y=1280,
                    size=27,
                    color=colors["muted"],
                    font_family=font,
                    weight=500,
                ),
            ]
        )

    elif kind in {"dialogue", "action"}:
        output.append(
            art_fragment(theme, image, page["plate"], x=70, y=115, width=940, height=690)
        )
       y = 880
        for item in page["lines"]:
            speaker = item["speaker"]
            speaker_color = {
                "阿迟": colors["achi"],
                "周叔": colors["zhoushu"],
                "旁白": colors["muted"],
            }[speaker]
            copy_lines = wrap_text(item["text"], 18)
            emphasize = kind == "action" and speaker == "阿迟"

            output.append(
                svg_text(
                    [speaker],
                    x=78,
                    y=y,
                    size=23,
                    color=speaker_color,
                    font_family=font,
                    weight=700,
                )
            )
            output.append(
                f'<line x1="78" y1="{y + 20}" x2="130" y2="{y + 20}" '
                f'stroke="{speaker_color}" stroke-width="4" stroke-linecap="round"/>'
            )
            text_x = 112 if emphasize else 78
            if emphasize:
                output.append(
                    f'<line x1="78" y1="{y + 54}" x2="78" '
                    f'y2="{y + 54 + len(copy_lines) * 66}" stroke="{colors["accent"]}" '
                    'stroke-width="6" stroke-linecap="round"/>'
                )
            output.append(
                svg_text(
                    copy_lines,
                    x=text_x,
                    y=y + 75,
                    size=49,
                    color=colors["ink"],
                    font_family=font,
                    weight=700 if emphasize else 500,
                    leading=1.28,
                )
            )
            y += 92 + len(copy_lines) * 63

    elif kind == "landing":
        output.append(
            art_fragment(theme, image, page["plate"], x=95, y=110, width=890, height=520)
        )
        output.append(
            svg_text(
                wrap_text(page["story"], 19),
                x=78,
                y=730,
                size=40,
                color=colors["muted"],
                font_family=font,
                leading=1.35,
            )
        )
        takeaway = wrap_text(page["takeaway"], 10)
        output.append(
            svg_text(
                takeaway,
                x=78,
                y=980,
                size=64,
                color=colors["ink"],
                font_family=font,
                weight=700,
                leading=1.22,
            )
        )
        underline_y = 992 + len(takeaway) * 78
        output.append(
            f'<line x1="78" y1="{underline_y}" x2="265" y2="{underline_y}" '
            f'stroke="{colors["accent"]}" stroke-width="7" stroke-linecap="round"/>'
        )
        output.append(
            svg_text(
                wrap_text(page["question"], 21),
                x=78,
                y=1260,
                size=31,
                color=colors["muted"],
                font_family=font,
                weight=500,
                leading=1.32,
            )
       )
        output.append(
            svg_text(
                [episode.get("source", "")],
                x=1004,
                y=1374,
                size=16,
                color=colors["muted"],
                font_family=font,
                anchor="end",
           )
        )

    output.extend([progress_dots(page_number, theme), "</svg>"])
    return "\n".join(output) + "\n"


def build(
    episode_path: Path,
    *,
    out_dir: Path | None = None,
    assets_dir: Path | None = None,
) -> Path:
    episode = load_json(episode_path)
    errors = validate_episode(episode)
    if errors:
        raise ValueError("episode validation failed:\n" + "\n".join(f"- {e}" for e in errors))

    visual = load_json(ROOT / "visual" / "plates.json")
    theme = load_json(ROOT / "templates" / "theme.json")
    episode_id = episode["episode_id"]
    out_dir = out_dir or ROOT / "build" / episode_id
    assets_dir = assets_dir or ROOT / "assets" / "plates"
    cards_dir = out_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    used_plates = list(dict.fromkeys(page["plate"] for page in episode["pages"]))
    with (out_dir / "prompts.jsonl").open("w", encoding="utf-8") as handle:
        for plate_id in used_plates:
            handle.write(
                json.dumps(
                    {
                        "plate": plate_id,
                        "prompt": prompt_for_plate(plate_id, visual),
                        "aspect_ratio": visual["canvas"],
                        "references": [
                            "assets/references/achi.png",
                            "assets/references/zhoushu.png",
                            "assets/references/achi-zhoushu.png",
                        ],
                        "output_path": f"assets/plates/{plate_id}.png",
                        "reuse_policy": "generate once, then reuse across episodes",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    manifest_pages = []
    for page_number, page in enumerate(episode["pages"], 1):
        image = find_plate(assets_dir, page["plate"])
        target = cards_dir / f"{episode_id}-{page_number:02d}.svg"
        target.write_text(
            render_card(episode, page, page_number, theme, image),
            encoding="utf-8",
        )
        manifest_pages.append(
            {
                "page": page_number,
                "kind": page["kind"],
                "plate": page["plate"],
                "has_art": image is not None,
                "card": str(target.relative_to(out_dir)),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )

    (out_dir / "caption.txt").write_text(
        episode.get("caption", "").strip() + "\n", encoding="utf-8"
    )
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--assets", type=Path)
    args = parser.parse_args()

    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    out_dir = args.out if args.out is None or args.out.is_absolute() else ROOT / args.out
    assets_dir = (
        args.assets if args.assets is None or args.assets.is_absolute() else ROOT / args.assets
    )
    result = build(episode_path, out_dir=out_dir, assets_dir=assets_dir)
    try:
        display = result.relative_to(ROOT)
    except ValueError:
        display = result
    print(f"Built {display}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
