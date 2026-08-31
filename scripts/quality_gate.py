#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from common import ROOT, episode_paths, load_json, validate_episode, validate_postflight


def print_result(label: str, errors: list[str]) -> None:
    if errors:
        print(f"FAIL {label}")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"PASS {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pre-generation or post-generation editorial gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre = subparsers.add_parser("pre", help="Validate an episode before image generation.")
    pre.add_argument("--episode", type=Path)
    pre.add_argument("--all", action="store_true")

    post = subparsers.add_parser("post", help="Validate a completed seven-page visual QA record.")
    post.add_argument("--episode", type=Path, required=True)
    post.add_argument("--qa", type=Path, required=True)

    args = parser.parse_args()
    all_errors: list[str] = []
    if args.command == "pre":
        if not args.episode and not args.all:
            parser.error("pre requires --episode PATH or --all")
        paths = episode_paths() if args.all else [args.episode]
        for path in paths:
            resolved = path if path.is_absolute() else ROOT / path
            episode = load_json(resolved)
            errors = validate_episode(episode, str(resolved.relative_to(ROOT)))
            print_result(str(resolved.relative_to(ROOT)), errors)
            all_errors.extend(errors)
    else:
        episode_path = args.episode if args.episode.is_absolute() else ROOT / args.episode
        qa_path = args.qa if args.qa.is_absolute() else ROOT / args.qa
        episode = load_json(episode_path)
        qa = load_json(qa_path)
        errors = validate_episode(episode, str(episode_path.relative_to(ROOT)))
        errors.extend(validate_postflight(episode, qa, str(qa_path.relative_to(ROOT))))
        print_result(str(qa_path.relative_to(ROOT)), errors)
        all_errors.extend(errors)
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
