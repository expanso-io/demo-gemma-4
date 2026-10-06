#!/usr/bin/env -S uv run -s
"""Deterministic local inference and dashboard receipt service for CI."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RESPONSES = {
    "Which of these objects": "person, bottle",
    "Read all text": "GEMMA 4",
    "Describe this scene": "A person holds a bottle beside an edge camera.",
    "Is this scene safe": "safe",
}


def build_handler(receipt_path: Path):
    class Handler(BaseHTTPRequestHandler):
        inference_count = 0

        def log_message(self, format_string, *args):
            return

        def do_GET(self):
            if self.path == "/health":
                self._json({"status": "ok"})
                return
            self.send_error(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self.send_error(400)
                return

            if self.path == "/api/detection":
                receipt_path.write_text(json.dumps(payload, indent=2) + "\n")
                self._json({"ok": True})
                return

            if self.path != "/v1/chat/completions":
                self.send_error(404)
                return

            prompt = payload["messages"][0]["content"][0]["text"]
            answer = next(
                (value for prefix, value in RESPONSES.items() if prefix in prompt),
                None,
            )
            if answer is None:
                self._json({"error": "unrecognized fixture prompt"}, 422)
                return

            Handler.inference_count += 1
            self._json(
                {
                    "choices": [{"message": {"content": answer}}],
                    "usage": {"total_tokens": len(answer.split())},
                }
            )

        def _json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18154)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        build_handler(args.receipt.resolve()),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
