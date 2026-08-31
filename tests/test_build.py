from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build import BANNED, ROOT, build, read_json, validate_episode


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.episode = read_json(ROOT / "episodes" / "EP-001.json")
        self.visual = read_json(ROOT / "visual" / "plates.json")

    def test_episode_and_dialogue_rhythm_are_valid(self) -> None:
        validate_episode(self.episode, self.visual)
        self.assertEqual(len(self.episode["pages"]), 5)
        text = "\n".join(
            bubble["text"]
            for page in self.episode["pages"]
            for bubble in page["bubbles"]
        )
        self.assertIn("……", text)
        self.assertIn("就这样？", text)
        self.assertFalse(any(word in text for word in BANNED))

    def test_build_outputs_mouth_anchored_bubbles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = build(
                ROOT / "episodes" / "EP-001.json",
                out_dir=Path(tmp) / "EP-001",
                art_dir=ROOT / "assets" / "plates",
            )
            cards = sorted((output / "cards").glob("*.svg"))
            self.assertEqual(len(cards), 5)
            combined = "\n".join(path.read_text(encoding="utf-8") for path in cards)
            self.assertIn('class="speech-bubble"', combined)
            self.assertIn('class="speech-tail"', combined)
            self.assertIn("data-tail-target", combined)
            self.assertIn("LXGW WenKai Medium", combined)
            self.assertNotIn('fill-opacity="0.92"', combined)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "five-card-mouth-anchored-bubbles-v2")

    def test_every_plate_has_mouths_and_non_overlapping_slots(self) -> None:
        for plate_id, plate in self.visual["plates"].items():
            self.assertEqual(set(plate["mouths"]), {"阿迟", "周叔"}, plate_id)
            for speaker, mouth in plate["mouths"].items():
                self.assertEqual(len(mouth), 2, f"{plate_id}:{speaker}")
                self.assertTrue(0 <= mouth[0] <= 1080 and 0 <= mouth[1] <= 1440)
            for slot in plate["slots"].values():
                self.assertGreater(slot["w"], 300)
                self.assertGreater(slot["max_h"], 100)

    def test_prompts_keep_art_text_free_and_simple(self) -> None:
        negative = self.visual["global_negative"]
        for phrase in ("no text", "no speech bubble", "no furniture", "no detailed hands", "no extra person"):
            self.assertIn(phrase, negative)


if __name__ == "__main__":
    unittest.main()
