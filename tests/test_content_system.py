from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import (  # noqa: E402
    AI_MARKERS,
    EXPECTED_BEATS,
    episode_paths,
    find_markers,
    load_json,
    read_topics,
    user_visible_strings,
    validate_episode,
)


class ContentSystemTests(unittest.TestCase):
    def test_topic_bank_has_twelve_complete_topics(self) -> None:
        topics = read_topics()
        self.assertEqual(len(topics), 12)
        self.assertEqual(len({row["topic_id"] for row in topics}), 12)
        self.assertEqual({row["relationship"] for row in topics}, {"family", "romance", "friendship", "self"})
        required = {
            "topic_id",
            "relationship",
            "scene",
            "surface_conflict",
            "hidden_need",
            "hook",
            "visual_action",
            "mentor_mode",
            "ending_type",
            "source",
            "status",
            "metrics",
        }
        for row in topics:
            self.assertTrue(required <= set(row))
            self.assertTrue(all(row[field].strip() for field in required - {"metrics"}))
            json.loads(row["metrics"] or "{}")

    def test_four_relationship_pilots_have_exactly_seven_pages(self) -> None:
        paths = episode_paths()
        self.assertGreaterEqual(len(paths), 4)
        relationships = set()
        for path in paths:
            episode = load_json(path)
            relationships.add(episode["relationship"])
            self.assertEqual(validate_episode(episode, path.name), [])
            self.assertEqual([page["beat"] for page in episode["pages"]], EXPECTED_BEATS)
            self.assertEqual(len(episode["pages"]), 7)
        self.assertEqual(relationships, {"family", "romance", "friendship", "self"})

    def test_visible_copy_has_no_assistance_marker(self) -> None:
        for path in episode_paths():
            episode = load_json(path)
            self.assertEqual(find_markers(user_visible_strings(episode), AI_MARKERS), [], path.name)

    def test_every_episode_has_action_or_honest_open_state(self) -> None:
        for path in episode_paths():
            episode = load_json(path)
            ending = episode["ending"]
            self.assertTrue(ending.get("action") or ending.get("open_state"), path.name)
            self.assertEqual(episode["comment_question"], episode["pages"][6]["copy"][-1]["text"])

    def test_image_briefs_do_not_copy_body_text(self) -> None:
        for path in episode_paths():
            episode = load_json(path)
            for page in episode["pages"]:
                image_text = " ".join(page["image"][field] for field in ("subject", "composition", "visual_action"))
                for line in page["copy"]:
                    if len(line["text"]) >= 6:
                        self.assertNotIn(line["text"], image_text, f"{path.name} page {page['number']}")

    def test_ep003_empty_seat_has_no_phantom_second_order(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-003.yaml")
        pages = {page["number"]: page for page in episode["pages"]}
        self.assertIn("一碗", " ".join(pages[1]["image"]["necessary_props"]))
        self.assertIn("一碗", " ".join(pages[2]["image"]["necessary_props"]))
        self.assertNotIn("两碗", " ".join(pages[2]["image"]["necessary_props"]))
        self.assertIn("两碗", " ".join(pages[3]["image"]["necessary_props"]))
        for number in range(4, 8):
            self.assertIn("三碗", " ".join(pages[number]["image"]["necessary_props"]))
        visible_copy = " ".join(line["text"] for page in episode["pages"] for line in page["copy"])
        self.assertNotIn("两碗面刚端上来", visible_copy)
        self.assertNotIn("对面空座和未动的面", pages[7]["image"]["subject"])
        self.assertIn("下次有变，能在我出门前说一声吗？", visible_copy)


if __name__ == "__main__":
    unittest.main()
