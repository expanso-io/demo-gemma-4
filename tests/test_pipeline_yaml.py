#!/usr/bin/env python3
"""
Unit tests for pipeline.yaml

Validates the pipeline structure, Bloblang mappings, and
configuration without requiring Expanso Edge to be installed.
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


# ── Structure Tests ──────────────────────────────────────────


class TestPipelineStructure:
    """Validate the pipeline YAML structure."""

    def test_yaml_parses(self, pipeline):
        """pipeline.yaml must be valid YAML."""
        assert pipeline is not None

    def test_has_input(self, pipeline):
        """Pipeline must have an input section."""
        assert "input" in pipeline

    def test_has_pipeline(self, pipeline):
        """Pipeline must have a pipeline section."""
        assert "pipeline" in pipeline

    def test_has_output(self, pipeline):
        """Pipeline must have an output section."""
        assert "output" in pipeline

    def test_input_is_generate(self, pipeline):
        """Input must be a generate trigger."""
        assert "generate" in pipeline["input"]

    def test_generate_has_interval(self, pipeline):
        """Generate input must have an interval."""
        gen = pipeline["input"]["generate"]
        assert "interval" in gen

    def test_generate_interval_uses_env_var(self, pipeline):
        """Interval should reference CAPTURE_INTERVAL env var."""
        interval = pipeline["input"]["generate"]["interval"]
        assert "CAPTURE_INTERVAL" in interval

    def test_processor_count(self, pipeline):
        """Pipeline should have exactly 6 processors."""
        procs = pipeline["pipeline"]["processors"]
        assert len(procs) == 6, f"Expected 6 processors, got {len(procs)}"

    def test_processor_order(self, pipeline):
        """Processors should be in the correct order."""
        procs = pipeline["pipeline"]["processors"]
        expected = ["subprocess", "mapping", "mutation", "branch", "mapping", "mutation"]
        actual = [list(p.keys())[0] for p in procs]
        assert actual == expected, f"Expected {expected}, got {actual}"


class TestSubprocessProcessor:
    """Test the subprocess (webcam capture) processor."""

    def test_subprocess_runs_python(self, pipeline):
        proc = pipeline["pipeline"]["processors"][0]["subprocess"]
        assert proc["name"] == "python3"

    def test_subprocess_runs_capture_script(self, pipeline):
        proc = pipeline["pipeline"]["processors"][0]["subprocess"]
        assert "capture_frame.py" in proc["args"]

    def test_subprocess_has_unbuffered_flag(self, pipeline):
        proc = pipeline["pipeline"]["processors"][0]["subprocess"]
        assert "-u" in proc["args"], "Python must run unbuffered for line-by-line output"

    def test_subprocess_buffer_size(self, pipeline):
        proc = pipeline["pipeline"]["processors"][0]["subprocess"]
        assert proc["max_buffer"] == 2097152, "Buffer must be 2MB for base64 frames"


class TestBranchProcessor:
    """Test the branch processor (Gemma 4 inference)."""

    def test_branch_has_request_map(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "request_map" in branch

    def test_branch_has_result_map(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "result_map" in branch

    def test_branch_uses_http_processor(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        http_proc = branch["processors"][0]
        assert "http" in http_proc

    def test_http_verb_is_post(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        http = branch["processors"][0]["http"]
        assert http["verb"] == "POST"

    def test_http_url_uses_env_var(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        http = branch["processors"][0]["http"]
        assert "INFERENCE_URL" in http["url"]

    def test_http_timeout_is_reasonable(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        http = branch["processors"][0]["http"]
        assert http["timeout"] == "60s"

    def test_request_map_includes_model(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "GEMMA_MODEL" in branch["request_map"]

    def test_request_map_includes_vision_prompt(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "VISION_PROMPT" in branch["request_map"]

    def test_request_map_includes_image(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "image_base64" in branch["request_map"]

    def test_result_map_extracts_response(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "inference_response" in branch["result_map"]

    def test_result_map_extracts_tokens(self, pipeline):
        branch = pipeline["pipeline"]["processors"][3]["branch"]
        assert "tokens_used" in branch["result_map"]


class TestSchemaMapping:
    """Test Step 3: the Bloblang schema mapping."""

    @pytest.fixture
    def mapping_text(self, pipeline):
        return pipeline["pipeline"]["processors"][4]["mapping"]

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

    def test_has_mode(self, mapping_text):
        assert "root.mode" in mapping_text

    def test_has_processing_ms(self, mapping_text):
        assert "root.processing_ms" in mapping_text

    def test_has_payload(self, mapping_text):
        assert "root.payload" in mapping_text

    # Derived analytics
    def test_has_object_count(self, mapping_text):
        assert "root.object_count" in mapping_text

    def test_has_has_detections(self, mapping_text):
        assert "root.has_detections" in mapping_text

    # Mode-specific fields
    def test_has_labels_for_detect_modes(self, mapping_text):
        assert "root.labels" in mapping_text
        assert "detect_objects" in mapping_text
        assert "detect_shapes" in mapping_text

    def test_has_safety_fields(self, mapping_text):
        assert "root.risk_level" in mapping_text
        assert "root.safe" in mapping_text
        assert "root.alert" in mapping_text
        assert "safety_check" in mapping_text

    def test_has_extracted_text_for_read_mode(self, mapping_text):
        assert "root.extracted_text" in mapping_text
        assert "read_text" in mapping_text

    # Integrity
    def test_has_integrity_hashes(self, mapping_text):
        assert "root.integrity" in mapping_text
        assert "payload_sha256" in mapping_text
        assert "frame_sha256" in mapping_text
        assert 'hash("sha256")' in mapping_text
        assert 'encode("hex")' in mapping_text

    # Data minimization
    def test_does_not_copy_image_to_output(self, mapping_text):
        assert "root.image_base64" not in mapping_text, \
            "Raw image must not be copied to output (data minimization)"

    # Graceful error handling
    def test_has_json_parse_with_catch(self, mapping_text):
        assert "parse_json().catch" in mapping_text

    def test_uses_deleted_for_conditional_fields(self, mapping_text):
        assert "deleted()" in mapping_text


class TestMakotoAttestation:
    """Test Step 4: the Makoto L1 attestation mutation."""

    @pytest.fixture
    def mutation_text(self, pipeline):
        return pipeline["pipeline"]["processors"][5]["mutation"]

    def test_has_attestation_field(self, mutation_text):
        assert "root.attestation" in mutation_text

    def test_has_intoto_type(self, mutation_text):
        assert "https://in-toto.io/Statement/v1" in mutation_text

    def test_has_makoto_predicate_type(self, mutation_text):
        assert "https://makoto.dev/transform/v1" in mutation_text

    def test_has_subject_with_digest(self, mutation_text):
        assert '"subject"' in mutation_text
        assert '"digest"' in mutation_text

    def test_has_inputs_with_frame_digest(self, mutation_text):
        assert '"inputs"' in mutation_text
        assert "webcam-frame" in mutation_text

    def test_has_transform_type(self, mutation_text):
        assert "vision-inference" in mutation_text

    def test_has_executor_identity(self, mutation_text):
        assert "expanso-edge://" in mutation_text
        assert '"platform"' in mutation_text

    def test_has_code_ref(self, mutation_text):
        assert '"codeRef"' in mutation_text
        assert "pipeline.yaml" in mutation_text

    def test_has_metadata_timing(self, mutation_text):
        assert '"processedOn"' in mutation_text
        assert '"processingMs"' in mutation_text

    def test_references_integrity_hashes(self, mutation_text):
        """Attestation should use the integrity hashes from Step 3."""
        assert "this.integrity.payload_sha256" in mutation_text
        assert "this.integrity.frame_sha256" in mutation_text


class TestOutputBroker:
    """Test the output broker configuration."""

    def test_output_is_broker(self, pipeline):
        assert "broker" in pipeline["output"]

    def test_broker_is_fan_out(self, pipeline):
        broker = pipeline["output"]["broker"]
        assert broker["pattern"] == "fan_out"

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
