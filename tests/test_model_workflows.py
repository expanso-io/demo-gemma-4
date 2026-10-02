import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from finetune import label_frames, review_labels


def _server(response_body: dict) -> tuple[HTTPServer, str, list[dict]]:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(size)))
            body = json.dumps(response_body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}", received


def test_local_label_request_sends_one_image(tmp_path: Path) -> None:
    content = json.dumps(
        {
            "objects": [{"label": "box", "bbox": [1, 2, 3, 4]}],
            "scene_description": "A box on a table.",
            "safety_assessment": "safe",
        }
    )
    server, url, received = _server({"choices": [{"message": {"content": content}}]})
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"jpeg bytes")
    try:
        result = label_frames.request_label(image, url, "gemma4")
    finally:
        server.shutdown()
        server.server_close()

    assert result["objects"][0]["label"] == "box"
    assert len(received) == 1
    data_url = received[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/jpeg;base64,")


def test_frame_selection_obeys_hard_run_limit(tmp_path: Path) -> None:
    for category in ("box", "person"):
        directory = tmp_path / category
        directory.mkdir()
        for index in range(5):
            (directory / f"{index}.jpg").write_bytes(b"frame")

    selected = label_frames.select_frames(tmp_path, None, 0, max_frames=3)

    assert len(selected) == 3


def test_inventory_excludes_paths_costs_and_model_names(tmp_path: Path) -> None:
    (tmp_path / "box.jsonl").write_text(
        json.dumps(
            {
                "image": "/private/frame.jpg",
                "model": "old-model",
                "cost_usd": 1.25,
                "objects": [{"label": "box"}],
                "scene_description": "A box.",
                "safety_assessment": "safe",
            }
        )
        + "\n"
    )

    inventory = review_labels.build_inventory(tmp_path)

    assert inventory == {
        "total_records": 1,
        "categories": {
            "box": {
                "records": 1,
                "object_labels": {"box": 1},
                "scene_descriptions": 1,
                "safe": 1,
                "alerts": 0,
                "errors": 0,
            }
        },
    }


def test_review_uses_one_named_gateway_request() -> None:
    server, url, received = _server(
        {
            "status": "ok",
            "source": "fixture",
            "backend": "gemini",
            "text": "# Inventory",
        }
    )
    try:
        result = review_labels.ask_gateway({"total_records": 4}, url)
    finally:
        server.shutdown()
        server.server_close()

    assert result["source"] == "fixture"
    assert len(received) == 1
    assert received[0]["fixture"] == review_labels.FIXTURE_NAME
