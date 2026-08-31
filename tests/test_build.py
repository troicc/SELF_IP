from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build import (
    ALLOWED_PLATES,
    BANNED_PHRASES,
    ROOT,
    build,
    load_json,
    prompt_for_plate,
    validate_episode,
)


class SimpleBuildTests(unittest.TestCase):
    def test_episode_is_five_pages_and_valid(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.json")
        self.assertEqual(validate_episode(episode), [])
        self.assertEqual(len(episode["pages"]), 5)
        self.assertEqual(
            {page["plate"] for page in episode["pages"]} - ALLOWED_PLATES,
            set(),
        )

    def test_build_has_clean_type_and_no_old_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "EP-001"
            build(
                ROOT / "episodes" / "EP-001.json",
                out_dir=output,
                assets_dir=Path(temp_dir) / "missing-art",
            )
            cards = sorted((output / "cards").glob("*.svg"))
            self.assertEqual(len(cards), 5)
            combined = "\n".join(card.read_text(encoding="utf-8") for card in cards)
            self.assertNotIn('fill-opacity="0.92"', combined)
            self.assertNotIn("01/07", combined)
            self.assertNotIn("<foreignObject", combined)
            self.assertIn("体谅别人", combined)
            self.assertIn("插画占位", combined)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "five-card-fixed-plate-v1")

    def test_prompts_forbid_complex_scenes(self) -> None:
        visual = load_json(ROOT / "visual" / "plates.json")
        prompt = prompt_for_plate("quiet", visual)
        for phrase in (
            "no furniture",
            "no full body",
            "no detailed hands",
            "no extra person",
            "no complex gesture",
        ):
            self.assertIn(phrase, prompt)

    def test_copy_avoids_banned_abstractions(self) -> None:
        raw = (ROOT / "episodes" / "EP-001.json").read_text(encoding="utf-8")
        self.assertFalse(any(phrase in raw for phrase in BANNED_PHRASES))

    def test_rejects_seven_pages(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.json")
        episode["pages"].extend(episode["pages"][:2])
        self.assertIn(
            "episode must contain exactly five pages",
            validate_episode(episode),
        )


if __name__ == "__main__":
    unittest.main()
