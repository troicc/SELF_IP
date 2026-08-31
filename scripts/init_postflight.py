#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import POSTFLIGHT_FIELDS, ROOT, dump_json, load_json, validate_episode


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a seven-page postflight QA worksheet.")
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
    episode = load_json(episode_path)
    errors = validate_episode(episode, str(episode_path))
    if errors:
        raise SystemExit("Episode preflight failed; fix it before creating postflight QA.")
    out = args.out or ROOT / "build" / "qa" / f"{episode['episode_id']}.json"
    if not out.is_absolute():
        out = ROOT / out
    pages = []
    for page in range(1, 8):
        item = {"page": page}
        item.update({field: False for field in POSTFLIGHT_FIELDS})
        item["notes"] = ""
        pages.append(item)
    dump_json(
        out,
        {
            "episode_id": episode["episode_id"],
            "reviewer": "",
            "reviewed_at": "",
            "pages": pages,
        },
    )
    print(f"Wrote postflight worksheet to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

