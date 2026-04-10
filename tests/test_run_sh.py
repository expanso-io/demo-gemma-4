#!/usr/bin/env python3
"""
Unit tests for run.sh

Tests the multi-modal launcher script's environment variable setup,
preflight checks, and banner output.
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


class TestEnvironmentDefaults:
    """Verify default environment variable values in run.sh."""

    @pytest.fixture
    def script_content(self):
        with open(RUN_SCRIPT) as f:
            return f.read()

    def test_default_node_id(self, script_content):
        assert "edge-cam-001" in script_content

    def test_default_inference_url(self, script_content):
        assert "http://localhost:8081" in script_content

    def test_default_capture_interval(self, script_content):
        assert "CAPTURE_INTERVAL" in script_content

    def test_default_pipeline_version(self, script_content):
        assert "2.0.0" in script_content

    def test_sets_camera_url(self, script_content):
        assert "CAMERA_URL" in script_content

    def test_sets_camera_index(self, script_content):
        assert "CAMERA_INDEX" in script_content


class TestPreflightChecks:
    """Verify run.sh checks for required tools."""

    @pytest.fixture
    def script_content(self):
        with open(RUN_SCRIPT) as f:
            return f.read()

    def test_checks_expanso_edge(self, script_content):
        assert "expanso-edge" in script_content

    def test_checks_opencv(self, script_content):
        assert "cv2" in script_content

    def test_checks_inference_health(self, script_content):
        assert "health" in script_content


class TestBannerOutput:
    """Verify the banner shows useful info."""

    @pytest.fixture
    def script_content(self):
        with open(RUN_SCRIPT) as f:
            return f.read()

    def test_shows_multi_modal_info(self, script_content):
        assert "Multi-Modal" in script_content or "multi" in script_content.lower()

    def test_mentions_four_modes(self, script_content):
        assert "DETECT" in script_content
        assert "READ" in script_content or "read" in script_content
        assert "DESCRIBE" in script_content or "describe" in script_content
        assert "SAFETY" in script_content

    def test_runs_pipeline_yaml(self, script_content):
        assert "pipeline.yaml" in script_content


class TestShellScriptSyntax:
    """Validate syntax of all shell scripts in the repo."""

    SHELL_SCRIPTS = [
        "run.sh",
        "start-server.sh",
        "watchdog.sh",
        "demo-ctl",
        "deploy.sh",
        "setup-jetson.sh",
        "mac-demo.sh",
        "run-edge.sh",
        "setup-dhcp-mac.sh",
    ]

    @pytest.mark.parametrize("script", SHELL_SCRIPTS)
    def test_shell_script_syntax(self, script):
        script_path = os.path.join(SCRIPT_DIR, script)
        if not os.path.exists(script_path):
            pytest.skip(f"{script} not found")
        result = subprocess.run(
            ["bash", "-n", script_path],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script}: {result.stderr}"

    @pytest.mark.parametrize("script", SHELL_SCRIPTS)
    def test_shell_script_is_executable(self, script):
        script_path = os.path.join(SCRIPT_DIR, script)
        if not os.path.exists(script_path):
            pytest.skip(f"{script} not found")
        assert os.access(script_path, os.X_OK), f"{script} is not executable"
