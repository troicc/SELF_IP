from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import load_json  # noqa: E402
from validate_project import validate_repository  # noqa: E402


class ProjectStructureTests(unittest.TestCase):
    def test_full_project_validator(self) -> None:
        self.assertEqual(validate_repository(), [])

    def test_vendor_is_single_style_recipe_source(self) -> None:
        style_files = [path for path in ROOT.rglob("STYLES.md") if ".git" not in path.parts]
        self.assertEqual(style_files, [ROOT / "vendor" / "hand-drawn-styles" / "STYLES.md"])
        modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
        self.assertIn("https://github.com/threerocks/hand-drawn-styles.git", modules)
        license_text = (ROOT / "vendor" / "hand-drawn-styles" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)

    def test_cast_bible_has_all_required_character_contracts(self) -> None:
        cast = load_json(ROOT / "ip" / "CAST_BIBLE.yaml")
        self.assertEqual({item["id"] for item in cast["characters"]}, {"achi", "zhoushu", "qinyi"})
        fields = {
            "immutable_traits",
            "variable_traits",
            "facial_features",
            "body_proportions",
            "hairstyle",
            "fixed_clothing",
            "fixed_props",
            "gesture_habits",
            "language_habits",
            "flaws",
            "growth_arc",
            "forbidden_drift",
        }
        for character in cast["characters"]:
            self.assertTrue(fields <= set(character), character["id"])

    def test_episode_schema_and_templates_are_machine_readable(self) -> None:
        schema = load_json(ROOT / "schemas" / "episode.schema.json")
        self.assertEqual(schema["properties"]["pages"]["minItems"], 7)
        self.assertEqual(schema["properties"]["pages"]["maxItems"], 7)
        self.assertEqual(len(schema["properties"]["pages"]["prefixItems"]), 7)
        load_json(ROOT / "templates" / "episode.template.yaml")
        load_json(ROOT / "templates" / "card-layout.json")

    def test_production_style_is_intentionally_unlocked_in_phase_one(self) -> None:
        self.assertFalse((ROOT / "config" / "style-lock.json").exists())
        contract = (ROOT / "ip" / "STYLE_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("benchmarking", contract)
        self.assertIn("dialogue-sketch-v1", contract)


if __name__ == "__main__":
    unittest.main()

