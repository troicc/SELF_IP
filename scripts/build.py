#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import math
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
PLATES = {"quiet", "achi-talk", "zhoushu-talk", "together"}
SPEAKERS = {"阿迟", "周叔"}
KINDS = {"cover", "dialogue", "action", "landing"}
BANNED = (
    "高敏感人格",
    "回避型",
    "情绪价值",
    "建立边界感",
    "真正爱你的人",
    "你应该学会",
    "归根结底",
    "人生的意义",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def visual_units(value: str) -> float:
    return sum(0.55 if ord(char) < 128 else 1.0 for char in value.replace("\n", ""))


def wrap_text(value: str, limit: float) -> list[str]:
    """Keep authored line breaks, only wrapping a line if it cannot fit."""
    if "\n" in value:
        lines: list[str] = []
        for part in value.splitlines():
            lines.extend(wrap_text(part, limit))
        return lines

    closing = set("，。！？：；、）》】）’”」』…")
    lines: list[str] = []
    current = ""
    used = 0.0
    for char in value.strip():
        weight = 0.55 if ord(char) < 128 else 1.0
        if current and used + weight > limit:
            if char in closing:
                current += char
                lines.append(current)
                current, used = "", 0.0
                continue
            lines.append(current)
            current, used = "", 0.0
        current += char
        used += weight
    if current:
        lines.append(current)
    return lines or [""]


def validate_episode(episode: dict[str, Any], visual: dict[str, Any]) -> None:
    errors: list[str] = []
    pages = episode.get("pages", [])
    if len(pages) != 5:
        errors.append("必须正好五页")
    if pages and pages[0].get("kind") != "cover":
        errors.append("第一页必须是 cover")
    if pages and pages[-1].get("kind") != "landing":
        errors.append("第五页必须是 landing")
    if sum(page.get("kind") == "action" for page in pages) != 1:
        errors.append("必须正好有一页 action")

    all_copy: list[str] = []
    short_bubbles = 0
    question_count = 0
    for number, page in enumerate(pages, 1):
        kind = page.get("kind")
        plate_id = page.get("plate")
        if kind not in KINDS:
            errors.append(f"第 {number} 页 kind 不合法")
        if plate_id not in PLATES:
            errors.append(f"第 {number} 页镜头不合法")
            continue

        plate = visual["plates"][plate_id]
        bubbles = page.get("bubbles", [])
        if not 1 <= len(bubbles) <= 3:
            errors.append(f"第 {number} 页必须有 1–3 个气泡")
        for bubble in bubbles:
            speaker = bubble.get("speaker")
            slot_name = bubble.get("slot")
            value = str(bubble.get("text", "")).strip()
            all_copy.append(value)
            if speaker not in SPEAKERS:
                errors.append(f"第 {number} 页 speaker 不合法")
            if slot_name not in plate["slots"]:
                errors.append(f"第 {number} 页气泡位 {slot_name!r} 不存在")
            if not value:
                errors.append(f"第 {number} 页有空气泡")
            if visual_units(value) > (52 if kind == "cover" else 42):
                errors.append(f"第 {number} 页单个气泡文字过长")
            if any(visual_units(line) <= 5 for line in value.splitlines() if line.strip()):
                short_bubbles += 1
            if "？" in value or "吗" in value:
                question_count += 1

        if kind == "action" and not any(
            phrase in "\n".join(str(bubble.get("text", "")) for bubble in bubbles)
            for phrase in ("几点", "能不能", "可以吗", "我来", "我陪")
        ):
            errors.append("action 页必须给出一句现实中可执行的表达")

        if kind == "landing":
            for key in ("note", "question"):
                value = str(page.get(key, "")).strip()
                all_copy.append(value)
                if not value:
                    errors.append(f"结尾页缺少 {key}")
            if visual_units(str(page.get("note", ""))) > 22:
                errors.append("结尾动作说明太长")

    joined = "\n".join(all_copy)
    for phrase in BANNED:
        if phrase in joined:
            errors.append(f"出现空泛或机器腔表达：{phrase}")
    if short_bubbles == 0:
        errors.append("全篇缺少一句真正短的回应")
    if question_count < 2:
        errors.append("对话缺少自然追问")
    if "……" not in joined:
        errors.append("全篇缺少一次停顿或吞回去的话")
    if not any(word in joined for word in ("摔", "邻居", "电话", "开会", "复诊", "视频")):
        errors.append("故事缺少可见、可记的现实细节")
    if errors:
        raise ValueError("剧集校验失败：\n- " + "\n- ".join(errors))


def svg_text(
    lines: Iterable[str],
    x: float,
    y: float,
    size: float,
    color: str,
    font: str,
    weight: int,
    leading: float,
    stroke_width: float = 0.0,
    anchor: str = "start",
    letter_spacing: float = 0.0,
) -> str:
    stroke = ""
    if stroke_width > 0:
        stroke = (
            f' stroke="{html.escape(color)}" stroke-width="{stroke_width:.2f}" '
            'paint-order="stroke fill" stroke-linejoin="round"'
        )
    parts = [
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{html.escape(color)}" font-size="{size:.1f}" '
        f'font-family="{html.escape(font, quote=True)}" font-weight="{weight}" text-anchor="{anchor}" '
        f'letter-spacing="{letter_spacing:.2f}"{stroke}>'
    ]
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else size * leading
        parts.append(f'<tspan x="{x:.1f}" dy="{dy:.1f}">{html.escape(line)}</tspan>')
    parts.append("</text>")
    return "\n".join(parts)


def find_art(art_dir: Path, plate_id: str) -> Path | None:
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = art_dir / f"{plate_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def embedded_art(path: Path) -> str:
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<image href="data:{mime};base64,{encoded}" x="0" y="0" width="1080" height="1440" '
        'preserveAspectRatio="xMidYMid slice"/>'
    )


def proof_art(plate: dict[str, Any], theme: dict[str, Any]) -> str:
    colors = theme["colors"]
    a = plate["mouths"]["阿迟"]
    z = plate["mouths"]["周叔"]
    return "\n".join(
        [
            f'<ellipse cx="{a[0]}" cy="1045" rx="185" ry="260" fill="{colors["sky"]}" opacity="0.38"/>',
            f'<circle cx="{a[0]}" cy="820" r="94" fill="#F1C5A7" opacity="0.68"/>',
            f'<ellipse cx="{z[0]}" cy="1045" rx="198" ry="266" fill="{colors["butter"]}" opacity="0.40"/>',
            f'<circle cx="{z[0]}" cy="820" r="98" fill="#E5B998" opacity="0.68"/>',
        ]
    )


def soft_tv_path(x: float, y: float, w: float, h: float, radius: float) -> str:
    """One smooth, slightly oval TV balloon used everywhere."""
    r = min(radius, h * 0.46, w * 0.19)
    return (
        f"M {x+r:.1f},{y:.1f} "
        f"C {x+w*0.34:.1f},{y-3:.1f} {x+w*0.66:.1f},{y-3:.1f} {x+w-r:.1f},{y:.1f} "
        f"C {x+w-r*0.26:.1f},{y:.1f} {x+w:.1f},{y+r*0.32:.1f} {x+w:.1f},{y+r:.1f} "
        f"L {x+w:.1f},{y+h-r:.1f} "
        f"C {x+w:.1f},{y+h-r*0.32:.1f} {x+w-r*0.26:.1f},{y+h:.1f} {x+w-r:.1f},{y+h:.1f} "
        f"C {x+w*0.66:.1f},{y+h+3:.1f} {x+w*0.34:.1f},{y+h+3:.1f} {x+r:.1f},{y+h:.1f} "
        f"C {x+r*0.26:.1f},{y+h:.1f} {x:.1f},{y+h-r*0.32:.1f} {x:.1f},{y+h-r:.1f} "
        f"L {x:.1f},{y+r:.1f} "
        f"C {x:.1f},{y+r*0.32:.1f} {x+r*0.26:.1f},{y:.1f} {x+r:.1f},{y:.1f} Z"
    )


def short_tail_path(
    x: float,
    y: float,
    w: float,
    h: float,
    mouth: tuple[float, float],
    progress: float,
    base_width: float,
    max_length: float,
) -> tuple[str, tuple[float, float], tuple[float, float]]:
    """Create one clean tapered tail, aimed at the mouth but never overlong.

    The visible tail stops before the face; the eye completes the invisible line.
    All normal tails share one width, curvature and maximum length.
    """
    mx, my = mouth
    attach_x = min(max(mx, x + 52), x + w - 52)
    attach_y = y + h - 1
    dx = mx - attach_x
    dy = my - attach_y
    distance = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / distance, dy / distance
    visible = min(distance * progress, max_length)
    tip_x = attach_x + ux * visible
    tip_y = attach_y + uy * visible

    px, py = -uy, ux
    half = base_width / 2
    left_x = attach_x + px * half
    left_y = attach_y + py * half
    right_x = attach_x - px * half
    right_y = attach_y - py * half
    bend_x = attach_x + ux * visible * 0.55 + px * 5
    bend_y = attach_y + uy * visible * 0.55 + py * 5
    path = (
        f"M {left_x:.1f},{left_y:.1f} "
        f"Q {bend_x:.1f},{bend_y:.1f} {tip_x:.1f},{tip_y:.1f} "
        f"Q {bend_x-px*10:.1f},{bend_y-py*10:.1f} {right_x:.1f},{right_y:.1f} Z"
    )
    return path, (attach_x, attach_y), (tip_x, tip_y)


def align_x(slot: dict[str, Any], width: float) -> float:
    x = float(slot["x"])
    max_w = float(slot["max_w"])
    align = slot.get("align", "left")
    if align == "right":
        return x + max_w - width
    if align == "center":
        return x + (max_w - width) / 2
    return x


def prepare_balloon(
    bubble: dict[str, Any],
    slot: dict[str, Any],
    mouth: tuple[float, float],
    theme: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    type_spec = theme["type"]
    balloon_spec = theme["balloon"]
    font_spec = theme["font"]

    size = float(type_spec["cover_size"] if kind == "cover" else type_spec["bubble_size"])
    if bubble.get("compact"):
        size = float(type_spec["bubble_small_size"])

    max_w = float(slot["max_w"])
    max_h = float(slot["max_h"])
    pad_x = float(balloon_spec["padding_x"])
    pad_y = float(balloon_spec["padding_y"])
    leading = float(type_spec["line_height"])

    while True:
        line_limit = max(5.5, (max_w - 2 * pad_x) / (size * 0.96))
        lines = wrap_text(str(bubble["text"]), line_limit)
        max_line = max(visual_units(line) for line in lines)
        width = min(max_w, max(float(balloon_spec["min_width"]), max_line * size * 0.96 + 2 * pad_x))
        height = 2 * pad_y + len(lines) * size * leading - size * (leading - 1)
        if height <= max_h and width <= max_w or size <= float(type_spec["min_size"]):
            break
        size -= 1.5

    x = align_x(slot, width)
    y = float(slot["y"])
    body_path = soft_tv_path(x, y, width, height, float(balloon_spec["radius"]))
    tail_path, tail_attach, tail_tip = short_tail_path(
        x,
        y,
        width,
        height,
        mouth,
        float(balloon_spec["tail_progress"]),
        float(balloon_spec["tail_base_width"]),
        float(balloon_spec["tail_max_length"]),
    )
    return {
        "speaker": bubble["speaker"],
        "emphasis": bool(bubble.get("emphasis")),
        "x": x,
        "y": y,
        "w": width,
        "h": height,
        "size": size,
        "lines": lines,
        "body_path": body_path,
        "tail_path": tail_path,
        "tail_attach": tail_attach,
        "tail_tip": tail_tip,
        "mouth": mouth,
        "font": font_spec["family"],
        "font_weight": font_spec["display_weight"] if bubble.get("emphasis") else font_spec["body_weight"],
        "stroke_width": font_spec["synthetic_stroke"],
        "leading": leading,
    }


def render_balloon(layout: dict[str, Any], theme: dict[str, Any]) -> str:
    colors = theme["colors"]
    balloon = theme["balloon"]
    fill = colors["balloon"]
    stroke = colors["balloon_line"]
    shadow = colors["shadow"]
    x, y, w, h = layout["x"], layout["y"], layout["w"], layout["h"]

    text_height = len(layout["lines"]) * layout["size"] * layout["leading"] - layout["size"] * (layout["leading"] - 1)
    first_baseline = y + (h - text_height) / 2 + layout["size"] * 0.78

    parts = [
        f'<g class="speech-balloon" data-speaker="{html.escape(layout["speaker"])}" '
        f'data-tail-progress="{balloon["tail_progress"]}" data-tail-target="{layout["mouth"][0]},{layout["mouth"][1]}">',
        f'<path d="{layout["tail_path"]}" fill="{shadow}" opacity="{balloon["shadow_opacity"]}" transform="translate(3 4)"/>',
        f'<path d="{layout["body_path"]}" fill="{shadow}" opacity="{balloon["shadow_opacity"]}" transform="translate(3 4)"/>',
        f'<path d="{layout["tail_path"]}" fill="{fill}" stroke="{stroke}" stroke-width="{balloon["stroke_width"]}" stroke-linejoin="round"/>',
        f'<path d="{layout["body_path"]}" fill="{fill}" stroke="{stroke}" stroke-width="{balloon["stroke_width"]}" stroke-linejoin="round"/>',
        svg_text(
            layout["lines"],
            x + w / 2,
            first_baseline,
            layout["size"],
            colors["ink"],
            layout["font"],
            layout["font_weight"],
            layout["leading"],
            layout["stroke_width"],
            anchor="middle",
            letter_spacing=0.10,
        ),
    ]
    if layout["emphasis"]:
        underline_y = y + h - 20
        parts.append(
            f'<path d="M {x+w*0.25:.1f},{underline_y:.1f} Q {x+w*0.50:.1f},{underline_y+5:.1f} {x+w*0.75:.1f},{underline_y:.1f}" '
            f'fill="none" stroke="{colors["coral"]}" stroke-width="4.6" stroke-linecap="round" opacity="0.72"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def page_header(theme: dict[str, Any], category: str) -> str:
    colors = theme["colors"]
    font = theme["font"]["family"]
    return "\n".join(
        [
            svg_text(["坐一会儿再走"], 62, 66, 23, colors["muted"], font, 600, 1.0, 0.15),
            f'<path d="M 62 87 Q 98 92 137 86" fill="none" stroke="{colors["coral"]}" stroke-width="4.2" stroke-linecap="round"/>',
            svg_text([category], 1018, 67, 20, colors["sage_line"], font, 600, 1.0, 0.10, anchor="end"),
        ]
    )


def page_footer(page_number: int, theme: dict[str, Any]) -> str:
    colors = theme["colors"]
    marks = []
    start = 466
    for index in range(1, 6):
        x = start + (index - 1) * 34
        if index == page_number:
            marks.append(f'<ellipse cx="{x}" cy="1374" rx="9" ry="5" fill="{colors["coral"]}"/>')
        else:
            marks.append(f'<circle cx="{x}" cy="1374" r="4" fill="{colors["proof"]}"/>')
    return "\n".join(marks)


def render_note(page: dict[str, Any], theme: dict[str, Any]) -> str:
    if not page.get("note"):
        return ""
    colors = theme["colors"]
    font = theme["font"]["family"]
    lines = wrap_text(page["note"], 18)
    return "\n".join(
        [
            f'<path d="M 72 1198 Q 210 1187 356 1199" fill="none" stroke="{colors["coral"]}" stroke-width="4.2" stroke-linecap="round" opacity="0.70"/>',
            svg_text(lines, 72, 1250, theme["type"]["note_size"], colors["ink"], font, 700, 1.18, 0.22),
        ]
    )


def render_page(
    episode: dict[str, Any],
    page: dict[str, Any],
    page_number: int,
    theme: dict[str, Any],
    visual: dict[str, Any],
    art_dir: Path,
) -> str:
    colors = theme["colors"]
    plate = visual["plates"][page["plate"]]
    art_path = find_art(art_dir, page["plate"])

    layouts = []
    for bubble in page["bubbles"]:
        slot = plate["slots"][bubble["slot"]]
        mouth = tuple(plate["mouths"][bubble["speaker"]])
        layouts.append(prepare_balloon(bubble, slot, mouth, theme, page["kind"]))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">',
        '<defs>',
        '<filter id="paper"><feTurbulence type="fractalNoise" baseFrequency="0.31" numOctaves="2" seed="11"/><feColorMatrix values="0 0 0 0 0.52  0 0 0 0 0.46  0 0 0 0 0.38  0 0 0 .035 0"/></filter>',
        '</defs>',
        f'<rect width="1080" height="1440" fill="{colors["paper"]}"/>',
        '<rect width="1080" height="1440" filter="url(#paper)" opacity="0.34"/>',
        f'<circle cx="1005" cy="120" r="8" fill="{colors["coral"]}" opacity="0.75"/>',
        f'<path d="M 954 114 q 18 -17 37 -2" fill="none" stroke="{colors["sage_line"]}" stroke-width="4" stroke-linecap="round" opacity="0.78"/>',
        embedded_art(art_path) if art_path else proof_art(plate, theme),
        page_header(theme, episode.get("category", "对话")),
    ]
    parts.extend(render_balloon(layout, theme) for layout in layouts)
    note = render_note(page, theme)
    if note:
        parts.append(note)
    if page.get("question"):
        font = theme["font"]["family"]
        parts.append(
            svg_text(
                [page["question"]],
                72,
                1320,
                theme["type"]["question_size"],
                colors["muted"],
                font,
                600,
                1.0,
                0.12,
            )
        )
    if page_number == 5:
        font = theme["font"]["family"]
        parts.append(svg_text([episode.get("source", "")], 1015, 1395, 16, colors["muted"], font, 500, 1.0, anchor="end"))
    parts.append(page_footer(page_number, theme))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def build(
    episode_path: Path,
    out_dir: Path | None = None,
    art_dir: Path | None = None,
) -> Path:
    episode = read_json(episode_path)
    theme = read_json(ROOT / "templates" / "theme.json")
    visual = read_json(ROOT / "visual" / "plates.json")
    validate_episode(episode, visual)

    target = out_dir or ROOT / "build" / episode["episode_id"]
    if not target.is_absolute():
        target = ROOT / target
    art_dir = art_dir or ROOT / "assets" / "plates"
    if not art_dir.is_absolute():
        art_dir = ROOT / art_dir
    cards_dir = target / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    used = list(dict.fromkeys(page["plate"] for page in episode["pages"]))
    with (target / "prompts.jsonl").open("w", encoding="utf-8") as handle:
        for plate_id in used:
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
            handle.write(
                json.dumps(
                    {
                        "plate": plate_id,
                        "prompt": prompt,
                        "aspect_ratio": visual["canvas"],
                        "reference_images": [
                            "assets/references/achi.png",
                            "assets/references/zhoushu.png",
                            "assets/references/achi-zhoushu.png",
                        ],
                        "output_path": f"assets/plates/{plate_id}.png",
                        "reuse_policy": "generate once; all balloons are one local SVG system",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    manifest_pages = []
    for number, page in enumerate(episode["pages"], 1):
        svg = render_page(episode, page, number, theme, visual, art_dir)
        target_path = cards_dir / f"{episode['episode_id']}-{number:02d}.svg"
        target_path.write_text(svg, encoding="utf-8")
        manifest_pages.append(
            {
                "page": number,
                "kind": page["kind"],
                "plate": page["plate"],
                "bubbles": len(page["bubbles"]),
                "has_art": find_art(art_dir, page["plate"]) is not None,
                "card": str(target_path.relative_to(target)),
            }
        )

    (target / "caption.txt").write_text(episode.get("caption", "").strip() + "\n", encoding="utf-8")
    (target / "manifest.json").write_text(
        json.dumps(
            {
                "episode_id": episode["episode_id"],
                "format": "five-card-unified-balloon-v3",
                "font_family": theme["font"]["family"],
                "balloon_style": "soft-tv-standard",
                "pages": manifest_pages,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one five-card SELF_IP episode with one unified professional balloon style.")
    parser.add_argument("episode", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--art-dir", type=Path)
    args = parser.parse_args()
    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    result = build(episode_path, args.out, args.art_dir)
    print(f"Built {result.relative_to(ROOT) if result.is_relative_to(ROOT) else result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
