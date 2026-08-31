#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path

from benchmark_run import validate_run
from common import ROOT, load_json


def expected_counts() -> dict[tuple[str, str], tuple[int, int]]:
    counts: dict[tuple[str, str], tuple[int, int]] = {}
    for number in range(1, 13):
        scene_id = f"B{number:02d}"
        run_path = ROOT / "benchmarks" / "runs" / f"{scene_id}.json"
        if not run_path.is_file():
            raise ValueError(f"missing completed benchmark run: {run_path.relative_to(ROOT)}")
        run = load_json(run_path)
        errors = validate_run(run, verify_files=True)
        if errors:
            raise ValueError(f"{scene_id} run is invalid: {'; '.join(errors)}")
        if run.get("status") not in {"completed_pending_blind_review", "completed"}:
            raise ValueError(f"{scene_id} objective QA is not completed")
        for style_id, unit in run["unit_counts"].items():
            counts[(scene_id, style_id)] = (
                int(unit["attempt_count"]),
                int(unit["successful_count"]),
            )
    return counts


def render_scorecard(path: Path) -> str:
    counts = expected_counts()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames
    if not fieldnames:
        raise ValueError("scorecard header is missing")
    actual = {(row.get("scene_id", ""), row.get("style_id", "")) for row in rows}
    if len(rows) != 36 or actual != set(counts):
        raise ValueError("scorecard must contain exactly the 36 expected scene-style rows")
    for row in rows:
        attempts, successes = counts[(row["scene_id"], row["style_id"])]
        row["attempt_count"] = str(attempts)
        row["successful_count"] = str(successes)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync objective run counts into the blind-review scorecard.")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "benchmarks" / "scorecard.csv")
    parser.add_argument("--check", action="store_true", help="Fail if the scorecard is out of sync; do not write.")
    args = parser.parse_args()
    scorecard = args.scorecard if args.scorecard.is_absolute() else ROOT / args.scorecard
    rendered = render_scorecard(scorecard)
    current = scorecard.read_text(encoding="utf-8")
    if args.check:
        if current != rendered:
            raise SystemExit("scorecard objective counts are out of sync")
        print("Scorecard objective counts are in sync")
        return 0
    scorecard.write_text(rendered, encoding="utf-8", newline="")
    counts = expected_counts()
    for style in ("10", "14", "18"):
        attempts = sum(value[0] for key, value in counts.items() if key[1] == style)
        successes = sum(value[1] for key, value in counts.items() if key[1] == style)
        print(f"style {style}: {successes}/{attempts} objective successes")
    print(f"Updated {scorecard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
