#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PLATES = {"quiet", "achi-talk", "zhoushu-talk", "together"}
SPEAKERS = {"阿迟", "周叔", "旁白"}
BANNED = (
    "高敏感人格",
    "回避型",
    "原生家庭决定",
    "真正爱你的人",
    "你应该学会",
    "建立边界感",
    "情绪价值",
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def visual_units(value: str) -> float:
    return sum(0.55 if ord(char) < 128 else 1.0 for char in value.replace("\n", ""))


def wrap(value: str, limit: float) -> list[str]:
    if "\n" in value:
        return [line for part in value.splitlines() for line in wrap(part, limit)]
    rows: list[str] = []
    current = ""
    width = 0.0
    for char in value.strip():
        weight = 0.55 if ord(char) < 128 else 1.0
        if current and width + weight > limit:
            rows.append(current)
            current = ""
            width = 0.0
        current += char
        width += weight
    if current:
        rows.append(current)
    return rows or [""]


def validate_episode(episode: dict) -> list[str]:
    pages = episode.get("pages", [])
    errors: list[str] = []
    if len(pages) != 5:
        return ["剧集必须正好五页"]
    if pages[0].get("kind") != "cover":
        errors.append("第一页必须是 cover")
    if pages[-1].get("kind") != "landing":
        errors.append("第五页必须是 landing")
    if sum(page.get("kind") == "action" for page in pages) != 1:
        errors.append("必须正好有一页 action")

    all_copy: list[str] = []
    for number, page in enumerate(pages, 1):
        if page.get("plate") not in PLATES:
            errors.append(f"第 {number} 页使用了未知镜头")
        kind = page.get("kind")
        if kind == "cover":
            value = str(page.get("text", "")).strip()
            all_copy.append(value)
            if not value or visual_units(value) > 30:
                errors.append("封面必须存在且不超过 30 个视觉字符")
        elif kind in {"dialogue", "action"}:
            lines = page.get("lines", [])
            if not 1 <= len(lines) <= 2:
                errors.append(f"第 {number} 页只能有 1–2 个文本块")
            page_units = 0.0
            for item in lines:
                speaker = item.get("speaker")
                value = str(item.get("text", "")).strip()
                all_copy.append(value)
                if speaker not in SPEAKERS:
                    errors.append(f"第 {number} 页人物名不合法")
                if not value or visual_units(value) > 34:
                    errors.append(f"第 {number} 页单段必须存在且不超过 34 个视觉字符")
                page_units += visual_units(value)
            if page_units > 58:
                errors.append(f"第 {number} 页文字过密")
            if kind == "action" and not any("？" in str(item.get("text", "")) or "吗" in str(item.get("text", "")) for item in lines):
                errors.append("action 页必须出现一句可直接说出口的请求")
        elif kind == "landing":
            for key in ("story", "takeaway", "question"):
                value = str(page.get(key, "")).strip()
                all_copy.append(value)
                if not value:
                    errors.append(f"第五页缺少 {key}")
            if visual_units(str(page.get("takeaway", ""))) > 28:
                errors.append("第五页落点过长")
        else:
            errors.append(f"第 {number} 页类型不合法")

    joined = "\n".join(all_copy)
    errors.extend(f"出现空泛表达：{phrase}" for phrase in BANNED if phrase in joined)
    return errors


def svg_text(
    lines: Iterable[str],
    x: int,
    y: int,
    size: int,
    color: str,
    font: str,
    weight: int = 400,
    leading: float = 1.25,
    anchor: str = "start",
) -> str:
    rows = [
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-family="{html.escape(font, quote=True)}" font-weight="{weight}" text-anchor="{anchor}">'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * leading
        rows.append(f'<tspan x="{x}" dy="{dy:.1f}">{html.escape(line)}</tspan>')
    rows.append("</text>")
    return "\n".join(rows)


def find_art(plate: str) -> Path | None:
    for suffix in ("png", "jpg", "jpeg", "webp"):
        candidate = ROOT / "assets" / "plates" / f"{plate}.{suffix}"
        if candidate.is_file():
            return candidate
    return None


def art_fragment(path: Path | None, plate: str, x: int, y: int, width: int, height: int, theme: dict) -> str:
    if path is not None:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return (
            f'<image href="data:{mime};base64,{encoded}" x="{x}" y="{y}" '
            f'width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet"/>'
        )
    proof = theme["colors"]["proof"]
    font = theme["font_family"]
    return "\n".join(
        [
            f'<line x1="{x + 80}" y1="{y + height // 2}" x2="{x + width - 80}" y2="{y + height // 2}" '
            f'stroke="{proof}" stroke-width="2" stroke-dasharray="9 13"/>',
            svg_text([f"{plate} · 插画占位，不作为成品"], x + width // 2, y + height // 2 - 24, 22, proof, font, anchor="middle"),
        ]
    )


def page_dots(page_number: int, colors: dict) -> str:
    items = []
    for index in range(1, 6):
        radius = 7 if index == page_number else 4
        fill = colors["accent"] if index == page_number else colors["proof"]
        items.append(f'<circle cx="{486 + (index - 1) * 27}" cy="1370" r="{radius}" fill="{fill}"/>')
    return "\n".join(items)


def render_card(episode: dict, page: dict, page_number: int, theme: dict) -> str:
    colors = theme["colors"]
    font = theme["font_family"]
    output = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">',
        f'<rect width="1080" height="1440" fill="{colors["paper"]}"/>',
        svg_text(["坐一会儿再走"], 76, 70, 22, colors["muted"], font, 500),
        f'<line x1="76" y1="94" x2="154" y2="94" stroke="{colors["accent"]}" stroke-width="5" stroke-linecap="round"/>',
    ]
    image = find_art(page["plate"])
    kind = page["kind"]

    if kind == "cover":
        output.extend(
            [
                svg_text(wrap(page["text"], 12), 76, 190, 72, colors["ink"], font, 700, 1.18),
                art_fragment(image, page["plate"], 54, 410, 972, 780, theme),
                svg_text(["阿迟 × 周叔"], 76, 1280, 27, colors["muted"], font, 500),
            ]
        )
    elif kind in {"dialogue", "action"}:
        output.append(art_fragment(image, page["plate"], 70, 115, 940, 690, theme))
        y = 880
        for item in page["lines"]:
            speaker = item["speaker"]
            speaker_color = colors["achi"] if speaker == "阿迟" else colors["zhoushu"]
            copy = wrap(item["text"], 18)
            emphasize = kind == "action" and speaker == "阿迟"
            output.extend(
                [
                    svg_text([speaker], 78, y, 23, speaker_color, font, 700),
                    f'<line x1="78" y1="{y + 20}" x2="130" y2="{y + 20}" stroke="{speaker_color}" stroke-width="4" stroke-linecap="round"/>',
                ]
            )
            text_x = 112 if emphasize else 78
            if emphasize:
                output.append(
                    f'<line x1="78" y1="{y + 54}" x2="78" y2="{y + 54 + len(copy) * 66}" '
                    f'stroke="{colors["accent"]}" stroke-width="6" stroke-linecap="round"/>'
                )
            output.append(svg_text(copy, text_x, y + 75, 49, colors["ink"], font, 700 if emphasize else 500, 1.28))
            y += 92 + len(copy) * 63
    else:
        output.extend(
            [
                art_fragment(image, page["plate"], 95, 110, 890, 520, theme),
                svg_text(wrap(page["story"], 19), 78, 730, 40, colors["muted"], font, 400, 1.35),
            ]
        )
        takeaway = wrap(page["takeaway"], 10)
        output.extend(
            [
                svg_text(takeaway, 78, 980, 64, colors["ink"], font, 700, 1.22),
                f'<line x1="78" y1="{992 + len(takeaway) * 78}" x2="265" y2="{992 + len(takeaway) * 78}" '
                f'stroke="{colors["accent"]}" stroke-width="7" stroke-linecap="round"/>',
                svg_text(wrap(page["question"], 21), 78, 1260, 31, colors["muted"], font, 500, 1.32),
                svg_text([episode.get("source", "")], 1004, 1374, 16, colors["muted"], font, 400, anchor="end"),
            ]
        )

    output.extend([page_dots(page_number, colors), "</svg>"])
    return "\n".join(output) + "\n"


def write_pngs(cards_dir: Path) -> int:
    try:
        import cairosvg  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PNG 导出需要 CairoSVG：python3 -m pip install cairosvg") from exc
    png_dir = cards_dir.parent / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for svg_path in sorted(cards_dir.glob("*.svg")):
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_dir / f"{svg_path.stem}.png"), output_width=1080, output_height=1440)
        count += 1
    return count


def build(source: Path, export_png: bool = False) -> Path:
    episode = read_json(source)
    errors = validate_episode(episode)
    if errors:
        raise ValueError("剧集校验失败：\n- " + "\n- ".join(errors))

    theme = read_json(ROOT / "templates" / "theme.json")
    visual = read_json(ROOT / "visual" / "plates.json")
    target = ROOT / "build" / episode["episode_id"]
    cards_dir = target / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    used_plates = dict.fromkeys(page["plate"] for page in episode["pages"])
    with (target / "prompts.jsonl").open("w", encoding="utf-8") as handle:
        for plate_id in used_plates:
            plate = visual["plates"][plate_id]
            prompt = ". ".join(
                (
                    visual["style"],
                    "Characters: " + "; ".join(visual["identity"][character] for character in plate["characters"]),
                    "Composition: " + plate["direction"],
                    "Background: " + visual["background"],
                    "Hard exclusions: " + visual["global_negative"],
                )
            ) + "."
            row = {
                "plate": plate_id,
                "prompt": prompt,
                "aspect_ratio": visual["canvas"],
                "references": [
                    "assets/references/achi.png",
                    "assets/references/zhoushu.png",
                    "assets/references/achi-zhoushu.png",
                ],
                "output_path": f"assets/plates/{plate_id}.png",
                "reuse": "generate once and reuse across episodes",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    for number, page in enumerate(episode["pages"], 1):
        path = cards_dir / f'{episode["episode_id"]}-{number:02d}.svg'
        path.write_text(render_card(episode, page, number, theme), encoding="utf-8")

    png_count = write_pngs(cards_dir) if export_png else 0
    (target / "caption.txt").write_text(episode.get("caption", "").strip() + "\n", encoding="utf-8")
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "episode_id": episode["episode_id"],
                "format": "five-card-fixed-plate-v1",
                "cards": 5,
                "png_cards": png_count,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one five-card fixed-character dialogue episode.")
    parser.add_argument("episode", type=Path)
    parser.add_argument("--png", action="store_true", help="also render 1080×1440 PNG cards with CairoSVG")
    args = parser.parse_args()
    source = args.episode if args.episode.is_absolute() else ROOT / args.episode
    result = build(source, export_png=args.png)
    print(f"Built {result.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
