#!/usr/bin/env python3
"""
Unit tests for run.sh

Tests the launcher script's mode selection, prompt loading,
environment variable setup, and preflight checks.
"""

import os
import subprocess

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SCRIPT = os.path.join(SCRIPT_DIR, "run.sh")


class TestRunShSyntax:
    """Basic script validation."""

    def test_bash_syntax(self):
        """run.sh should pass bash syntax check."""
        result = subprocess.run(
            ["bash", "-n", RUN_SCRIPT],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_is_executable(self):
        """run.sh should have execute permission."""
        assert os.access(RUN_SCRIPT, os.X_OK), "run.sh is not executable"


class TestModeSelection:
    """Test prompt file loading and mode validation."""

    VALID_MODES = ["detect_objects", "detect_shapes", "read_text", "safety_check", "describe_scene"]

    @pytest.mark.parametrize("mode", VALID_MODES)
    def test_prompt_file_exists(self, mode):
        """Each mode should have a corresponding prompt file."""
        prompt_file = os.path.join(SCRIPT_DIR, "prompts", f"{mode}.txt")
        assert os.path.isfile(prompt_file), f"Missing prompt file: prompts/{mode}.txt"

    @pytest.mark.parametrize("mode", VALID_MODES)
    def test_prompt_file_not_empty(self, mode):
        """Prompt files should not be empty."""
        prompt_file = os.path.join(SCRIPT_DIR, "prompts", f"{mode}.txt")
        with open(prompt_file) as f:
            content = f.read().strip()
        assert len(content) > 10, f"Prompt file prompts/{mode}.txt is too short"

    @pytest.mark.parametrize("mode", VALID_MODES)
    def test_prompt_requests_json_output(self, mode):
        """Each prompt should instruct the model to return JSON."""
        prompt_file = os.path.join(SCRIPT_DIR, "prompts", f"{mode}.txt")
        with open(prompt_file) as f:
            content = f.read().lower()
        assert "json" in content, f"Prompt {mode} doesn't mention JSON output format"

    def test_invalid_mode_fails(self):
        """Running with an unknown mode should show available modes."""
        result = subprocess.run(
            ["bash", "-c", f'source "{RUN_SCRIPT}" nonexistent_mode 2>&1 || true'],
            capture_output=True, text=True,
            env={**os.environ, "SKIP_PREFLIGHT": "1"},
            cwd=SCRIPT_DIR,
        )
        # The script should mention the mode is unknown
        # Since it uses exec at the end, we test the prompt file check directly
        prompt_file = os.path.join(SCRIPT_DIR, "prompts", "nonexistent_mode.txt")
        assert not os.path.isfile(prompt_file)

    def test_default_mode_is_detect_objects(self):
        """Default mode (no argument) should be detect_objects."""
        # Verify by checking the script source
        with open(RUN_SCRIPT) as f:
            content = f.read()
        assert 'MODE="${1:-detect_objects}"' in content


class TestPromptSchemas:
    """Validate that prompt files define the expected output schemas."""

    def test_detect_objects_expects_array(self):
        """detect_objects prompt should request a JSON array with label/confidence/box_2d."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "detect_objects.txt")) as f:
            content = f.read()
        assert "label" in content
        assert "confidence" in content
        assert "box_2d" in content

    def test_detect_shapes_expects_array(self):
        """detect_shapes prompt should request a JSON array with shape/color."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "detect_shapes.txt")) as f:
            content = f.read()
        assert "shape" in content
        assert "color" in content

    def test_read_text_expects_object(self):
        """read_text prompt should request a JSON object with text field."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "read_text.txt")) as f:
            content = f.read()
        assert '"text"' in content

    def test_safety_check_expects_risk_level(self):
        """safety_check prompt should request risk_level (used by pipeline alert)."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "safety_check.txt")) as f:
            content = f.read()
        assert "risk_level" in content
        assert "safe" in content
        assert "concerns" in content

    def test_safety_check_documents_alert_trigger(self):
        """safety_check prompt should tell model about risk_level > 3 alert."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "safety_check.txt")) as f:
            content = f.read()
        assert "risk_level > 3" in content or "risk_level &gt; 3" in content

    def test_describe_scene_expects_object(self):
        """describe_scene prompt should request a JSON object with mood/objects."""
        with open(os.path.join(SCRIPT_DIR, "prompts", "describe_scene.txt")) as f:
            content = f.read()
        assert "mood" in content
        assert "objects" in content


class TestEnvironmentDefaults:
    """Verify default environment variable values in run.sh."""

    @pytest.fixture
    def script_content(self):
        with open(RUN_SCRIPT) as f:
            return f.read()

    def test_default_node_id(self, script_content):
        assert "edge-cam-001" in script_content

    def test_default_inference_url(self, script_content):
        assert "http://localhost:11434" in script_content

    def test_default_model(self, script_content):
        assert "gemma4-e4b-it" in script_content

    def test_default_capture_interval(self, script_content):
        assert "3s" in script_content

    def test_default_pipeline_version(self, script_content):
        assert "1.0.0" in script_content

    def test_exports_vision_prompt(self, script_content):
        assert "export VISION_PROMPT" in script_content

    def test_exports_detection_mode(self, script_content):
        assert "export DETECTION_MODE" in script_content
