#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any

from common import ROOT, dump_json, load_json, sha256_file, validate_episode, validate_postflight


def split_visual_units(text: str, max_units: int) -> list[str]:
    closing_punctuation = set("，。！？：；、）》】}）’”」』…")

    def visual_units(value: str) -> float:
        return sum(0.55 if ord(char) < 128 else 1.0 for char in value)

    lines: list[str] = []
    current = ""
    units = 0.0
    for char in text.strip():
        weight = 0.55 if ord(char) < 128 else 1.0
        if current and units + weight > max_units and char in closing_punctuation:
            current += char
            units += weight
        elif current and units + weight > max_units:
            lines.append(current)
            current = char
            units = weight
        else:
            current += char
            units += weight
    if current:
        lines.append(current)
    if len(lines) >= 2:
        last_units = visual_units(lines[-1])
        while last_units < 7 and visual_units(lines[-2]) > 8:
            move_count = 2 if lines[-2][-1] in closing_punctuation else 1
            if visual_units(lines[-2][:-move_count]) < 7:
                break
            moved = lines[-2][-move_count:]
            lines[-2] = lines[-2][:-move_count]
            lines[-1] = moved + lines[-1]
            last_units += visual_units(moved)
    return lines or [""]


def find_page_image(image_dir: Path | None, episode_id: str, page: int) -> Path | None:
    if image_dir is None:
        return None
    names = [
        f"{episode_id}-p{page:02d}.png",
        f"{episode_id}-p{page:02d}.jpg",
        f"page-{page:02d}.png",
        f"page-{page:02d}.jpg",
        f"{page:02d}.png",
        f"{page:02d}.jpg",
    ]
    for name in names:
        candidate = image_dir / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def svg_text_block(
    x: float,
    y: float,
    width: float,
    height: float,
    lines: list[dict[str, str]],
    layout: dict[str, Any],
) -> str:
    max_chars = int(layout["text"]["max_chars_per_line"])
    rendered: list[tuple[str, bool]] = []
    for item in lines:
        speaker = item["speaker"]
        prefix = "" if speaker == "旁白" else f"{speaker}："
        wrapped = split_visual_units(prefix + item["text"], max_chars)
        rendered.extend((line, speaker != "旁白" and index == 0) for index, line in enumerate(wrapped))

    body_size = int(layout["text"]["body_size"])
    line_height = body_size * float(layout["text"]["line_height"])
    max_fit = max(1, int(height // line_height))
    if len(rendered) > max_fit:
        body_size = max(28, int(body_size * max_fit / len(rendered)))
        line_height = body_size * float(layout["text"]["line_height"])
    color = html.escape(layout["text"]["color"])
    font_family = html.escape(layout["text"]["font_family"])
    fragments = [
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="18" fill="#FDF9F2" fill-opacity="0.92"/>',
        f'<text x="{x + 22:.1f}" y="{y + body_size + 12:.1f}" fill="{color}" font-size="{body_size}" font-family="{font_family}">',
    ]
    for index, (line, is_speaker) in enumerate(rendered):
        dy = 0 if index == 0 else line_height
        weight = "600" if is_speaker else "400"
        fragments.append(
            f'<tspan x="{x + 22:.1f}" dy="{dy:.1f}" font-weight="{weight}">{html.escape(line)}</tspan>'
        )
    fragments.append("</text>")
    return "\n".join(fragments)


def render_page_svg(
    episode: dict[str, Any],
    page: dict[str, Any],
    layout: dict[str, Any],
    image_path: Path | None,
) -> str:
    width = int(layout["canvas"]["width"])
    height = int(layout["canvas"]["height"])
    background = html.escape(layout["background"])
    fragments = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{background}"/>',
    ]
    if image_path is not None:
        suffix = image_path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        embedded_href = f"data:{mime};base64,{encoded}"
        fragments.append(
            f'<image href="{html.escape(embedded_href, quote=True)}" x="0" y="0" width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice"/>'
        )
    else:
        fragments.extend(
            [
                f'<rect x="44" y="44" width="{width - 88}" height="{height - 118}" rx="36" fill="#EEF0ED"/>',
                f'<ellipse cx="{width * 0.52:.1f}" cy="{height * 0.72:.1f}" rx="{width * 0.24:.1f}" ry="{height * 0.055:.1f}" fill="#DDE3E5"/>',
            ]
        )

    grouped: dict[str, list[dict[str, str]]] = {}
    for copy_line in page["copy"]:
        grouped.setdefault(copy_line.get("region_id", "header"), []).append(copy_line)
    regions = {item["id"]: item for item in page["image"]["reserved_text_regions"]}
    for region_id, lines in grouped.items():
        region = regions[region_id]
        fragments.append(
            svg_text_block(
                x=region["x"] * width,
                y=region["y"] * height,
                width=region["width"] * width,
                height=region["height"] * height,
                lines=lines,
                layout=layout,
            )
        )

    footer_y = height - 28
    footer_size = int(layout["footer"]["font_size"])
    footer_color = html.escape(layout["footer"]["color"])
    font_family = html.escape(layout["text"]["font_family"])
    if page["number"] == int(layout["footer"]["show_source_on_page"]):
        source = html.escape(episode["source"]["disclosure"])
        footer = source
    else:
        footer = html.escape(f"坐一会儿再走 · {page['number']:02d}/07")
    fragments.append(
        f'<text x="54" y="{footer_y}" fill="{footer_color}" font-size="{footer_size}" font-family="{font_family}">{footer}</text>'
    )
    fragments.append("</svg>")
    return "\n".join(fragments) + "\n"


def export_episode(
    episode_path: Path,
    output_dir: Path,
    image_dir: Path | None,
    allow_placeholders: bool,
    qa_path: Path | None = None,
) -> list[Path]:
    episode = load_json(episode_path)
    errors = validate_episode(episode, str(episode_path))
    if errors:
        raise ValueError("episode failed preflight:\n" + "\n".join(f"- {item}" for item in errors))
    if image_dir is not None and not allow_placeholders:
        if qa_path is None:
            raise ValueError("final-image export requires a passed postflight QA file")
        qa = load_json(qa_path)
        qa_errors = validate_postflight(episode, qa, str(qa_path))
        if qa_errors:
            raise ValueError("postflight QA failed:\n" + "\n".join(f"- {item}" for item in qa_errors))
    layout = load_json(ROOT / "templates" / "card-layout.json")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    manifest_pages: list[dict[str, Any]] = []
    for page in episode["pages"]:
        image = find_page_image(image_dir, episode["episode_id"], page["number"])
        if image is None and not allow_placeholders:
            raise FileNotFoundError(f"missing image for page {page['number']:02d}; pass --allow-placeholders for a layout proof")
        svg = render_page_svg(episode, page, layout, image)
        target = output_dir / f"{episode['episode_id']}-p{page['number']:02d}.svg"
        target.write_text(svg, encoding="utf-8")
        outputs.append(target)
        manifest_pages.append(
            {
                "page": page["number"],
                "card": target.name,
                "card_sha256": sha256_file(target),
                "illustration": str(image) if image else None,
                "layout_status": "final-image" if image else "placeholder-proof",
            }
        )
    dump_json(
        output_dir / "manifest.json",
        {
            "episode_id": episode["episode_id"],
            "title": episode["title"],
            "source_type": episode["source"]["type"],
            "text_rendering": "local-svg-overlay",
            "pages": manifest_pages,
        },
    )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Lay out seven Chinese-text SVG cards locally.")
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--qa", type=Path)
    parser.add_argument("--allow-placeholders", action="store_true")
    args = parser.parse_args()

    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    episode = load_json(episode_path)
    output_dir = args.out or ROOT / "build" / "cards" / episode["episode_id"]
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    image_dir = args.image_dir
    if image_dir is not None and not image_dir.is_absolute():
        image_dir = ROOT / image_dir
    qa_path = args.qa
    if qa_path is not None and not qa_path.is_absolute():
        qa_path = ROOT / qa_path
    outputs = export_episode(episode_path, output_dir, image_dir, args.allow_placeholders, qa_path)
    print(f"Exported {len(outputs)} locally typeset cards to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
