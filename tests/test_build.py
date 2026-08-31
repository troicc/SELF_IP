from __future__ import annotations

import json
import shutil
import unittest
from unittest.mock import patch

from scripts.build import BANNED, PLATES, ROOT, build, read_json, render, validate, wrap


class BuildTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutil.rmtree(ROOT / "build", ignore_errors=True)

    def test_episode_is_five_pages_and_valid(self) -> None:
        episode = read_json(ROOT / "episodes" / "EP-001.json")
        self.assertIsNone(validate(episode))
        self.assertEqual(len(episode["pages"]), 5)
        self.assertEqual({page["plate"] for page in episode["pages"]} - PLATES, set())

    def test_build_has_clean_typography_and_no_old_overlay(self) -> None:
        with patch("scripts.build.find_art", return_value=None):
            output = build(ROOT / "episodes" / "EP-001.json")
        cards = sorted((output / "cards").glob("*.svg"))
        self.assertEqual(len(cards), 5)
        combined = "\n".join(card.read_text(encoding="utf-8") for card in cards)
        self.assertNotIn('fill-opacity="0.92"', combined)
        self.assertNotIn("01/07", combined)
        self.assertNotIn("<foreignObject", combined)
        self.assertIn("体谅别人", combined)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["format"], "five-card-fixed-plate-v1")

    def test_prompts_forbid_complex_scenes(self) -> None:
        visual = read_json(ROOT / "visual" / "plates.json")
        prompt = visual["global_negative"]
        for phrase in (
            "no furniture",
            "no full body",
            "no detailed hands",
            "no extra person",
            "no complex gesture",
            "no hard rectangular image edge",
        ):
            self.assertIn(phrase, prompt)

    def test_copy_avoids_banned_abstractions(self) -> None:
        raw = (ROOT / "episodes" / "EP-001.json").read_text(encoding="utf-8")
        self.assertFalse(any(word in raw for word in BANNED))

    def test_rejects_seven_pages(self) -> None:
        episode = read_json(ROOT / "episodes" / "EP-001.json")
        episode["pages"].extend(episode["pages"][:2])
        with self.assertRaisesRegex(ValueError, "必须正好五页"):
            validate(episode)

    def test_wrap_keeps_closing_punctuation_with_previous_line(self) -> None:
        self.assertEqual(wrap("一二三四五六七八九十。", 10), ["一二三四五六七八九十。"])

    def test_checked_in_layout_proof_matches_generator(self) -> None:
        episode = read_json(ROOT / "episodes" / "EP-001.json")
        theme = read_json(ROOT / "templates" / "theme.json")
        proof_dir = ROOT / "examples" / "EP-001-layout-proof"
        with patch("scripts.build.find_art", return_value=None):
            for number, page in enumerate(episode["pages"], 1):
                generated = render(episode, page, number, theme)
                checked_in = proof_dir / f"EP-001-{number:02d}.svg"
                self.assertEqual(generated, checked_in.read_text(encoding="utf-8"), checked_in.name)


if __name__ == "__main__":
    unittest.main()
