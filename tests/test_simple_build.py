from __future__ import annotations

import json
import shutil
import unittest

from scripts.build import BANNED, PLATES, ROOT, build, read_json, validate_episode


class SimpleBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(ROOT / "build", ignore_errors=True)

    def test_episode_is_exactly_five_pages(self) -> None:
        episode = read_json(ROOT / "episodes" / "EP-001.json")
        self.assertEqual(validate_episode(episode), [])
        self.assertEqual(len(episode["pages"]), 5)
        self.assertEqual({page["plate"] for page in episode["pages"]} - PLATES, set())

    def test_build_removes_old_overlay_and_seven_page_footer(self) -> None:
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

    def test_prompts_forbid_complex_scene_generation(self) -> None:
        output = build(ROOT / "episodes" / "EP-001.json")
        prompts = (output / "prompts.jsonl").read_text(encoding="utf-8")
        for phrase in ("no furniture", "no full body", "no extra person", "no complex gesture"):
            self.assertIn(phrase, prompts)

    def test_copy_avoids_banned_abstractions(self) -> None:
        raw = (ROOT / "episodes" / "EP-001.json").read_text(encoding="utf-8")
        self.assertFalse(any(phrase in raw for phrase in BANNED))


if __name__ == "__main__":
    unittest.main()
