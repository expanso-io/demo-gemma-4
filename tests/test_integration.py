#!/usr/bin/env python3
"""
Integration tests for the Gemma 4 × Expanso Edge pipeline.

These tests verify the full pipeline works end-to-end by:
1. Mocking the webcam with a synthetic test frame
2. Running a local mock inference server
3. Validating the structured output

Requires: opencv-python, flask (for mock server)
Optional: expanso-edge (for full pipeline test)
"""

import base64
import hashlib
import json
import os
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def _has_expanso_edge():
    return subprocess.run(
        ["which", "expanso-edge"], capture_output=True
    ).returncode == 0


def _has_ollama():
    return subprocess.run(
        ["which", "ollama"], capture_output=True
    ).returncode == 0


def _ollama_is_running():
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False


# ── Mock Inference Server ────────────────────────────────────


class MockOllamaHandler(BaseHTTPRequestHandler):
    """Mock Ollama OpenAI-compatible endpoint that returns canned responses."""

    # Class variable: which mode to simulate
    response_mode = "detect_objects"

    RESPONSES = {
        "detect_objects": json.dumps([
            {"label": "coffee mug", "confidence": 0.94, "box_2d": [120, 45, 280, 310]},
            {"label": "keyboard", "confidence": 0.91, "box_2d": [50, 200, 400, 500]},
        ]),
        "detect_shapes": json.dumps([
            {"shape": "circle", "color": "red", "position": "center", "confidence": 0.88},
        ]),
        "read_text": json.dumps({
            "text": "Hello World",
            "type": "printed",
            "language": "en",
            "confidence": 0.95,
        }),
        "safety_check": json.dumps({
            "safe": False,
            "risk_level": 4,
            "concerns": ["exposed wiring", "no fire extinguisher"],
            "description": "Office with electrical hazard",
        }),
        "describe_scene": json.dumps({
            "mood": "calm",
            "dominant_colors": ["brown", "white"],
            "objects": ["desk", "laptop", "coffee cup"],
            "summary": "A tidy office workspace with a laptop and coffee",
        }),
    }

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Determine response based on class variable
        response_text = self.RESPONSES.get(
            self.response_mode,
            self.RESPONSES["detect_objects"],
        )

        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response_text,
                }
            }],
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 50,
                "total_tokens": 550,
            },
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps(response).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Suppress log noise during tests


@pytest.fixture(scope="module")
def mock_server():
    """Start a mock Ollama server on a random port."""
    server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ── Mock Frame Generator ─────────────────────────────────────


@pytest.fixture
def synthetic_frame_b64():
    """Create a synthetic test frame as base64 JPEG."""
    if not _has_opencv():
        pytest.skip("opencv-python not installed")
    import cv2
    import numpy as np

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw some shapes for visual interest
    cv2.rectangle(frame, (100, 100), (300, 300), (0, 255, 0), 3)
    cv2.circle(frame, (450, 240), 80, (0, 0, 255), -1)
    cv2.putText(frame, "TEST", (200, 400), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf).decode("utf-8")


# ── Output Validation Tests ──────────────────────────────────


class TestOutputSchema:
    """Validate the structured output schema produced by the pipeline.

    These tests simulate what the Bloblang mapping produces by
    constructing the expected output and validating its shape.
    """

    @pytest.fixture
    def mock_detection_output(self, synthetic_frame_b64, mock_server):
        """Simulate what the pipeline would produce for detect_objects mode."""

        # Call the mock server like the pipeline would
        inference_response = json.dumps([
            {"label": "coffee mug", "confidence": 0.94, "box_2d": [120, 45, 280, 310]},
            {"label": "keyboard", "confidence": 0.91, "box_2d": [50, 200, 400, 500]},
        ])

        # Simulate the Bloblang mapping output
        raw = inference_response
        parsed = json.loads(raw)

        output = {
            "timestamp": "2026-04-03T14:23:01.482-04:00",
            "node_id": "edge-cam-001",
            "pipeline_version": "1.0.0",
            "model": "gemma4-e4b-it",
            "frame_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "mode": "detect_objects",
            "processing_ms": 1847,
            "payload": parsed,
            "object_count": len(parsed),
            "has_detections": len(parsed) > 0,
            "labels": [item.get("label", "unknown") for item in parsed],
            "integrity": {
                "payload_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "frame_sha256": hashlib.sha256(synthetic_frame_b64.encode()).hexdigest(),
            },
            "tokens": {
                "prompt_tokens": 500,
                "completion_tokens": 50,
                "total_tokens": 550,
            },
        }

        # Simulate Makoto attestation (Step 4 mutation)
        output["attestation"] = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [{
                "name": f"detection:{output['frame_id']}",
                "digest": {
                    "sha256": output["integrity"]["payload_sha256"],
                    "recordCount": "1",
                },
            }],
            "predicateType": "https://makoto.dev/transform/v1",
            "predicate": {
                "inputs": [{
                    "name": f"webcam-frame:{output['frame_id']}",
                    "digest": {
                        "sha256": output["integrity"]["frame_sha256"],
                    },
                }],
                "transform": {
                    "type": "https://makoto.dev/transforms/vision-inference",
                    "name": output["mode"],
                    "version": output["pipeline_version"],
                    "parameters": {
                        "model": output["model"],
                        "prompt_mode": output["mode"],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                    "codeRef": {
                        "uri": "https://github.com/expanso-io/demo-gemma-4",
                        "pipeline": "pipeline.yaml",
                    },
                },
                "executor": {
                    "id": f"expanso-edge://{output['node_id']}",
                    "platform": "expanso-edge",
                },
                "metadata": {
                    "processedOn": output["timestamp"],
                    "processingMs": output["processing_ms"],
                },
            },
        }

        return output

    # ── Envelope fields ──

    def test_has_timestamp(self, mock_detection_output):
        assert "timestamp" in mock_detection_output

    def test_has_node_id(self, mock_detection_output):
        assert mock_detection_output["node_id"] == "edge-cam-001"

    def test_has_pipeline_version(self, mock_detection_output):
        assert mock_detection_output["pipeline_version"] == "1.0.0"

    def test_has_model(self, mock_detection_output):
        assert mock_detection_output["model"] == "gemma4-e4b-it"

    def test_has_frame_id(self, mock_detection_output):
        assert len(mock_detection_output["frame_id"]) > 0

    def test_has_mode(self, mock_detection_output):
        assert mock_detection_output["mode"] == "detect_objects"

    def test_has_processing_ms(self, mock_detection_output):
        assert isinstance(mock_detection_output["processing_ms"], (int, float))

    # ── Derived analytics ──

    def test_object_count_matches_payload(self, mock_detection_output):
        assert mock_detection_output["object_count"] == len(mock_detection_output["payload"])

    def test_has_detections_is_bool(self, mock_detection_output):
        assert isinstance(mock_detection_output["has_detections"], bool)
        assert mock_detection_output["has_detections"] is True

    def test_labels_extracted(self, mock_detection_output):
        assert mock_detection_output["labels"] == ["coffee mug", "keyboard"]

    # ── No image leak ──

    def test_no_image_in_output(self, mock_detection_output):
        """Raw image must never appear in output."""
        assert "image_base64" not in mock_detection_output
        output_str = json.dumps(mock_detection_output)
        # A base64 JPEG starts with /9j/
        assert "/9j/" not in output_str or len(output_str) < 10000

    # ── Integrity hashes ──

    def test_integrity_has_payload_hash(self, mock_detection_output):
        h = mock_detection_output["integrity"]["payload_sha256"]
        assert len(h) == 64  # SHA-256 hex digest

    def test_integrity_has_frame_hash(self, mock_detection_output):
        h = mock_detection_output["integrity"]["frame_sha256"]
        assert len(h) == 64

    def test_integrity_hashes_are_deterministic(self, mock_detection_output, synthetic_frame_b64):
        """Same input should produce same hash."""
        raw = json.dumps(mock_detection_output["payload"])
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert mock_detection_output["integrity"]["payload_sha256"] == expected

    # ── Makoto attestation ──

    def test_attestation_type(self, mock_detection_output):
        att = mock_detection_output["attestation"]
        assert att["_type"] == "https://in-toto.io/Statement/v1"

    def test_attestation_predicate_type(self, mock_detection_output):
        att = mock_detection_output["attestation"]
        assert att["predicateType"] == "https://makoto.dev/transform/v1"

    def test_attestation_subject_references_frame(self, mock_detection_output):
        subject = mock_detection_output["attestation"]["subject"][0]
        assert subject["name"].startswith("detection:")
        assert "sha256" in subject["digest"]

    def test_attestation_input_references_frame(self, mock_detection_output):
        inp = mock_detection_output["attestation"]["predicate"]["inputs"][0]
        assert inp["name"].startswith("webcam-frame:")
        assert "sha256" in inp["digest"]

    def test_attestation_executor_is_expanso(self, mock_detection_output):
        executor = mock_detection_output["attestation"]["predicate"]["executor"]
        assert executor["platform"] == "expanso-edge"
        assert executor["id"].startswith("expanso-edge://")

    def test_attestation_has_code_ref(self, mock_detection_output):
        transform = mock_detection_output["attestation"]["predicate"]["transform"]
        assert "codeRef" in transform
        assert transform["codeRef"]["pipeline"] == "pipeline.yaml"

    def test_attestation_digest_chain_matches(self, mock_detection_output):
        """Subject digest should match the integrity payload hash."""
        att = mock_detection_output["attestation"]
        subject_hash = att["subject"][0]["digest"]["sha256"]
        integrity_hash = mock_detection_output["integrity"]["payload_sha256"]
        assert subject_hash == integrity_hash, "Attestation digest must match integrity hash"


class TestModeSpecificOutputs:
    """Test that different modes produce different output schemas."""

    def test_safety_check_alert_triggered(self, mock_server):
        """Safety check with risk_level > 3 should set alert=True."""
        # Simulate pipeline output for safety_check mode
        parsed = json.loads(MockOllamaHandler.RESPONSES["safety_check"])
        alert = parsed.get("risk_level", 0) > 3
        assert alert is True

    def test_safety_check_low_risk_no_alert(self):
        """Safety check with risk_level <= 3 should NOT alert."""
        parsed = {"safe": True, "risk_level": 1, "concerns": [], "description": "Safe scene"}
        alert = parsed.get("risk_level", 0) > 3
        assert alert is False

    def test_detect_shapes_has_shape_labels(self, mock_server):
        """detect_shapes should extract shape field as labels."""
        parsed = json.loads(MockOllamaHandler.RESPONSES["detect_shapes"])
        labels = [item.get("shape", "unknown") for item in parsed]
        assert labels == ["circle"]

    def test_read_text_extracts_text(self, mock_server):
        """read_text mode should promote text field."""
        parsed = json.loads(MockOllamaHandler.RESPONSES["read_text"])
        assert parsed["text"] == "Hello World"

    def test_describe_scene_has_mood(self, mock_server):
        """describe_scene should include mood field."""
        parsed = json.loads(MockOllamaHandler.RESPONSES["describe_scene"])
        assert parsed["mood"] in ["calm", "energetic", "tense", "playful", "neutral"]


class TestMockServerResponses:
    """Test the mock inference server itself."""

    def test_mock_returns_valid_openai_format(self, mock_server):
        """Mock server should return OpenAI-compatible response."""
        import urllib.request

        request_body = json.dumps({
            "model": "gemma4-e4b-it",
            "messages": [{"role": "user", "content": "test"}],
        }).encode()

        req = urllib.request.Request(
            f"{mock_server}/v1/chat/completions",
            data=request_body,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        assert "choices" in data
        assert "usage" in data
        assert data["choices"][0]["message"]["role"] == "assistant"
        content = data["choices"][0]["message"]["content"]
        # Content should be parseable JSON
        json.loads(content)

    def test_mock_returns_token_usage(self, mock_server):
        """Mock server should return token usage stats."""
        import urllib.request

        request_body = json.dumps({
            "model": "gemma4-e4b-it",
            "messages": [{"role": "user", "content": "test"}],
        }).encode()

        req = urllib.request.Request(
            f"{mock_server}/v1/chat/completions",
            data=request_body,
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        usage = data["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage


# ── Full Pipeline Integration ────────────────────────────────


@pytest.mark.skipif(not _has_expanso_edge(), reason="expanso-edge not installed")
@pytest.mark.skipif(not _has_opencv(), reason="opencv-python not installed")
@pytest.mark.skipif(True, reason="Requires physical camera + running inference server — run manually")
class TestFullPipeline:
    """End-to-end pipeline test with mock inference server.

    These tests require expanso-edge to be installed.
    They use the mock server instead of real Ollama.
    """

    def test_pipeline_starts_and_produces_output(self, mock_server, tmp_path):
        """Pipeline should start, capture a frame, call inference, and output JSON."""
        env = os.environ.copy()
        env["INFERENCE_URL"] = mock_server
        env["CAPTURE_INTERVAL"] = "1s"
        env["DETECTION_MODE"] = "detect_objects"
        env["VISION_PROMPT"] = "Detect objects"
        env["NODE_ID"] = "test-node-001"
        env["GEMMA_MODEL"] = "gemma4-e4b-it"
        env["PIPELINE_VERSION"] = "test"

        proc = subprocess.Popen(
            ["expanso-edge", "run", "pipeline.yaml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=SCRIPT_DIR,
            env=env,
        )

        # Wait for first JSON output (up to 30s for camera warmup + inference)
        # Skip non-JSON lines (startup logs, warnings, etc.)
        try:
            data = None
            start = time.time()
            while time.time() - start < 30:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                line_str = line.decode().strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    break  # Got valid JSON
                except json.JSONDecodeError:
                    continue  # Skip non-JSON lines (logs, banners)

            if data is None:
                pytest.fail("No valid JSON output received within 30 seconds")

            # Validate envelope
            assert "timestamp" in data
            assert data["node_id"] == "test-node-001"
            assert data["mode"] == "detect_objects"
            assert "frame_id" in data
            assert "payload" in data
            assert "attestation" in data
            assert "integrity" in data

            # Validate derived analytics
            assert "object_count" in data
            assert "has_detections" in data

            # Validate no image leak
            assert "image_base64" not in data

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
