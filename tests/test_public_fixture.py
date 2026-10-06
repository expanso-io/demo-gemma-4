from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


def test_committed_job_embeds_current_pipeline():
    pipeline = yaml.safe_load((ROOT / "pipeline.yaml").read_text())
    job = yaml.safe_load((ROOT / "scripts" / "job.yaml").read_text())
    assert job["config"] == pipeline


def test_cloud_job_targets_jetson_nodes():
    job = yaml.safe_load((ROOT / "scripts" / "job.yaml").read_text())
    assert job["selector"] == {
        "match_labels": {"hardware": "nvidia-jetson"}
    }


def test_fixture_server_has_one_answer_per_inference_branch():
    fixture_server = (ROOT / "scripts" / "fixture_server.py").read_text()
    for prompt in (
        "Which of these objects",
        "Read all text",
        "Describe this scene",
        "Is this scene safe",
    ):
        assert prompt in fixture_server


def test_fixture_run_starts_from_clean_edge_state():
    runner = (ROOT / "scripts" / "run-public-fixture.sh").read_text()
    assert 'EDGE_DATA_DIR="${RUNTIME}/edge"' in runner
    assert 'rm -rf "${EDGE_DATA_DIR}"' in runner
    assert '--data-dir "${EDGE_DATA_DIR}"' in runner
