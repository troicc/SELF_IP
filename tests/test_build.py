from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from scripts.build import BANNED, ROOT, build, read_json, short_tail_path, validate_episode


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.episode = read_json(ROOT / "episodes" / "EP-001.json")
        self.visual = read_json(ROOT / "visual" / "plates.json")
        self.theme = read_json(ROOT / "templates" / "theme.json")

    def test_story_has_hook_reframe_and_action(self) -> None:
        validate_episode(self.episode, self.visual)
        self.assertEqual(len(self.episode["pages"]), 5)
        cover = self.episode["pages"][0]["bubbles"][0]["text"]
        reveal = "\n".join(b["text"] for b in self.episode["pages"][2]["bubbles"])
        action = "\n".join(b["text"] for b in self.episode["pages"][3]["bubbles"])
        self.assertIn("邻居", cover)
        self.assertIn("妈，我在开会", reveal)
        self.assertIn("几点复诊", action)
        raw = json.dumps(self.episode, ensure_ascii=False)
        self.assertFalse(any(word in raw for word in BANNED))

    def test_build_uses_one_unified_balloon_system(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = build(
                ROOT / "episodes" / "EP-001.json",
                out_dir=Path(tmp) / "EP-001",
                art_dir=ROOT / "assets" / "plates",
            )
            cards = sorted((output / "cards").glob("*.svg"))
            self.assertEqual(len(cards), 5)
            combined = "\n".join(path.read_text(encoding="utf-8") for path in cards)
            expected_bubbles = sum(len(page["bubbles"]) for page in self.episode["pages"])
            self.assertEqual(combined.count('class="speech-balloon"'), expected_bubbles)
            self.assertNotIn('class="speech-bubble"', combined)
            self.assertNotIn("data-speaker=\"阿迟\">\n<text", combined)
            self.assertIn("LXGW WenKai Medium", combined)
            self.assertNotIn('fill-opacity="0.92"', combined)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["format"], "five-card-unified-balloon-v3")
            self.assertEqual(manifest["balloon_style"], "soft-tv-standard")

    def test_tail_points_to_mouth_and_is_capped(self) -> None:
        path, attach, tip = short_tail_path(
            x=100,
            y=300,
            w=420,
            h=180,
            mouth=(320, 980),
            progress=self.theme["balloon"]["tail_progress"],
            base_width=self.theme["balloon"]["tail_base_width"],
            max_length=self.theme["balloon"]["tail_max_length"],
        )
        self.assertTrue(path.endswith("Z"))
        tail_length = math.dist(attach, tip)
        self.assertLessEqual(tail_length, self.theme["balloon"]["tail_max_length"] + 0.01)
        ax, ay = attach
        tx, ty = tip
        mx, my = (320, 980)
        cross = (tx - ax) * (my - ay) - (ty - ay) * (mx - ax)
        self.assertAlmostEqual(cross, 0.0, places=5)

    def test_visual_contract_keeps_art_simple_and_text_free(self) -> None:
        negative = self.visual["global_negative"]
        for phrase in (
            "no text",
            "no speech balloon",
            "no furniture",
            "no detailed hands",
            "no extra person",
        ):
            self.assertIn(phrase, negative)
        for plate_id, plate in self.visual["plates"].items():
            self.assertEqual(set(plate["mouths"]), {"阿迟", "周叔"}, plate_id)
            self.assertGreaterEqual(len(plate["slots"]), 2)

    def test_font_and_balloon_baseline_are_locked(self) -> None:
        font = self.theme["font"]
        balloon = self.theme["balloon"]
        self.assertIn("LXGW WenKai Medium", font["family"])
        self.assertEqual(balloon["stroke_width"], 2.5)
        self.assertEqual(balloon["tail_base_width"], 28)
        self.assertEqual(balloon["tail_max_length"], 115)
        self.assertEqual(self.theme["colors"]["balloon"], "#FFFDF8")


if __name__ == "__main__":
    unittest.main()
