#!/usr/bin/env python3
from __future__ import annotations

import argparse, base64, html, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATES = {"quiet", "achi-talk", "zhoushu-talk", "together"}
SPEAKERS = {"阿迟", "周叔", "旁白"}
BANNED = ("高敏感人格", "回避型", "真正爱你的人", "你应该学会", "建立边界感", "情绪价值")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def units(text: str) -> float:
    return sum(.55 if ord(c) < 128 else 1 for c in text.replace("\n", ""))


def wrap(text: str, limit: float) -> list[str]:
    if "\n" in text:
        return [line for part in text.splitlines() for line in wrap(part, limit)]
    result, line, width = [], "", 0.0
    for c in text.strip():
        w = .55 if ord(c) < 128 else 1
        if line and width + w > limit:
            result.append(line); line, width = "", 0.0
        line += c; width += w
    return result + ([line] if line else [])


def validate(ep: dict) -> None:
    pages = ep.get("pages", [])
    errors = []
    if len(pages) != 5: errors.append("必须正好五页")
    if pages and pages[0].get("kind") != "cover": errors.append("第一页必须是 cover")
    if pages and pages[-1].get("kind") != "landing": errors.append("第五页必须是 landing")
    if sum(p.get("kind") == "action" for p in pages) != 1: errors.append("必须正好有一页 action")
    all_copy = []
    for n, page in enumerate(pages, 1):
        if page.get("plate") not in PLATES: errors.append(f"第 {n} 页镜头不合法")
        if page.get("kind") in {"dialogue", "action"}:
            lines = page.get("lines", [])
            if not 1 <= len(lines) <= 2: errors.append(f"第 {n} 页只能有 1–2 个文本块")
            for item in lines:
                text_value = str(item.get("text", "")).strip(); all_copy.append(text_value)
                if item.get("speaker") not in SPEAKERS: errors.append(f"第 {n} 页人物名不合法")
                if units(text_value) > 34: errors.append(f"第 {n} 页单段超过 34 个视觉字符")
        else:
            all_copy.extend(str(page.get(k, "")) for k in ("text", "story", "takeaway", "question"))
    joined = "\n".join(all_copy)
    errors.extend(f"出现空泛表达：{word}" for word in BANNED if word in joined)
    if errors: raise ValueError("剧集校验失败：\n- " + "\n- ".join(errors))


def svg_text(lines, x, y, size, color, font, weight=400, leading=1.25, anchor="start") -> str:
    rows = [f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-family="{html.escape(font, quote=True)}" font-weight="{weight}" text-anchor="{anchor}">']
    for i, line in enumerate(lines):
        rows.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * leading:.1f}">{html.escape(line)}</tspan>')
    return "\n".join(rows + ["</text>"])


def find_art(plate: str) -> Path | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        path = ROOT / "assets" / "plates" / f"{plate}.{ext}"
        if path.is_file(): return path
    return None


def art(path: Path | None, plate: str, x: int, y: int, w: int, h: int, theme: dict) -> str:
    if path:
        mime = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp"}[path.suffix.lower()]
        data = base64.b64encode(path.read_bytes()).decode()
        return f'<image href="data:{mime};base64,{data}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet"/>'
    pale, font = theme["colors"]["proof"], theme["font_family"]
    return "\n".join([
        f'<line x1="{x+80}" y1="{y+h//2}" x2="{x+w-80}" y2="{y+h//2}" stroke="{pale}" stroke-width="2" stroke-dasharray="9 13"/>',
        svg_text([f"{plate} · 插画占位，不作为成品"], x+w//2, y+h//2-24, 22, pale, font, anchor="middle")
    ])


def dots(page: int, colors: dict) -> str:
    return "\n".join(f'<circle cx="{486+(i-1)*27}" cy="1370" r="{7 if i==page else 4}" fill="{colors["accent"] if i==page else colors["proof"]}"/>' for i in range(1, 6))


def render(ep: dict, page: dict, number: int, theme: dict) -> str:
    c, font = theme["colors"], theme["font_family"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">', f'<rect width="1080" height="1440" fill="{c["paper"]}"/>', svg_text(["坐一会儿再走"], 76, 70, 22, c["muted"], font, 500), f'<line x1="76" y1="94" x2="154" y2="94" stroke="{c["accent"]}" stroke-width="5" stroke-linecap="round"/>']
    image = find_art(page["plate"])
    kind = page["kind"]
    if kind == "cover":
        out += [svg_text(wrap(page["text"], 12), 76, 190, 72, c["ink"], font, 700, 1.18), art(image, page["plate"], 54, 410, 972, 780, theme), svg_text(["阿迟 × 周叔"], 76, 1280, 27, c["muted"], font, 500)]
    elif kind in {"dialogue", "action"}:
        out.append(art(image, page["plate"], 70, 115, 940, 690, theme)); y = 880
        for item in page["lines"]:
            who = item["speaker"]; color = c["achi"] if who == "阿迟" else c["zhoushu"] if who == "周叔" else c["muted"]
            copy = wrap(item["text"], 18); emphasize = kind == "action" and who == "阿迟"
            out += [svg_text([who], 78, y, 23, color, font, 700), f'<line x1="78" y1="{y+20}" x2="130" y2="{y+20}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>']
            x = 112 if emphasize else 78
            if emphasize: out.append(f'<line x1="78" y1="{y+54}" x2="78" y2="{y+54+len(copy)*66}" stroke="{c["accent"]}" stroke-width="6" stroke-linecap="round"/>')
            out.append(svg_text(copy, x, y+75, 49, c["ink"], font, 700 if emphasize else 500, 1.28)); y += 92 + len(copy)*63
    else:
        out += [art(image, page["plate"], 95, 110, 890, 520, theme), svg_text(wrap(page["story"], 19), 78, 730, 40, c["muted"], font, 400, 1.35)]
        take = wrap(page["takeaway"], 10)
        out += [svg_text(take, 78, 980, 64, c["ink"], font, 700, 1.22), f'<line x1="78" y1="{992+len(take)*78}" x2="265" y2="{992+len(take)*78}" stroke="{c["accent"]}" stroke-width="7" stroke-linecap="round"/>', svg_text(wrap(page["question"], 21), 78, 1260, 31, c["muted"], font, 500, 1.32), svg_text([ep.get("source", "")], 1004, 1374, 16, c["muted"], font, 400, anchor="end")]
    return "\n".join(out + [dots(number, c), "</svg>"]) + "\n"


def build(source: Path) -> Path:
    ep, theme, visual = read_json(source), read_json(ROOT/"templates/theme.json"), read_json(ROOT/"visual/plates.json")
    validate(ep); target = ROOT/"build"/ep["episode_id"]; cards = target/"cards"; cards.mkdir(parents=True, exist_ok=True)
    used = dict.fromkeys(p["plate"] for p in ep["pages"])
    with (target/"prompts.jsonl").open("w", encoding="utf-8") as f:
        for plate in used:
            spec = visual["plates"][plate]
            prompt = ". ".join((visual["style"], "Characters: "+"; ".join(visual["identity"][x] for x in spec["characters"]), "Composition: "+spec["direction"], "Background: "+visual["background"], "Hard exclusions: "+visual["global_negative"])) + "."
            f.write(json.dumps({"plate":plate,"prompt":prompt,"aspect_ratio":visual["canvas"],"references":["assets/references/achi.png","assets/references/zhoushu.png","assets/references/achi-zhoushu.png"],"output_path":f"assets/plates/{plate}.png","reuse":"generate once"}, ensure_ascii=False)+"\n")
    for n, page in enumerate(ep["pages"], 1): (cards/f'{ep["episode_id"]}-{n:02d}.svg').write_text(render(ep, page, n, theme), encoding="utf-8")
    (target/"caption.txt").write_text(ep.get("caption", "").strip()+"\n", encoding="utf-8")
    (target/"manifest.json").write_text(json.dumps({"episode_id":ep["episode_id"],"format":"five-card-fixed-plate-v1","cards":5}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("episode", type=Path); args = parser.parse_args()
    path = args.episode if args.episode.is_absolute() else ROOT/args.episode
    print(f"Built {build(path).relative_to(ROOT)}")
