#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ROOT, compile_benchmark_requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the 12 × 3 standardized benchmark prompt matrix.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "build" / "benchmarks" / "requests.jsonl",
        help="Output JSONL path.",
    )
    args = parser.parse_args()

    requests = compile_benchmark_requests()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for request in requests:
            handle.write(json.dumps(request, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    ready = sum(1 for item in requests if item["ready_for_generation"])
    print(f"Wrote {len(requests)} standardized requests to {args.out}")
    print(f"Ready for generation: {ready}/{len(requests)}")
    if ready != len(requests):
        print("Expected in phase one: add candidate identity-only cast sheets before running image generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

