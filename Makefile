PYTHON ?= python3
TOPIC ?= T009
EPISODE ?= EP-001
SCENE ?= B01

.PHONY: bootstrap validate test benchmark-prompts benchmark-jobs benchmark-run-init benchmark-run-validate refinement-jobs refinement-validate calibration-jobs calibration-compose pilot postflight production-requests export

bootstrap:
	git submodule update --init --recursive

validate:
	$(PYTHON) scripts/validate_project.py

test:
	$(PYTHON) -m unittest discover -s tests -v

benchmark-prompts:
	$(PYTHON) scripts/render_benchmarks.py --out build/benchmarks/requests.jsonl

benchmark-jobs: benchmark-prompts
	$(PYTHON) scripts/build_benchmark_jobs.py --out build/benchmarks/jobs.jsonl

benchmark-run-init:
	$(PYTHON) scripts/benchmark_run.py init --scene $(SCENE) --out benchmarks/runs/$(SCENE).json

benchmark-run-validate:
	$(PYTHON) scripts/benchmark_run.py validate --run benchmarks/runs/$(SCENE).json --verify-files

refinement-jobs:
	$(PYTHON) scripts/build_style14_refinement_jobs.py --out build/benchmarks/style14-refinement-jobs.jsonl

refinement-validate:
	$(PYTHON) scripts/refinement_run.py validate --run benchmarks/refinement-runs/style14-v2.json

calibration-jobs:
	$(PYTHON) scripts/build_pilot_calibration_jobs.py --episode episodes/$(EPISODE).yaml --out build/pilots/$(EPISODE)/jobs.jsonl

calibration-compose:
	$(PYTHON) scripts/place_illustration_stage.py --all --jobs build/pilots/$(EPISODE)/jobs.jsonl

pilot:
	$(PYTHON) scripts/select_topic.py --topic $(TOPIC) --out build/work/$(TOPIC)/topic.json
	$(PYTHON) scripts/quality_gate.py pre --episode episodes/$(EPISODE).yaml
	$(PYTHON) scripts/export_cards.py --episode episodes/$(EPISODE).yaml --out build/cards/$(EPISODE)-layout-proof --allow-placeholders

postflight:
	$(PYTHON) scripts/init_postflight.py --episode episodes/$(EPISODE).yaml --out build/qa/$(EPISODE).json

production-requests:
	$(PYTHON) scripts/build_episode_image_requests.py --episode episodes/$(EPISODE).yaml --out build/requests/$(EPISODE).jsonl

IMAGE_DIR ?= build/images/$(EPISODE)
QA ?= build/qa/$(EPISODE).json
OUT ?= build/cards/$(EPISODE)

export:
	$(PYTHON) scripts/quality_gate.py post --episode episodes/$(EPISODE).yaml --qa $(QA)
	$(PYTHON) scripts/export_cards.py --episode episodes/$(EPISODE).yaml --image-dir $(IMAGE_DIR) --qa $(QA) --out $(OUT)
