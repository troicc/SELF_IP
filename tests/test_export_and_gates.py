from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_episode_image_requests import build_requests  # noqa: E402
from build_pilot_calibration_jobs import build_jobs as build_calibration_jobs  # noqa: E402
from common import load_json, validate_postflight  # noqa: E402
from export_cards import export_episode, split_visual_units  # noqa: E402


class ExportAndGateTests(unittest.TestCase):
    def test_placeholder_proof_exports_seven_local_text_svgs(self) -> None:
        episode_path = ROOT / "episodes" / "EP-001.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cards"
            outputs = export_episode(episode_path, out, None, True)
            self.assertEqual(len(outputs), 7)
            self.assertTrue((out / "manifest.json").is_file())
            combined = "\n".join(path.read_text(encoding="utf-8") for path in outputs)
            self.assertIn("水果箱渗水五天了", combined)
            self.assertIn("本故事为原创虚构", combined)
            self.assertNotIn("AIGC", combined)
            self.assertNotIn("AI辅助", combined)
            self.assertNotIn("AI 生成", combined)

    def test_final_image_export_requires_postflight(self) -> None:
        episode_path = ROOT / "episodes" / "EP-001.yaml"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "requires a passed postflight"):
                export_episode(episode_path, Path(tmp) / "cards", Path(tmp) / "images", False)

    def test_incomplete_postflight_fails_closed(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.yaml")
        qa = load_json(ROOT / "templates" / "postflight-qa.template.json")
        qa["episode_id"] = episode["episode_id"]
        errors = validate_postflight(episode, qa, "qa")
        self.assertTrue(errors)

    def test_production_requests_fail_before_style_lock(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-001.yaml")
        with self.assertRaisesRegex(ValueError, "not locked"):
            build_requests(episode)

    def test_local_line_breaker_avoids_punctuation_and_short_widows(self) -> None:
        lines = split_visual_units("周叔：也可能。我刚才说轻了，光替没来的人想了。", 18)
        self.assertGreaterEqual(len(lines), 2)
        self.assertFalse(lines[-1].startswith(tuple("，。！？：；、）》】}）’”」』…")))
        self.assertGreaterEqual(len(lines[-1]), 7)

    def test_ep003_calibration_jobs_keep_art_and_copy_contracts_separate(self) -> None:
        episode = load_json(ROOT / "episodes" / "EP-003.yaml")
        jobs = build_calibration_jobs(episode)
        self.assertEqual(len(jobs), 7)
        for page, job in zip(episode["pages"], jobs, strict=True):
            self.assertEqual(job["page"], page["number"])
            self.assertEqual(job["style_id"], "14")
            self.assertTrue(job["calibration_only"])
            self.assertFalse(job["production_style_locked"])
            self.assertLessEqual(job["reference_count"], 5)
            self.assertTrue(all(item["role"] == "style-only" for item in job["style_references"]))
            self.assertTrue(all(item["role"] == "identity-only" for item in job["character_references"]))
            self.assertFalse(
                {item["path"] for item in job["style_references"]}
                & {item["path"] for item in job["character_references"]}
            )
            for copy_line in page["copy"]:
                self.assertNotIn(copy_line["text"], job["prompt"])
            stage = job["subject_stage_region"]
            for region in job["reserved_text_regions"]:
                separated = (
                    stage["x"] + stage["width"] <= region["x"]
                    or region["x"] + region["width"] <= stage["x"]
                    or stage["y"] + stage["height"] <= region["y"]
                    or region["y"] + region["height"] <= stage["y"]
                )
                self.assertTrue(separated, job["job_id"])


if __name__ == "__main__":
    unittest.main()
