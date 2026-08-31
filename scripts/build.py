#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import random
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


def overlap_ratio(first: dict[str, float], second: dict[str, float]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["max_h"], second["y"] + second["max_h"])
    if right <= left or bottom <= top:
        return 0.0
    area = (right - left) * (bottom - top)
    smaller = min(first["w"] * first["max_h"], second["w"] * second["max_h"])
    return area / smaller if smaller else 0.0


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
    short_lines = 0
    punctuation_shapes: set[str] = set()
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
        if not 1 <= len(bubbles) <= 2:
            errors.append(f"第 {number} 页必须有 1–2 个对话气泡")
        used_slots: list[dict[str, float]] = []
        for bubble in bubbles:
            speaker = bubble.get("speaker")
            slot_name = bubble.get("slot")
            value = str(bubble.get("text", "")).strip()
            all_copy.append(value)
            if speaker not in SPEAKERS:
                errors.append(f"第 {number} 页 speaker 不合法")
            if slot_name not in plate["slots"]:
                errors.append(f"第 {number} 页气泡位 {slot_name!r} 不存在")
                continue
            slot = plate["slots"][slot_name]
            used_slots.append(slot)
            if not value:
                errors.append(f"第 {number} 页有空气泡")
            if visual_units(value) > (42 if kind == "cover" else 38):
                errors.append(f"第 {number} 页单个气泡文字过长")
            if visual_units(value) <= 8:
                short_lines += 1
            punctuation_shapes.add(value[-1:] if value else "")
            mouth = plate["mouths"].get(speaker)
            if mouth:
                mx, my = mouth
                if slot["x"] < mx < slot["x"] + slot["w"] and slot["y"] < my < slot["y"] + slot["max_h"]:
                    errors.append(f"第 {number} 页 {speaker} 的气泡盖住嘴部锚点")
                center_x = slot["x"] + slot["w"] / 2
                center_y = slot["y"] + slot["max_h"] / 2
                if math.dist((center_x, center_y), (mx, my)) > 770:
                    errors.append(f"第 {number} 页 {speaker} 的气泡离嘴太远")
        if len(used_slots) == 2 and overlap_ratio(used_slots[0], used_slots[1]) > 0.18:
            errors.append(f"第 {number} 页两个气泡重叠过多")
        if kind == "action" and not any("？" in bubble.get("text", "") or "吗" in bubble.get("text", "") for bubble in bubbles):
            errors.append("action 页必须包含现实中能直接说出口的具体请求")
        if kind == "landing":
            for key in ("caption", "note", "question"):
                value = str(page.get(key, "")).strip()
                all_copy.append(value)
                if not value:
                    errors.append(f"结尾页缺少 {key}")
            if visual_units(str(page.get("note", ""))) > 20:
                errors.append("结尾小道理太长")

    joined = "\n".join(all_copy)
    for phrase in BANNED:
        if phrase in joined:
            errors.append(f"出现空泛或机器腔表达：{phrase}")
    if short_lines == 0:
        errors.append("全篇缺少一句短回应，节奏过于整齐")
    if len(punctuation_shapes - {""}) < 2:
        errors.append("所有句子收尾过于一致")
    if "……" not in joined and "——" not in joined:
        errors.append("样稿缺少一次停顿或自我修正，口语节奏过平")
    if not any(word in joined for word in ("面", "筷子", "手机", "门", "雨", "杯", "鞋", "包")):
        errors.append("全篇缺少能落到画面里的具体物件")
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
        stroke = f' stroke="{color}" stroke-width="{stroke_width:.2f}" paint-order="stroke fill" stroke-linejoin="round"'
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
    return f'<image href="data:{mime};base64,{encoded}" x="0" y="0" width="1080" height="1440" preserveAspectRatio="xMidYMid slice"/>'


def proof_art(plate: dict[str, Any], theme: dict[str, Any]) -> str:
    colors = theme["colors"]
    font = theme["font"]["family"]
    a = plate["mouths"]["阿迟"]
    z = plate["mouths"]["周叔"]
    return "\n".join(
        [
            f'<ellipse cx="{a[0]}" cy="1010" rx="190" ry="270" fill="{colors["sky"]}" opacity="0.48"/>',
            f'<circle cx="{a[0]}" cy="780" r="98" fill="#F4C7A7" opacity="0.72"/>',
            f'<path d="M {a[0]-115} 815 Q {a[0]} 690 {a[0]+115} 815" fill="none" stroke="{colors["sky_line"]}" stroke-width="9" opacity="0.55"/>',
            f'<ellipse cx="{z[0]}" cy="1010" rx="205" ry="275" fill="{colors["butter"]}" opacity="0.52"/>',
            f'<circle cx="{z[0]}" cy="780" r="102" fill="#E8B997" opacity="0.72"/>',
            f'<path d="M {z[0]-120} 815 Q {z[0]} 690 {z[0]+120} 815" fill="none" stroke="{colors["butter_line"]}" stroke-width="9" opacity="0.55"/>',
            svg_text(["阿迟"], a[0], 1115, 28, colors["sky_line"], font, 600, 1.0, anchor="middle"),
            svg_text(["周叔"], z[0], 1115, 28, colors["butter_line"], font, 600, 1.0, anchor="middle"),
        ]
    )


def irregular_bubble_path(x: float, y: float, w: float, h: float, seed: int) -> str:
    rng = random.Random(seed)
    top = [(x + 30, y + rng.uniform(-3, 3)), (x + w * 0.35, y + rng.uniform(-6, 1)), (x + w - 34, y + rng.uniform(-2, 5))]
    right = [(x + w + rng.uniform(-2, 5), y + 34), (x + w + rng.uniform(-4, 3), y + h * 0.55), (x + w + rng.uniform(-2, 3), y + h - 30)]
    bottom = [(x + w - 34, y + h + rng.uniform(-3, 4)), (x + w * 0.55, y + h + rng.uniform(-2, 6)), (x + 30, y + h + rng.uniform(-4, 3))]
    left = [(x + rng.uniform(-4, 3), y + h - 32), (x + rng.uniform(-3, 4), y + h * 0.46), (x + rng.uniform(-2, 4), y + 30)]
    return (
        f"M {top[0][0]:.1f},{top[0][1]:.1f} "
        f"C {top[1][0]-80:.1f},{top[1][1]:.1f} {top[1][0]+80:.1f},{top[1][1]:.1f} {top[2][0]:.1f},{top[2][1]:.1f} "
        f"Q {x+w:.1f},{y:.1f} {right[0][0]:.1f},{right[0][1]:.1f} "
        f"C {right[1][0]:.1f},{right[1][1]-60:.1f} {right[1][0]:.1f},{right[1][1]+60:.1f} {right[2][0]:.1f},{right[2][1]:.1f} "
        f"Q {x+w:.1f},{y+h:.1f} {bottom[0][0]:.1f},{bottom[0][1]:.1f} "
        f"C {bottom[1][0]+90:.1f},{bottom[1][1]:.1f} {bottom[1][0]-90:.1f},{bottom[1][1]:.1f} {bottom[2][0]:.1f},{bottom[2][1]:.1f} "
        f"Q {x:.1f},{y+h:.1f} {left[0][0]:.1f},{left[0][1]:.1f} "
        f"C {left[1][0]:.1f},{left[1][1]+55:.1f} {left[1][0]:.1f},{left[1][1]-55:.1f} {left[2][0]:.1f},{left[2][1]:.1f} "
        f"Q {x:.1f},{y:.1f} {top[0][0]:.1f},{top[0][1]:.1f} Z"
    )


def tail_path(x: float, y: float, w: float, h: float, target: tuple[float, float]) -> str:
    """Draw a soft curved pointer that stops just before the speaker's mouth."""
    tx, ty = target
    cx, cy = x + w / 2, y + h / 2
    dx, dy = tx - cx, ty - cy
    distance = max(1.0, math.hypot(dx, dy))
    tip_x = tx - dx / distance * 18
    tip_y = ty - dy / distance * 18

    if abs(dx / max(w, 1)) > abs(dy / max(h, 1)):
        attach_y = min(max(ty, y + 42), y + h - 42)
        if dx > 0:
            ax = x + w - 2
            return (
                f"M {ax-3:.1f},{attach_y-17:.1f} "
                f"C {ax+34:.1f},{attach_y-8:.1f} {tip_x-38:.1f},{tip_y-22:.1f} {tip_x:.1f},{tip_y:.1f} "
                f"C {tip_x-35:.1f},{tip_y+18:.1f} {ax+26:.1f},{attach_y+10:.1f} {ax-3:.1f},{attach_y+17:.1f} Z"
            )
        ax = x + 2
        return (
            f"M {ax+3:.1f},{attach_y-17:.1f} "
            f"C {ax-34:.1f},{attach_y-8:.1f} {tip_x+38:.1f},{tip_y-22:.1f} {tip_x:.1f},{tip_y:.1f} "
            f"C {tip_x+35:.1f},{tip_y+18:.1f} {ax-26:.1f},{attach_y+10:.1f} {ax+3:.1f},{attach_y+17:.1f} Z"
        )

    attach_x = min(max(tx, x + 55), x + w - 55)
    if dy >= 0:
        ay = y + h - 2
        bend = 24 if tip_x >= attach_x else -24
        return (
            f"M {attach_x-18:.1f},{ay-3:.1f} "
            f"C {attach_x+bend-5:.1f},{ay+30:.1f} {tip_x+bend:.1f},{tip_y-42:.1f} {tip_x:.1f},{tip_y:.1f} "
            f"C {tip_x-bend*.35:.1f},{tip_y-34:.1f} {attach_x-bend-4:.1f},{ay+24:.1f} {attach_x+20:.1f},{ay-3:.1f} Z"
        )
    ay = y + 2
    bend = 24 if tip_x >= attach_x else -24
    return (
        f"M {attach_x-18:.1f},{ay+3:.1f} "
        f"C {attach_x+bend-5:.1f},{ay-30:.1f} {tip_x+bend:.1f},{tip_y+42:.1f} {tip_x:.1f},{tip_y:.1f} "
        f"C {tip_x-bend*.35:.1f},{tip_y+34:.1f} {attach_x-bend-4:.1f},{ay-24:.1f} {attach_x+20:.1f},{ay+3:.1f} Z"
    )


def bubble_palette(speaker: str, theme: dict[str, Any], emphasis: bool) -> tuple[str, str, str]:
    colors = theme["colors"]
    if emphasis:
        return colors["cream"], colors["coral"], colors["coral"]
    if speaker == "阿迟":
        return colors["sky"], colors["sky_line"], colors["sky_line"]
    return colors["butter"], colors["butter_line"], colors["butter_line"]


def prepare_bubble(
    bubble: dict[str, Any],
    slot: dict[str, float],
    mouth: tuple[float, float],
    theme: dict[str, Any],
    seed: int,
    kind: str,
) -> dict[str, Any]:
    speaker = bubble["speaker"]
    emphasis = bool(bubble.get("emphasis"))
    fill, stroke, label_color = bubble_palette(speaker, theme, emphasis)
    type_spec = theme["type"]
    font_spec = theme["font"]
    size = type_spec["cover_size"] if kind == "cover" else type_spec["bubble_size"]
    if slot["w"] < 390:
        size = type_spec["bubble_small_size"]
    max_units = max(7.5, (slot["w"] - 70) / (size * 0.98))
    lines = wrap_text(bubble["text"], max_units)
    label_h = 29 if kind != "cover" else 0
    padding_top = 40 if kind == "cover" else 31
    line_h = size * type_spec["line_height"]
    height = padding_top + label_h + len(lines) * line_h + 28
    while height > slot["max_h"] and size > 33:
        size -= 2
        max_units = max(7.5, (slot["w"] - 70) / (size * 0.98))
        lines = wrap_text(bubble["text"], max_units)
        line_h = size * type_spec["line_height"]
        height = padding_top + label_h + len(lines) * line_h + 28
    height = min(height, slot["max_h"])
    x, y, w = slot["x"], slot["y"], slot["w"]
    return {
        "speaker": speaker,
        "emphasis": emphasis,
        "fill": fill,
        "stroke": stroke,
        "label_color": label_color,
        "font": font_spec["family"],
        "font_spec": font_spec,
        "type_spec": type_spec,
        "size": size,
        "lines": lines,
        "label_h": label_h,
        "padding_top": padding_top,
        "line_h": line_h,
        "height": height,
        "x": x,
        "y": y,
        "w": w,
        "path": irregular_bubble_path(x, y, w, height, seed),
        "tail": tail_path(x, y, w, height, mouth),
        "mouth": mouth,
        "kind": kind,
    }


def render_bubble_tail(layout: dict[str, Any]) -> str:
    shadow_color = layout["stroke"]
    return "\n".join(
        [
            f'<g class="speech-tail" data-speaker="{html.escape(layout["speaker"])}" data-tail-target="{layout["mouth"][0]},{layout["mouth"][1]}">',
            f'<path d="{layout["tail"]}" fill="{shadow_color}" opacity="0.12" transform="translate(5 6)"/>',
            f'<path d="{layout["tail"]}" fill="{layout["fill"]}" stroke="{layout["stroke"]}" stroke-width="2.8" stroke-linejoin="round"/>',
            "</g>",
        ]
    )


def render_bubble_body(layout: dict[str, Any], theme: dict[str, Any]) -> str:
    speaker = layout["speaker"]
    x, y, w, height = layout["x"], layout["y"], layout["w"], layout["height"]
    font_spec = layout["font_spec"]
    font = layout["font"]
    emphasis = layout["emphasis"]
    shadow_color = theme["colors"]["coral"] if emphasis else layout["stroke"]
    parts = [
        f'<g class="speech-bubble" data-speaker="{html.escape(speaker)}">',
        f'<path d="{layout["path"]}" fill="{shadow_color}" opacity="0.12" transform="translate(6 7)"/>',
        f'<path d="{layout["path"]}" fill="{layout["fill"]}" stroke="{layout["stroke"]}" stroke-width="2.8" stroke-linejoin="round"/>',
        f'<path d="{layout["path"]}" fill="none" stroke="{layout["stroke"]}" stroke-width="1.0" opacity="0.28" transform="translate(2 -2)"/>',
    ]
    text_y = y + layout["padding_top"]
    if layout["kind"] != "cover":
        parts.append(
            svg_text(
                [speaker],
                x + 34,
                text_y,
                21,
                layout["label_color"],
                font,
                font_spec["label_weight"],
                1.0,
                font_spec["synthetic_stroke"] * 0.5,
                letter_spacing=0.4,
            )
        )
        text_y += layout["label_h"] + 15 + layout["size"] * 0.78
    else:
        text_y += layout["size"] * 0.78
    parts.append(
        svg_text(
            layout["lines"],
            x + 34,
            text_y,
            layout["size"],
            theme["colors"]["ink"],
            font,
            font_spec["display_weight"] if emphasis else font_spec["body_weight"],
            layout["type_spec"]["line_height"],
            font_spec["synthetic_stroke"],
        )
    )
    if emphasis:
        underline_y = y + height - 22
        parts.append(
            f'<path d="M {x+38:.1f},{underline_y:.1f} Q {x+w*0.36:.1f},{underline_y+7:.1f} {x+w*0.67:.1f},{underline_y+1:.1f}" '
            f'fill="none" stroke="{theme["colors"]["coral"]}" stroke-width="5.5" stroke-linecap="round" opacity="0.76"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def caption_sticker(value: str, slot: dict[str, float], theme: dict[str, Any], seed: int) -> str:
    font = theme["font"]["family"]
    color = theme["colors"]["lavender_line"]
    fill = theme["colors"]["lavender"]
    x, y, w = slot["x"], slot["y"], slot["w"]
    lines = wrap_text(value, 22)
    h = min(slot["max_h"], 44 + len(lines) * 36)
    path = irregular_bubble_path(x, y, w, h, seed)
    return "\n".join(
        [
            f'<g class="caption-sticker"><path d="{path}" fill="{fill}" stroke="{color}" stroke-width="2.5" stroke-dasharray="8 5"/>',
            svg_text(lines, x + w / 2, y + 42, theme["type"]["caption_size"], color, font, 600, 1.18, 0.2, anchor="middle"),
            "</g>",
        ]
    )


def doodles(page_number: int, theme: dict[str, Any]) -> str:
    c = theme["colors"]
    if page_number % 3 == 1:
        return "\n".join(
            [
                f'<path d="M 934 104 q 25 -22 45 2 q -12 20 -35 16" fill="none" stroke="{c["mint_line"]}" stroke-width="5" stroke-linecap="round"/>',
                f'<circle cx="970" cy="145" r="7" fill="{c["coral"]}" opacity="0.8"/>',
                f'<circle cx="997" cy="128" r="4" fill="{c["sky_line"]}" opacity="0.7"/>',
            ]
        )
    if page_number % 3 == 2:
        return "\n".join(
            [
                f'<path d="M 83 118 q 22 -18 42 0 q -12 18 -31 12" fill="none" stroke="{c["coral"]}" stroke-width="5" stroke-linecap="round"/>',
                f'<path d="M 945 122 l 9 18 18 9-18 9-9 18-9-18-18-9 18-9z" fill="{c["butter"]}" stroke="{c["butter_line"]}" stroke-width="2" opacity="0.85"/>',
            ]
        )
    return "\n".join(
        [
            f'<path d="M 90 118 q 18 -16 36 0 q -9 18 -28 15" fill="none" stroke="{c["mint_line"]}" stroke-width="5" stroke-linecap="round"/>',
            f'<path d="M 961 112 q 22 18 0 38 q -22 -18 0 -38" fill="{c["sky"]}" stroke="{c["sky_line"]}" stroke-width="2.5" opacity="0.8"/>',
        ]
    )


def page_mark(page_number: int, theme: dict[str, Any]) -> str:
    c = theme["colors"]
    marks = []
    start = 450
    for index in range(1, 6):
        x = start + (index - 1) * 36
        if index == page_number:
            marks.append(f'<path d="M {x-8} 1370 q 8 -11 17 0 q -8 12 -17 0" fill="{c["coral"]}"/>')
        else:
            marks.append(f'<circle cx="{x}" cy="1370" r="4.5" fill="{c["proof"]}"/>')
    return "\n".join(marks)


def render_page(
    episode: dict[str, Any],
    page: dict[str, Any],
    page_number: int,
    theme: dict[str, Any],
    visual: dict[str, Any],
    art_dir: Path,
) -> str:
    colors = theme["colors"]
    font = theme["font"]["family"]
    plate = visual["plates"][page["plate"]]
    art_path = find_art(art_dir, page["plate"])
    bubble_layouts = []
    for index, bubble in enumerate(page["bubbles"], 1):
        slot = plate["slots"][bubble["slot"]]
        mouth = tuple(plate["mouths"][bubble["speaker"]])
        bubble_layouts.append(prepare_bubble(bubble, slot, mouth, theme, page_number * 100 + index, page["kind"]))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">',
        f'<rect width="1080" height="1440" fill="{colors["paper"]}"/>',
        '<defs><filter id="paper"><feTurbulence type="fractalNoise" baseFrequency="0.32" numOctaves="2" seed="7"/><feColorMatrix values="0 0 0 0 0.55  0 0 0 0 0.50  0 0 0 0 0.40  0 0 0 .055 0"/></filter></defs>',
        '<rect width="1080" height="1440" filter="url(#paper)" opacity="0.42"/>',
        f'<ellipse cx="220" cy="510" rx="250" ry="360" fill="{colors["sky"]}" opacity="0.12"/>',
        f'<ellipse cx="900" cy="610" rx="260" ry="390" fill="{colors["butter"]}" opacity="0.12"/>',
    ]
    parts.extend(render_bubble_tail(layout) for layout in bubble_layouts)
    parts.append(embedded_art(art_path) if art_path else proof_art(plate, theme))
    parts.extend(
        [
            doodles(page_number, theme),
            svg_text(["坐一会儿再走"], 62, 68, theme["type"]["brand_size"], colors["muted"], font, 600, 1.0, 0.15),
            f'<path d="M 62 88 q 34 7 74 -2" fill="none" stroke="{colors["coral"]}" stroke-width="5" stroke-linecap="round"/>',
        ]
    )

    if page.get("caption"):
        parts.append(caption_sticker(page["caption"], plate["slots"]["caption"], theme, 900 + page_number))

    parts.extend(render_bubble_body(layout, theme) for layout in bubble_layouts)

    if page.get("kicker"):
        parts.append(svg_text([page["kicker"]], 68, 1290, 30, colors["mint_line"], font, 600, 1.0, 0.18))
        parts.append(
            f'<path d="M 69 1310 q 120 16 255 -3" fill="none" stroke="{colors["mint_line"]}" stroke-width="4" stroke-linecap="round" opacity="0.65"/>'
        )
    if page.get("note"):
        note_lines = wrap_text(page["note"], 16)
        parts.append(
            f'<path d="M 62 1168 q 115 -20 240 3 q 135 22 282 -4" fill="none" stroke="{colors["coral"]}" stroke-width="5" stroke-linecap="round" opacity="0.72"/>'
        )
        parts.append(svg_text(note_lines, 65, 1225, theme["type"]["note_size"], colors["ink"], font, 700, 1.18, 0.22))
    if page.get("question"):
        parts.append(svg_text([page["question"]], 65, 1330, theme["type"]["question_size"], colors["muted"], font, 600, 1.0, 0.12))
    if page_number == 5:
        parts.append(svg_text([episode.get("source", "")], 1015, 1390, 17, colors["muted"], font, 500, 1.0, anchor="end"))
    parts.append(page_mark(page_number, theme))
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
                        "reuse_policy": "generate once, reuse across episodes; dialogue balloons are local SVG overlays",
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
                "format": "five-card-mouth-anchored-bubbles-v2",
                "font_family": theme["font"]["family"],
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
    parser = argparse.ArgumentParser(description="Build one five-card SELF_IP episode with mouth-anchored dialogue balloons.")
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
