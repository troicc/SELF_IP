from __future__ import annotations

import csv
import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import compile_benchmark_requests, load_json  # noqa: E402
from build_benchmark_jobs import build_jobs  # noqa: E402
from benchmark_run import CHECK_FIELDS, validate_run  # noqa: E402
from build_style14_refinement_jobs import build_refinement_jobs  # noqa: E402
from finalize_style import evaluate_scorecard  # noqa: E402
from place_illustration_stage import stage_geometry  # noqa: E402
from refinement_run import validate_run as validate_refinement_run  # noqa: E402


SCORE_FIELDS = [
    "scene_id",
    "style_id",
    "attempt_count",
    "successful_count",
    "e1_name",
    "e1_character_consistency",
    "e1_emotional_expression",
    "e1_whitespace",
    "e1_interaction_naturalness",
    "e1_distinctiveness",
    "e1_synthetic_polish_flag",
    "e2_name",
    "e2_character_consistency",
    "e2_emotional_expression",
    "e2_whitespace",
    "e2_interaction_naturalness",
    "e2_distinctiveness",
    "e2_synthetic_polish_flag",
    "notes",
]


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requests = compile_benchmark_requests()
        cls.jobs = build_jobs(cls.requests)

    def test_matrix_is_twelve_scenes_by_three_styles(self) -> None:
        self.assertEqual(len(self.requests), 36)
        self.assertEqual({item["scene_id"] for item in self.requests}, {f"B{i:02d}" for i in range(1, 13)})
        self.assertEqual({item["style_id"] for item in self.requests}, {"10", "14", "18"})
        for scene_id in {item["scene_id"] for item in self.requests}:
            self.assertEqual({item["style_id"] for item in self.requests if item["scene_id"] == scene_id}, {"10", "14", "18"})

    def test_every_request_contains_the_required_contract_fields(self) -> None:
        fields = {
            "subject",
            "composition",
            "style_id",
            "style_references",
            "character_references",
            "negative_constraints",
            "aspect_ratio",
            "reserved_text_regions",
            "prompt",
        }
        for request in self.requests:
            self.assertTrue(fields <= set(request), request["request_id"])
            self.assertEqual(request["aspect_ratio"], "3:4")
            self.assertEqual(request["expected_attempts"], 3)
            self.assertNotIn("【", request["prompt"])
            self.assertNotIn("】", request["prompt"])

    def test_style_and_character_references_are_separate(self) -> None:
        for request in self.requests:
            style_paths = {item["path"] for item in request["style_references"]}
            cast_paths = {item["path"] for item in request["character_references"]}
            self.assertFalse(style_paths & cast_paths)
            self.assertTrue(all(item["role"] == "style-only" for item in request["style_references"]))
            self.assertTrue(all(item["role"] == "identity-only" for item in request["character_references"]))
            self.assertLessEqual(len(request["style_references"] + request["character_references"]), 5)
            self.assertEqual(request["ready_for_generation"], all(item["exists"] for item in request["style_references"] + request["character_references"]))

    def test_same_identity_references_are_reused_across_candidate_styles(self) -> None:
        for scene_id in {item["scene_id"] for item in self.requests}:
            groups = [
                tuple(item["path"] for item in request["character_references"])
                for request in self.requests
                if request["scene_id"] == scene_id
            ]
            self.assertEqual(len(set(groups)), 1, scene_id)

    def test_all_benchmark_requests_are_generation_ready(self) -> None:
        not_ready = [request["request_id"] for request in self.requests if not request["ready_for_generation"]]
        self.assertEqual(not_ready, [])

    def test_identity_manifest_covers_exactly_the_referenced_assets(self) -> None:
        manifest = load_json(ROOT / "benchmarks" / "reference-assets" / "identity-neutral" / "manifest.json")
        manifest_paths = {item["path"] for item in manifest["assets"]}
        request_paths = {
            item["path"]
            for request in self.requests
            for item in request["character_references"]
        }
        self.assertEqual(manifest["role"], "identity-only")
        self.assertEqual(manifest["status"], "accepted_for_benchmark")
        self.assertEqual(manifest["asset_set_version"], "2.1.0")
        self.assertEqual(manifest["render_treatment"], "functional_flat_cleanup")
        self.assertEqual(manifest_paths, request_paths)
        self.assertTrue(all(item["qa_status"] == "accepted" for item in manifest["assets"]))

    def test_upstream_prompts_explicitly_forbid_text(self) -> None:
        for request in self.requests:
            prompt_lower = request["prompt"].lower()
            self.assertTrue(
                "不加任何文字" in request["prompt"] or "no text" in prompt_lower,
                request["request_id"],
            )

    def test_job_manifest_expands_to_108_role_safe_attempts(self) -> None:
        self.assertEqual(len(self.jobs), 108)
        self.assertEqual(len({job["job_id"] for job in self.jobs}), 108)
        request_by_id = {request["request_id"]: request for request in self.requests}
        for job in self.jobs:
            request = request_by_id[job["request_id"]]
            self.assertLessEqual(job["reference_count"], 5)
            self.assertIn(request["prompt"], job["prompt"])
            self.assertEqual(job["upstream_prompt_sha256"], request["prompt_sha256"])
            self.assertTrue(all(item["role"] == "style-only" for item in job["style_references"]))
            self.assertTrue(all(item["role"] == "identity-only" for item in job["character_references"]))
            self.assertEqual([item["index"] for item in job["ordered_references"]], list(range(1, job["reference_count"] + 1)))

    def test_style14_refinement_round_keeps_style_and_identity_separate(self) -> None:
        jobs = build_refinement_jobs()
        self.assertEqual(len(jobs), 36)
        self.assertEqual({job["scene_id"] for job in jobs}, {f"B{i:02d}" for i in range(1, 13)})
        self.assertEqual({job["style_id"] for job in jobs}, {"14"})
        for job in jobs:
            self.assertTrue(job["calibration_only"])
            self.assertFalse(job["production_style_locked"])
            self.assertLessEqual(job["reference_count"], 5)
            self.assertTrue(all(item["role"] == "style-only" for item in job["style_references"]))
            self.assertTrue(all(item["role"] == "identity-only" for item in job["character_references"]))
            self.assertFalse(
                {item["path"] for item in job["style_references"]}
                & {item["path"] for item in job["character_references"]}
            )
            stage = job["subject_stage_region"]
            for reserved in job["reserved_text_regions"]:
                separated = (
                    stage["x"] + stage["width"] <= reserved["x"]
                    or reserved["x"] + reserved["width"] <= stage["x"]
                    or stage["y"] + stage["height"] <= reserved["y"]
                    or reserved["y"] + reserved["height"] <= stage["y"]
                )
                self.assertTrue(separated, job["job_id"])

    def test_stage_geometry_fits_inside_declared_region(self) -> None:
        stage = {"x": 0.04, "y": 0.27, "width": 0.53, "height": 0.69}
        width, height, x, y = stage_geometry((976, 910, 54, 538), stage)
        self.assertGreater(width, 0)
        self.assertGreater(height, 0)
        self.assertGreaterEqual(x, round(stage["x"] * 1086))
        self.assertGreaterEqual(y, round(stage["y"] * 1448))
        self.assertLessEqual(x + width, round((stage["x"] + stage["width"]) * 1086))
        self.assertLessEqual(y + height, round((stage["y"] + stage["height"]) * 1448))

    def test_style14_refinement_objective_gate_is_recorded_without_locking_style(self) -> None:
        run = load_json(ROOT / "benchmarks" / "refinement-runs" / "style14-v2.json")
        self.assertEqual(validate_refinement_run(run, verify_files=False), [])
        self.assertEqual(run["objective_result"]["successful_count"], 27)
        self.assertEqual(run["objective_result"]["attempt_count"], 36)
        self.assertTrue(run["objective_result"]["hard_gate_passed"])
        self.assertFalse(run["production_style_locked"])
        self.assertEqual(run["blind_review"]["status"], "pending_two_independent_reviewers")

    def test_unreviewed_scorecard_cannot_select_a_style(self) -> None:
        with self.assertRaisesRegex(ValueError, "two different named evaluators"):
            evaluate_scorecard(ROOT / "benchmarks" / "scorecard.csv")

    def test_completed_runs_have_verifiable_objective_counts(self) -> None:
        with (ROOT / "benchmarks" / "scorecard.csv").open("r", encoding="utf-8", newline="") as handle:
            score_rows = list(csv.DictReader(handle))
        totals = {"10": 0, "14": 0, "18": 0}
        for scene_id in (f"B{number:02d}" for number in range(1, 13)):
            run = load_json(ROOT / "benchmarks" / "runs" / f"{scene_id}.json")
            self.assertEqual(validate_run(run), [])
            self.assertEqual(run["status"], "completed_pending_blind_review")
            rows = {
                row["style_id"]: row
                for row in score_rows
                if row["scene_id"] == scene_id
            }
            for style, counts in run["unit_counts"].items():
                self.assertEqual(int(rows[style]["attempt_count"]), counts["attempt_count"])
                self.assertEqual(int(rows[style]["successful_count"]), counts["successful_count"])
                totals[style] += counts["successful_count"]
        self.assertEqual(totals, {"10": 6, "14": 10, "18": 7})

    def test_superseded_scene_prompt_contract_is_explicit_and_cannot_mask_drift(self) -> None:
        for scene_id in ("B03", "B07", "B09", "B11"):
            run = load_json(ROOT / "benchmarks" / "runs" / f"{scene_id}.json")
            contract_path = run["source_prompt_contract"]
            self.assertEqual(contract_path, f"benchmarks/contracts/{scene_id}-initial-v1.json")
            contract = load_json(ROOT / contract_path)
            self.assertEqual(contract["status"], "superseded")
            self.assertTrue(contract["superseded_reason"])
            drifted = copy.deepcopy(run)
            drifted["attempts"][0]["prompt_sha256"] = "0" * 64
            self.assertTrue(any("historical job contract" in error for error in validate_run(drifted)))

    def test_rejected_umbrella_choreography_is_not_an_active_scene(self) -> None:
        scene = next(item for item in load_json(ROOT / "benchmarks" / "scenes.yaml")["scenes"] if item["scene_id"] == "B07")
        active_text = " ".join(
            str(scene[key])
            for key in ("title", "subject_zh", "subject_en", "composition_zh", "composition_en", "visual_action")
        )
        self.assertNotIn("伞", active_text)
        self.assertNotIn("鞋尖", active_text)
        self.assertIn("筷子", active_text)

    def test_benchmark_objective_checks_are_scene_agnostic(self) -> None:
        self.assertIn("scene_specific_constraints_met", CHECK_FIELDS)
        self.assertNotIn("invitation_blank_once", CHECK_FIELDS)
        self.assertNotIn("snips_put_down_and_separate", CHECK_FIELDS)

    def test_benchmark_success_cannot_override_a_failed_check(self) -> None:
        run = copy.deepcopy(load_json(ROOT / "benchmarks" / "runs" / "B06.json"))
        run["attempts"][0]["successful"] = True
        errors = validate_run(run)
        self.assertTrue(any("successful must equal" in error for error in errors))

    def _write_scorecard(
        self,
        path: Path,
        style_scores: dict[str, float],
        synthetic_polish_style: str | None = None,
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SCORE_FIELDS)
            writer.writeheader()
            for number in range(1, 13):
                for style in ("10", "14", "18"):
                    score = style_scores[style]
                    row = {
                        "scene_id": f"B{number:02d}",
                        "style_id": style,
                        "attempt_count": 3,
                        "successful_count": 3,
                        "e1_name": "甲",
                        "e2_name": "乙",
                        "e1_synthetic_polish_flag": str(
                            style == synthetic_polish_style and number <= 3
                        ).lower(),
                        "e2_synthetic_polish_flag": str(
                            style == synthetic_polish_style and number <= 3
                        ).lower(),
                        "notes": "三张样本反复出现同脸与无理由柔光" if style == synthetic_polish_style and number <= 3 else "",
                    }
                    for evaluator in ("e1", "e2"):
                        for metric in (
                            "character_consistency",
                            "emotional_expression",
                            "whitespace",
                            "interaction_naturalness",
                            "distinctiveness",
                        ):
                            row[f"{evaluator}_{metric}"] = score
                    writer.writerow(row)

    def test_completed_scorecard_selects_only_statistical_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.csv"
            self._write_scorecard(path, {"10": 4.7, "14": 4.0, "18": 3.7})
            result = evaluate_scorecard(path)
            self.assertEqual(result["winner"], "10")

    def test_close_candidates_require_another_blind_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.csv"
            self._write_scorecard(path, {"10": 4.5, "14": 4.4, "18": 3.7})
            with self.assertRaisesRegex(ValueError, "tied within 0.15"):
                evaluate_scorecard(path)

    def test_consensus_synthetic_polish_flag_hard_fails_a_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scores.csv"
            self._write_scorecard(
                path,
                {"10": 4.8, "14": 4.2, "18": 3.7},
                synthetic_polish_style="10",
            )
            result = evaluate_scorecard(path)
            self.assertEqual(result["winner"], "14")
            self.assertIn(
                "synthetic_polish_consensus_in_three_or_more_scenes",
                result["summaries"]["10"]["hard_failures"],
            )


if __name__ == "__main__":
    unittest.main()
