#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import ROOT


CROP_PATTERN = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def detect_foreground_crop(input_path: Path, limit: float = 0.035) -> tuple[int, int, int, int]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loop",
        "1",
        "-i",
        str(input_path),
        "-vf",
        f"format=gray,negate,cropdetect=limit={limit}:round=2:reset=0",
        "-frames:v",
        "10",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    matches = CROP_PATTERN.findall(result.stderr)
    if result.returncode != 0 or not matches:
        raise ValueError(f"could not detect foreground bounds in {input_path}")
    width, height, x, y = (int(value) for value in matches[-1])
    return width, height, x, y


def padded_crop(
    crop: tuple[int, int, int, int],
    canvas: tuple[int, int],
    padding_fraction: float = 0.02,
) -> tuple[int, int, int, int]:
    width, height, x, y = crop
    canvas_width, canvas_height = canvas
    pad_x = round(canvas_width * padding_fraction)
    pad_y = round(canvas_height * padding_fraction)
    left = max(0, x - pad_x)
    top = max(0, y - pad_y)
    right = min(canvas_width, x + width + pad_x)
    bottom = min(canvas_height, y + height + pad_y)
    result_width = right - left
    result_height = bottom - top
    result_width -= result_width % 2
    result_height -= result_height % 2
    return result_width, result_height, left, top


def stage_geometry(
    crop: tuple[int, int, int, int],
    stage: dict[str, float],
    canvas: tuple[int, int] = (1086, 1448),
) -> tuple[int, int, int, int]:
    crop_width, crop_height, _, _ = crop
    canvas_width, canvas_height = canvas
    stage_x = round(stage["x"] * canvas_width)
    stage_y = round(stage["y"] * canvas_height)
    stage_width = round(stage["width"] * canvas_width)
    stage_height = round(stage["height"] * canvas_height)
    scale = min(stage_width / crop_width, stage_height / crop_height)
    target_width = max(2, int(crop_width * scale) // 2 * 2)
    target_height = max(2, int(crop_height * scale) // 2 * 2)
    x = stage_x + (stage_width - target_width) // 2
    y = stage_y + stage_height - target_height
    return target_width, target_height, x, y


def place_image(input_path: Path, output_path: Path, stage: dict[str, float]) -> None:
    if shutil.which("ffmpeg") is None:
        raise ValueError("ffmpeg is required for deterministic illustration placement")
    detected = detect_foreground_crop(input_path)
    crop = padded_crop(detected, (1086, 1448))
    target_width, target_height, x, y = stage_geometry(crop, stage)
    crop_width, crop_height, crop_x, crop_y = crop
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        "[0:v]crop=1086:300:0:0,scale=1086:1448:flags=bicubic[paper];"
        f"[0:v]crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"scale={target_width}:{target_height}:flags=lanczos[illustration];"
        f"[paper][illustration]overlay={x}:{y}:format=auto"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_graph,
        "-frames:v",
        "1",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def _job_map(jobs_path: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    with jobs_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                job = json.loads(line)
                jobs[job["job_id"]] = job
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Place generated illustrations inside deterministic safe stages.")
    parser.add_argument("--job", help="One refinement job id, for example R14-B01-A01.")
    parser.add_argument("--all", action="store_true", help="Compose every generated refinement output.")
    parser.add_argument(
        "--jobs",
        type=Path,
        default=ROOT / "build" / "benchmarks" / "style14-refinement-jobs.jsonl",
    )
    args = parser.parse_args()
    if bool(args.job) == bool(args.all):
        raise SystemExit("Choose exactly one of --job or --all")
    jobs_path = args.jobs if args.jobs.is_absolute() else ROOT / args.jobs
    jobs = _job_map(jobs_path)
    selected = jobs.values() if args.all else [jobs[args.job]]
    completed = 0
    for job in selected:
        input_path = ROOT / job["output_path"]
        output_path = ROOT / job["composed_output_path"]
        if not input_path.is_file():
            if args.all:
                continue
            raise SystemExit(f"missing raw generation: {input_path}")
        place_image(input_path, output_path, job["subject_stage_region"])
        completed += 1
        print(f"Composed {job['job_id']} -> {output_path.relative_to(ROOT)}")
    print(f"Composed {completed} illustration(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
