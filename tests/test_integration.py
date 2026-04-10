#!/usr/bin/env python3
"""
Integration tests for the Gemma 4 × Expanso Edge pipeline.

Tests validate the multi-modal output schema (detect, read, describe, safety)
and the mock inference server used for development.
"""

import base64
import hashlib
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


# ── Mock Inference Server ────────────────────────────────────


class MockGemmaHandler(BaseHTTPRequestHandler):
    """Mock llama.cpp / Ollama OpenAI-compatible endpoint."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Detect which mode based on the prompt text
        prompt_text = ""
        for msg in request.get("messages", []):
            if isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if item.get("type") == "text":
                        prompt_text += item.get("text", "")
            elif isinstance(msg.get("content"), str):
                prompt_text += msg["content"]

        if "visible" in prompt_text and "CSV" in prompt_text:
            response_text = "person, bottle"
        elif "Read all text" in prompt_text:
            response_text = "Dasani, Purified Water"
        elif "Describe this scene" in prompt_text:
            response_text = "A person holds a water bottle at a desk"
        elif "safe" in prompt_text.lower():
            response_text = "safe"
        else:
            response_text = "none"

        response = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response_text,
                }
            }],
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 20,
                "total_tokens": 520,
            },
        }

        resp_body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    """Start a mock inference server on a random port."""
    server = HTTPServer(("127.0.0.1", 0), MockGemmaHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def synthetic_frame_b64():
    """Create a synthetic test frame as base64 JPEG."""
    if not _has_opencv():
        pytest.skip("opencv-python not installed")
    import cv2
    import numpy as np

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(frame, (50, 50), (150, 150), (0, 255, 0), 3)
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(buf).decode("utf-8")


# ── Output Schema Validation ────────────────────────────────


class TestMultiModalOutputSchema:
    """Validate the multi-modal output envelope structure.

    Simulates what the Bloblang mapping in pipeline.yaml produces.
    """

    @pytest.fixture
    def mock_output(self, synthetic_frame_b64):
        """Build a mock multi-modal pipeline output."""
        frame_hash = hashlib.sha256(synthetic_frame_b64.encode()).hexdigest()

        return {
            "timestamp": "2026-04-07T14:23:01.482-04:00",
            "node_id": "edge-cam-001",
            "pipeline_version": "2.0.0",
            "model": "gemma4-e2b-q4",
            "frame_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "mode": "multi",
            "detect": {
                "labels": ["person", "bottle"],
                "count": 2,
                "ms": 1847,
                "tokens": 42,
            },
            "read_text": {
                "text": "Dasani, Purified Water",
                "ms": 1203,
                "tokens": 38,
            },
            "describe": {
                "summary": "A person holds a water bottle at a desk",
                "ms": 982,
                "tokens": 35,
            },
            "safety": {
                "safe": True,
                "risk": 1,
                "detail": "safe",
                "ms": 641,
                "tokens": 28,
            },
            "total_ms": 4673,
            "total_tokens": 143,
            "integrity": {
                "frame_sha256": frame_hash,
            },
            "attestation": {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [{
                    "name": "multimodal:a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "digest": {"sha256": frame_hash, "recordCount": "4"},
                }],
                "predicateType": "https://makoto.dev/transform/v1",
                "predicate": {
                    "inputs": [{
                        "name": "webcam-frame:a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "digest": {"sha256": frame_hash},
                    }],
                    "transform": {
                        "type": "https://makoto.dev/transforms/vision-inference",
                        "name": "multi-modal",
                        "version": "2.0.0",
                        "parameters": {
                            "model": "gemma4-e2b-q4",
                            "modes": ["detect", "read_text", "describe", "safety"],
                            "temperature": 0.1,
                        },
                        "codeRef": {
                            "uri": "https://github.com/expanso-io/demo-gemma-4",
                            "pipeline": "pipeline.yaml",
                        },
                    },
                    "executor": {
                        "id": "expanso-edge://edge-cam-001",
                        "platform": "expanso-edge",
                    },
                    "metadata": {
                        "processedOn": "2026-04-07T14:23:01.482-04:00",
                        "processingMs": 4673,
                    },
                },
            },
        }

    # ── Envelope ──

    def test_has_timestamp(self, mock_output):
        assert "timestamp" in mock_output

    def test_has_node_id(self, mock_output):
        assert mock_output["node_id"] == "edge-cam-001"

    def test_has_pipeline_version(self, mock_output):
        assert mock_output["pipeline_version"] == "2.0.0"

    def test_has_model(self, mock_output):
        assert "gemma4" in mock_output["model"]

    def test_mode_is_multi(self, mock_output):
        assert mock_output["mode"] == "multi"

    # ── Four analyses ──

    def test_detect_has_labels(self, mock_output):
        assert isinstance(mock_output["detect"]["labels"], list)
        assert mock_output["detect"]["count"] == len(mock_output["detect"]["labels"])

    def test_read_text_has_text(self, mock_output):
        assert isinstance(mock_output["read_text"]["text"], str)

    def test_describe_has_summary(self, mock_output):
        assert isinstance(mock_output["describe"]["summary"], str)

    def test_safety_has_safe_flag(self, mock_output):
        assert isinstance(mock_output["safety"]["safe"], bool)

    def test_safety_has_risk_level(self, mock_output):
        assert isinstance(mock_output["safety"]["risk"], int)

    # ── Timing ──

    def test_all_analyses_have_ms(self, mock_output):
        for key in ["detect", "read_text", "describe", "safety"]:
            assert "ms" in mock_output[key], f"{key} missing ms timing"

    def test_all_analyses_have_tokens(self, mock_output):
        for key in ["detect", "read_text", "describe", "safety"]:
            assert "tokens" in mock_output[key], f"{key} missing token count"

    def test_total_ms_is_sum(self, mock_output):
        expected = sum(mock_output[k]["ms"] for k in ["detect", "read_text", "describe", "safety"])
        assert mock_output["total_ms"] == expected

    def test_total_tokens_is_sum(self, mock_output):
        expected = sum(mock_output[k]["tokens"] for k in ["detect", "read_text", "describe", "safety"])
        assert mock_output["total_tokens"] == expected

    # ── No image leak ──

    def test_no_image_in_output(self, mock_output):
        assert "image_base64" not in mock_output

    # ── Integrity ──

    def test_has_frame_sha256(self, mock_output):
        h = mock_output["integrity"]["frame_sha256"]
        assert len(h) == 64

    # ── Makoto attestation ──

    def test_attestation_type(self, mock_output):
        assert mock_output["attestation"]["_type"] == "https://in-toto.io/Statement/v1"

    def test_attestation_predicate_type(self, mock_output):
        assert mock_output["attestation"]["predicateType"] == "https://makoto.dev/transform/v1"

    def test_attestation_subject_references_multimodal(self, mock_output):
        subject = mock_output["attestation"]["subject"][0]
        assert subject["name"].startswith("multimodal:")
        assert subject["digest"]["recordCount"] == "4"

    def test_attestation_executor_is_expanso(self, mock_output):
        executor = mock_output["attestation"]["predicate"]["executor"]
        assert executor["platform"] == "expanso-edge"
        assert executor["id"].startswith("expanso-edge://")

    def test_attestation_lists_all_modes(self, mock_output):
        modes = mock_output["attestation"]["predicate"]["transform"]["parameters"]["modes"]
        assert set(modes) == {"detect", "read_text", "describe", "safety"}

    def test_attestation_has_code_ref(self, mock_output):
        transform = mock_output["attestation"]["predicate"]["transform"]
        assert transform["codeRef"]["pipeline"] == "pipeline.yaml"


class TestMockServerResponses:
    """Test the mock inference server itself."""

    def test_mock_returns_valid_openai_format(self, mock_server):
        import urllib.request

        request_body = json.dumps({
            "model": "gemma4",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Which are visible? CSV"},
            ]}],
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

    def test_mock_returns_token_usage(self, mock_server):
        import urllib.request

        request_body = json.dumps({
            "model": "gemma4",
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
        assert "total_tokens" in usage
        assert usage["total_tokens"] > 0
