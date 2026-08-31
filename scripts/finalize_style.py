#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import ROOT, current_vendor_commit, dump_json, load_json, sha256_file


METRICS = [
    "character_consistency",
    "emotional_expression",
    "whitespace",
    "interaction_naturalness",
    "distinctiveness",
]
WEIGHTS = {
    "character_consistency": 0.25,
    "emotional_expression": 0.20,
    "whitespace": 0.15,
    "interaction_naturalness": 0.15,
    "generation_success_rate": 0.15,
    "distinctiveness": 0.10,
}


def _score(value: str, field: str, row_label: str) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{row_label}: missing or invalid score {field}") from None
    if score < 1 or score > 5:
        raise ValueError(f"{row_label}: {field} must be between 1 and 5")
    return score


def _flag(value: str | None, field: str, row_label: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{row_label}: {field} must be true or false")


def evaluate_scorecard(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected = {(f"B{number:02d}", style) for number in range(1, 13) for style in ("10", "14", "18")}
    actual = {(row.get("scene_id"), row.get("style_id")) for row in rows}
    if len(rows) != 36 or actual != expected:
        raise ValueError("scorecard must contain exactly the 36 expected scene-style rows")

    units: dict[str, list[dict[str, Any]]] = {"10": [], "14": [], "18": []}
    for row in rows:
        label = f"{row['scene_id']}/style-{row['style_id']}"
        try:
            attempts = int(row["attempt_count"])
            successes = int(row["successful_count"])
        except (TypeError, ValueError):
            raise ValueError(f"{label}: attempt_count and successful_count must be integers") from None
        if attempts < 3:
            raise ValueError(f"{label}: at least three independent attempts are required")
        if successes < 0 or successes > attempts:
            raise ValueError(f"{label}: successful_count must be between zero and attempt_count")
        e1 = row.get("e1_name", "").strip()
        e2 = row.get("e2_name", "").strip()
        if not e1 or not e2 or e1 == e2:
            raise ValueError(f"{label}: two different named evaluators are required")

        synthetic_polish_flags = {
            "e1": _flag(row.get("e1_synthetic_polish_flag"), "e1_synthetic_polish_flag", label),
            "e2": _flag(row.get("e2_synthetic_polish_flag"), "e2_synthetic_polish_flag", label),
        }
        if any(synthetic_polish_flags.values()) and not row.get("notes", "").strip():
            raise ValueError(f"{label}: synthetic polish flag needs visible-evidence notes")

        averages: dict[str, float] = {}
        disagreements: dict[str, float] = {}
        for metric in METRICS:
            first = _score(row.get(f"e1_{metric}", ""), f"e1_{metric}", label)
            second = _score(row.get(f"e2_{metric}", ""), f"e2_{metric}", label)
            disagreement = abs(first - second)
            if disagreement > 1.5 and not row.get("notes", "").strip():
                raise ValueError(f"{label}: {metric} differs by more than 1.5 and needs review notes")
            averages[metric] = (first + second) / 2
            disagreements[metric] = disagreement
        success_score = 5 * successes / attempts
        unit_score = sum(averages[name] * WEIGHTS[name] for name in METRICS)
        unit_score += success_score * WEIGHTS["generation_success_rate"]
        units[row["style_id"]].append(
            {
                "scene_id": row["scene_id"],
                "attempt_count": attempts,
                "successful_count": successes,
                "generation_success_rate": success_score,
                "metrics": averages,
                "disagreements": disagreements,
                "synthetic_polish_flags": synthetic_polish_flags,
                "synthetic_polish_consensus": all(synthetic_polish_flags.values()),
                "unit_score": unit_score,
            }
        )

    summaries: dict[str, Any] = {}
    for style_id, style_units in units.items():
        metric_means = {
            metric: statistics.fmean(unit["metrics"][metric] for unit in style_units) for metric in METRICS
        }
        metric_means["generation_success_rate"] = statistics.fmean(
            unit["generation_success_rate"] for unit in style_units
        )
        totals = [unit["unit_score"] for unit in style_units]
        hard_failures: list[str] = []
        if metric_means["character_consistency"] < 3.5:
            hard_failures.append("character_consistency_below_3.5")
        if metric_means["generation_success_rate"] < 3.5:
            hard_failures.append("generation_success_rate_below_3.5")
        whitespace_failures = sum(1 for unit in style_units if unit["metrics"]["whitespace"] < 3.0)
        if whitespace_failures >= 3:
            hard_failures.append("reserved_text_region_failures_in_three_or_more_scenes")
        synthetic_polish_failures = sum(1 for unit in style_units if unit["synthetic_polish_consensus"])
        if synthetic_polish_failures >= 3:
            hard_failures.append("synthetic_polish_consensus_in_three_or_more_scenes")
        summaries[style_id] = {
            "eligible": not hard_failures,
            "hard_failures": hard_failures,
            "weighted_total": statistics.fmean(totals),
            "unit_score_stdev": statistics.pstdev(totals),
            "metric_means": metric_means,
            "lowest_scene": min(style_units, key=lambda item: item["unit_score"])["scene_id"],
            "attempt_count": sum(unit["attempt_count"] for unit in style_units),
            "successful_count": sum(unit["successful_count"] for unit in style_units),
            "synthetic_polish_consensus_count": synthetic_polish_failures,
        }

    eligible = sorted(
        ((style, summary) for style, summary in summaries.items() if summary["eligible"]),
        key=lambda pair: pair[1]["weighted_total"],
        reverse=True,
    )
    if not eligible:
        raise ValueError("no candidate passed the hard gates")
    if len(eligible) > 1 and eligible[0][1]["weighted_total"] - eligible[1][1]["weighted_total"] <= 0.15:
        raise ValueError("top candidates are tied within 0.15; run a second blind 12-scene round")
    return {"winner": eligible[0][0], "summaries": summaries}


def _ensure_image(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {resolved}")
    header = resolved.read_bytes()[:12]
    if not (header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff")):
        raise ValueError(f"{label} must be a PNG or JPEG image")
    return resolved


def _copy_without_overwrite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) != sha256_file(destination):
            raise ValueError(f"refusing to overwrite different frozen asset: {destination}")
        return
    shutil.copy2(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Automatically select and freeze dialogue-sketch-v1 after complete scoring.")
    parser.add_argument("--scorecard", type=Path, default=ROOT / "benchmarks" / "scorecard.csv")
    parser.add_argument("--style-anchor", type=Path, required=True)
    parser.add_argument("--achi-ref", type=Path, required=True)
    parser.add_argument("--zhoushu-ref", type=Path, required=True)
    parser.add_argument("--qinyi-ref", type=Path, required=True)
    parser.add_argument("--pair-achi-zhoushu", type=Path, required=True)
    parser.add_argument("--pair-achi-qinyi", type=Path, required=True)
    parser.add_argument("--reviewers", required=True, help="Comma-separated evaluator names.")
    args = parser.parse_args()

    result = evaluate_scorecard(args.scorecard)
    winner = result["winner"]
    inputs = {
        "style_anchor": _ensure_image(args.style_anchor, "style anchor"),
        "achi": _ensure_image(args.achi_ref, "Achi reference"),
        "zhoushu": _ensure_image(args.zhoushu_ref, "Uncle Zhou reference"),
        "qinyi": _ensure_image(args.qinyi_ref, "Aunt Qin reference"),
        "pair_achi_zhoushu": _ensure_image(args.pair_achi_zhoushu, "Achi-Uncle Zhou pair sheet"),
        "pair_achi_qinyi": _ensure_image(args.pair_achi_qinyi, "Achi-Aunt Qin pair sheet"),
    }
    if len(set(inputs.values())) != len(inputs):
        raise SystemExit("Style and cast reference inputs must be different files.")
    if len({sha256_file(path) for path in inputs.values()}) != len(inputs):
        raise SystemExit("Style and cast reference inputs must have different file contents.")
    anchor_root = (ROOT / "benchmarks" / "outputs" / f"style-{winner}").resolve()
    try:
        inputs["style_anchor"].relative_to(anchor_root)
    except ValueError:
        raise SystemExit(f"Winning style anchor must come from {anchor_root}") from None

    destinations = {
        "style_anchor": ROOT / "assets" / "dialogue-sketch-v1" / "style-anchor.png",
        "achi": ROOT / "assets" / "dialogue-sketch-v1" / "cast" / "achi.png",
        "zhoushu": ROOT / "assets" / "dialogue-sketch-v1" / "cast" / "zhoushu.png",
        "qinyi": ROOT / "assets" / "dialogue-sketch-v1" / "cast" / "qinyi.png",
        "pair_achi_zhoushu": ROOT / "assets" / "dialogue-sketch-v1" / "cast" / "pair-achi-zhoushu.png",
        "pair_achi_qinyi": ROOT / "assets" / "dialogue-sketch-v1" / "cast" / "pair-achi-qinyi.png",
    }
    for key, destination in destinations.items():
        _copy_without_overwrite(inputs[key], destination)

    reviewers = [item.strip() for item in args.reviewers.split(",") if item.strip()]
    if len(set(reviewers)) < 2:
        raise SystemExit("At least two named reviewers are required.")
    styles = load_json(ROOT / "benchmarks" / "styles.yaml")
    lock = {
        "schema_version": "1.0.0",
        "production_name": "dialogue-sketch-v1",
        "contract_version": "1.0.0",
        "status": "locked",
        "upstream_style_id": winner,
        "upstream_repository": styles["upstream"]["repository"],
        "upstream_commit": current_vendor_commit(),
        "recipe_source": styles["upstream"]["recipe_source"],
        "recipe_overrides_allowed": False,
        "text_rendering": "local-only",
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "reviewers": reviewers,
        "score_summary": result["summaries"],
        "style_reference": {
            "path": str(destinations["style_anchor"].relative_to(ROOT)),
            "role": "style-only",
            "sha256": sha256_file(destinations["style_anchor"]),
        },
        "character_references": {
            key: {
                "path": str(destinations[key].relative_to(ROOT)),
                "role": "identity-only",
                "sha256": sha256_file(destinations[key]),
            }
            for key in ("achi", "zhoushu", "qinyi")
        },
        "pair_references": {
            "achi_zhoushu": {
                "path": str(destinations["pair_achi_zhoushu"].relative_to(ROOT)),
                "role": "identity-only",
                "sha256": sha256_file(destinations["pair_achi_zhoushu"]),
            },
            "achi_qinyi": {
                "path": str(destinations["pair_achi_qinyi"].relative_to(ROOT)),
                "role": "identity-only",
                "sha256": sha256_file(destinations["pair_achi_qinyi"]),
            },
        },
    }
    dump_json(ROOT / "config" / "style-lock.json", lock)
    print(f"Locked dialogue-sketch-v1 to upstream style {winner}")
    print(f"Wrote {ROOT / 'config' / 'style-lock.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
