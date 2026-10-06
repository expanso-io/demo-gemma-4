#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tiny HTTP sidecar that a fixture pipeline calls during a local replay."""

from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:
        return


HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
