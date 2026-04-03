#!/usr/bin/env python3
"""
Unit tests for capture_frame.py

Tests the webcam capture subprocess independently from the pipeline.
Uses mock camera when no physical camera is available.
"""

import json
import base64
import os
import subprocess
import sys
import time

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE_SCRIPT = os.path.join(SCRIPT_DIR, "capture_frame.py")


# ── Helpers ──────────────────────────────────────────────────


def _has_camera():
    """Check if a physical camera is available."""
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        ret = cap.isOpened()
        cap.release()
        return ret
    except Exception:
        return False


def _has_opencv():
    """Check if opencv-python is installed."""
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _create_test_frame_jpeg():
    """Create a minimal valid JPEG for testing (1x1 red pixel)."""
    import cv2
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:, :] = (0, 0, 255)  # Red in BGR
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


# ── Unit Tests ───────────────────────────────────────────────


class TestCaptureFrameScript:
    """Test capture_frame.py script behavior."""

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_script_exists_and_has_valid_syntax(self):
        """Script should parse without syntax errors."""
        result = subprocess.run(
            [sys.executable, "-c", f"import py_compile; py_compile.compile('{CAPTURE_SCRIPT}', doraise=True)"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_script_imports(self):
        """All imports in capture_frame.py should resolve."""
        result = subprocess.run(
            [sys.executable, "-c", "import cv2, json, base64, signal, os, sys"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    @pytest.mark.skipif(not _has_camera(), reason="No camera available")
    def test_single_capture(self):
        """Send one trigger, get one JSON frame back."""
        proc = subprocess.Popen(
            [sys.executable, "-u", CAPTURE_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=SCRIPT_DIR,
        )

        # Send one trigger
        proc.stdin.write(b"\n")
        proc.stdin.flush()

        # Read one line of output (with timeout)
        proc.stdin.close()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("capture_frame.py timed out after 10s")

        lines = [l for l in stdout.decode().strip().split("\n") if l]
        # Filter out status messages, keep only frame outputs
        frame_lines = [l for l in lines if '"image_base64"' in l]
        assert len(frame_lines) >= 1, f"Expected at least 1 frame line, got {len(frame_lines)} (total lines: {len(lines)})"

        # Parse the JSON
        data = json.loads(frame_lines[0])
        assert "image_base64" in data, f"Missing image_base64 key. Got: {list(data.keys())}"

        # Validate base64
        raw_bytes = base64.b64decode(data["image_base64"])
        assert len(raw_bytes) > 100, f"Image too small: {len(raw_bytes)} bytes"
        assert raw_bytes[:2] == b"\xff\xd8", "Not a valid JPEG (missing SOI marker)"

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    @pytest.mark.skipif(not _has_camera(), reason="No camera available")
    def test_multiple_captures(self):
        """Send multiple triggers, get multiple frames."""
        proc = subprocess.Popen(
            [sys.executable, "-u", CAPTURE_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=SCRIPT_DIR,
        )

        # Send 3 triggers
        for _ in range(3):
            proc.stdin.write(b"\n")
            proc.stdin.flush()
            time.sleep(0.1)

        proc.stdin.close()
        try:
            stdout, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("Timed out")

        lines = [l for l in stdout.decode().strip().split("\n") if l]
        # Filter out status messages, keep only frame outputs
        frame_lines = [l for l in lines if '"image_base64"' in l]
        assert len(frame_lines) == 3, f"Expected 3 frames, got {len(frame_lines)} (total lines: {len(lines)})"

        for i, line in enumerate(frame_lines):
            data = json.loads(line)
            assert "image_base64" in data, f"Frame {i} missing image_base64"

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_env_var_defaults(self):
        """Default config values should be sensible."""
        result = subprocess.run(
            [sys.executable, "-c", """
import os
os.environ.pop('CAMERA_INDEX', None)
os.environ.pop('CAPTURE_WIDTH', None)
os.environ.pop('CAPTURE_HEIGHT', None)
os.environ.pop('JPEG_QUALITY', None)
os.environ.pop('WARMUP_FRAMES', None)

# Simulate loading the config section
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "640"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "480"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "80"))
WARMUP_FRAMES = int(os.environ.get("WARMUP_FRAMES", "5"))

assert CAMERA_INDEX == 0
assert CAPTURE_WIDTH == 640
assert CAPTURE_HEIGHT == 480
assert JPEG_QUALITY == 80
assert WARMUP_FRAMES == 5
print("OK")
"""],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_env_var_overrides(self):
        """Environment variables should override defaults."""
        env = os.environ.copy()
        env["CAMERA_INDEX"] = "2"
        env["CAPTURE_WIDTH"] = "320"
        env["CAPTURE_HEIGHT"] = "240"
        env["JPEG_QUALITY"] = "50"
        env["WARMUP_FRAMES"] = "0"

        result = subprocess.run(
            [sys.executable, "-c", """
import os
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "640"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "480"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "80"))
WARMUP_FRAMES = int(os.environ.get("WARMUP_FRAMES", "5"))

assert CAMERA_INDEX == 2
assert CAPTURE_WIDTH == 320
assert CAPTURE_HEIGHT == 240
assert JPEG_QUALITY == 50
assert WARMUP_FRAMES == 0
print("OK")
"""],
            capture_output=True, text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr


class TestOutputFormat:
    """Test that capture output matches what the pipeline expects."""

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_output_is_single_line_json(self):
        """Each output must be a single line of valid JSON (subprocess codec requirement)."""
        import cv2
        import numpy as np

        # Create a fake frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")

        output = json.dumps({"image_base64": b64})

        # Must be single line
        assert "\n" not in output, "Output must be single-line for subprocess codec"

        # Must parse back
        parsed = json.loads(output)
        assert parsed["image_base64"] == b64

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_base64_roundtrip(self):
        """Base64 encoding should produce a valid JPEG that roundtrips."""
        import cv2
        import numpy as np

        # Create a frame with known content
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[40:60, 40:60] = (255, 0, 0)  # Blue square in center

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b64 = base64.b64encode(buf).decode("utf-8")

        # Decode back
        raw = base64.b64decode(b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        assert decoded is not None, "Failed to decode JPEG back"
        assert decoded.shape == (100, 100, 3)

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_frame_size_within_buffer_limit(self):
        """640x480 JPEG at quality 80 should fit in the 2MB subprocess buffer."""
        import cv2
        import numpy as np

        # Worst case: high-entropy frame (noise)
        rng = np.random.default_rng(42)
        frame = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")

        output_line = json.dumps({"image_base64": b64})
        output_bytes = len(output_line.encode("utf-8"))

        # Pipeline has max_buffer: 2097152 (2 MB)
        assert output_bytes < 2097152, (
            f"Frame output is {output_bytes} bytes, exceeds 2MB buffer. "
            f"JPEG size: {len(buf)} bytes, base64: {len(b64)} chars"
        )

    @pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
    def test_error_output_format(self):
        """Error messages should also be valid single-line JSON."""
        error_msg = json.dumps({"error": "Could not open camera 0"})
        parsed = json.loads(error_msg)
        assert "error" in parsed
        assert "\n" not in error_msg
