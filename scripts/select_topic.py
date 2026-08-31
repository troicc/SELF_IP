#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import ROOT, dump_json, read_topics


def main() -> int:
    parser = argparse.ArgumentParser(description="Select one topic-bank row into a work brief.")
    parser.add_argument("--topic", required=True, help="Topic id such as T001.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    matches = [row for row in read_topics() if row["topic_id"] == args.topic]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one topic {args.topic}, found {len(matches)}")
    row = matches[0]
    out = args.out or ROOT / "build" / "work" / args.topic / "topic.json"
    if not out.is_absolute():
        out = ROOT / out
    dump_json(
        out,
        {
            "selected_topic": row,
            "next_contract": "Create or choose one seven-page episode, then pass scripts/quality_gate.py pre.",
            "source_declaration_required": row["source"],
        },
    )
    print(f"Selected {args.topic}: {row['working_title']}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
