#!/usr/bin/env python3
"""
Unit tests for pipeline.yaml

Validates the multi-modal pipeline structure — 4 Gemma 4 analyses
per frame (detect, read, describe, safety) with Makoto attestation.
"""

import os

import yaml
import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_FILE = os.path.join(SCRIPT_DIR, "pipeline.yaml")


@pytest.fixture
def pipeline():
    """Load and parse pipeline.yaml."""
    with open(PIPELINE_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def processors(pipeline):
    """Get the processor list."""
    return pipeline["pipeline"]["processors"]


# ── Structure Tests ──────────────────────────────────────────


class TestPipelineStructure:
    """Validate the pipeline YAML structure."""

    def test_yaml_parses(self, pipeline):
        """pipeline.yaml must be valid YAML."""
        assert pipeline is not None

    def test_has_input(self, pipeline):
        assert "input" in pipeline

    def test_has_pipeline(self, pipeline):
        assert "pipeline" in pipeline

    def test_has_output(self, pipeline):
        assert "output" in pipeline

    def test_input_is_generate(self, pipeline):
        assert "generate" in pipeline["input"]

    def test_generate_has_interval(self, pipeline):
        gen = pipeline["input"]["generate"]
        assert "interval" in gen

    def test_generate_interval_uses_env_var(self, pipeline):
        interval = pipeline["input"]["generate"]["interval"]
        assert "CAPTURE_INTERVAL" in interval


class TestSubprocessProcessor:
    """Test the subprocess (webcam capture) processor."""

    def test_first_processor_is_subprocess(self, processors):
        assert "subprocess" in processors[0]

    def test_subprocess_runs_uv(self, processors):
        proc = processors[0]["subprocess"]
        assert proc["name"] == "uv"

    def test_subprocess_runs_capture_script(self, processors):
        proc = processors[0]["subprocess"]
        args_str = " ".join(proc["args"])
        assert "capture_frame.py" in args_str

    def test_subprocess_has_buffer(self, processors):
        proc = processors[0]["subprocess"]
        assert proc["max_buffer"] >= 1048576, "Buffer must be at least 1MB for base64 frames"


class TestMultiModalBranches:
    """Test the four inference branches (detect, read, describe, safety)."""

    def _get_branches(self, processors):
        """Extract all branch processors."""
        return [p for p in processors if "branch" in p]

    def test_has_four_branches(self, processors):
        branches = self._get_branches(processors)
        assert len(branches) == 4, f"Expected 4 inference branches, got {len(branches)}"

    def test_all_branches_use_http_post(self, processors):
        for p in self._get_branches(processors):
            branch = p["branch"]
            http = branch["processors"][0]["http"]
            assert http["verb"] == "POST"

    def test_all_branches_use_inference_url_env(self, processors):
        for p in self._get_branches(processors):
            branch = p["branch"]
            http = branch["processors"][0]["http"]
            assert "INFERENCE_URL" in http["url"]

    def test_all_branches_include_image(self, processors):
        for p in self._get_branches(processors):
            branch = p["branch"]
            assert "image_base64" in branch["request_map"]

    def test_branch_result_maps_have_timing(self, processors):
        """Each branch should capture millisecond timing."""
        for p in self._get_branches(processors):
            branch = p["branch"]
            assert "ms" in branch["result_map"]

    def test_detect_branch_extracts_detect(self, processors):
        branches = self._get_branches(processors)
        assert "detect" in branches[0]["branch"]["result_map"]

    def test_read_branch_extracts_read_text(self, processors):
        branches = self._get_branches(processors)
        assert "read_text" in branches[1]["branch"]["result_map"]

    def test_describe_branch_extracts_describe(self, processors):
        branches = self._get_branches(processors)
        assert "describe" in branches[2]["branch"]["result_map"]

    def test_safety_branch_extracts_safety(self, processors):
        branches = self._get_branches(processors)
        assert "safety" in branches[3]["branch"]["result_map"]


class TestSchemaMapping:
    """Test the Bloblang schema mapping that assembles the output envelope."""

    @pytest.fixture
    def mapping_text(self, processors):
        """Find the main assembly mapping (after the branches)."""
        mappings = [p for p in processors if "mapping" in p]
        # The assembly mapping is the last one (after parse + filter + 4 branches)
        return mappings[-1]["mapping"]

    def test_has_timestamp(self, mapping_text):
        assert "root.timestamp" in mapping_text

    def test_has_node_id(self, mapping_text):
        assert "root.node_id" in mapping_text

    def test_has_pipeline_version(self, mapping_text):
        assert "root.pipeline_version" in mapping_text

    def test_has_model(self, mapping_text):
        assert "root.model" in mapping_text

    def test_has_frame_id(self, mapping_text):
        assert "root.frame_id" in mapping_text

    def test_has_mode_multi(self, mapping_text):
        assert '"multi"' in mapping_text

    def test_has_detect_section(self, mapping_text):
        assert "root.detect" in mapping_text

    def test_has_read_text_section(self, mapping_text):
        assert "root.read_text" in mapping_text

    def test_has_describe_section(self, mapping_text):
        assert "root.describe" in mapping_text

    def test_has_safety_section(self, mapping_text):
        assert "root.safety" in mapping_text

    def test_has_total_ms(self, mapping_text):
        assert "root.total_ms" in mapping_text

    def test_has_total_tokens(self, mapping_text):
        assert "root.total_tokens" in mapping_text

    def test_has_integrity_hash(self, mapping_text):
        assert "root.integrity" in mapping_text
        assert 'hash("sha256")' in mapping_text


class TestMakotoAttestation:
    """Test the Makoto L1 attestation mutation."""

    @pytest.fixture
    def mutation_text(self, processors):
        """Find the attestation mutation (last processor)."""
        mutations = [p for p in processors if "mutation" in p]
        # The attestation is the last mutation
        return mutations[-1]["mutation"]

    def test_has_attestation_field(self, mutation_text):
        assert "root.attestation" in mutation_text

    def test_has_intoto_type(self, mutation_text):
        assert "https://in-toto.io/Statement/v1" in mutation_text

    def test_has_makoto_predicate_type(self, mutation_text):
        assert "https://makoto.dev/transform/v1" in mutation_text

    def test_has_subject_with_digest(self, mutation_text):
        assert '"subject"' in mutation_text
        assert '"digest"' in mutation_text

    def test_has_executor_identity(self, mutation_text):
        assert "expanso-edge://" in mutation_text

    def test_references_multi_modal_modes(self, mutation_text):
        assert "detect" in mutation_text
        assert "read_text" in mutation_text
        assert "describe" in mutation_text
        assert "safety" in mutation_text


class TestOutputBroker:
    """Test the output broker configuration."""

    def test_output_is_broker(self, pipeline):
        assert "broker" in pipeline["output"]

    def test_broker_is_fan_out(self, pipeline):
        assert pipeline["output"]["broker"]["pattern"] == "fan_out"

    def test_has_stdout_output(self, pipeline):
        outputs = pipeline["output"]["broker"]["outputs"]
        stdout_outputs = [o for o in outputs if "stdout" in o]
        assert len(stdout_outputs) == 1

    def test_has_file_output(self, pipeline):
        outputs = pipeline["output"]["broker"]["outputs"]
        file_outputs = [o for o in outputs if "file" in o]
        assert len(file_outputs) == 1

    def test_file_output_is_daily_jsonl(self, pipeline):
        outputs = pipeline["output"]["broker"]["outputs"]
        file_out = [o for o in outputs if "file" in o][0]["file"]
        assert ".jsonl" in file_out["path"]
        assert "ts_format" in file_out["path"]

    def test_file_output_uses_lines_codec(self, pipeline):
        outputs = pipeline["output"]["broker"]["outputs"]
        file_out = [o for o in outputs if "file" in o][0]["file"]
        assert file_out["codec"] == "lines"

    def test_has_dashboard_http_output(self, pipeline):
        """Pipeline should POST detections to the dashboard."""
        outputs = pipeline["output"]["broker"]["outputs"]
        http_outputs = [o for o in outputs if "drop_on" in o or "http_client" in o]
        assert len(http_outputs) >= 1
