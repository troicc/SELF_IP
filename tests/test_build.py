from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build import ROOT, build, load_json, prompt_for_plate, validate_episode


class BuildTests(unittest.TestCase):
    def test_sample_episode_is_valid(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.json")
        self.assertEqual(validate_episode(episode), [])
        self.assertEqual(len(episode["pages"]), 5)

    def test_build_outputs_five_clean_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "EP-001"
            build(ROOT / "episodes" / "EP-001.json", out_dir=out, assets_dir=Path(temp_dir) / "missing")
            cards = sorted((out / "cards").glob("*.svg"))
            self.assertEqual(len(cards), 5)
            combined = "\n".join(card.read_text(encoding="utf-8") for card in cards)
            self.assertNotIn('fill-opacity="0.92"', combined)
            self.assertNotIn("01/07", combined)
            self.assertIn("体谅别人", combined)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "five-card-fixed-plate-v1")

    def test_prompts_forbid_complex_scene(self) -> None:
        visual = load_json(ROOT / "visual" / "plates.json")
        prompt = prompt_for_plate("quiet", visual)
        self.assertIn("no furniture", prompt)
        self.assertIn("no full body", prompt)
        self.assertIn("no extra person", prompt)

    def test_rejects_seven_pages(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.json")
        episode["pages"].extend(episode["pages"][:2])
        self.assertIn("episode must contain exactly five pages", validate_episode(episode))


if __name__ == "__main__":
    unittest.main()
