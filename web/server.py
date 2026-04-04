#!/usr/bin/env python3
"""
Gemma 4 × Expanso Edge — Live Dashboard Server

Standalone web server that displays pipeline output in real-time.
- Watches the JSONL detection output and streams via SSE
- Grabs camera snapshots directly from RTSP for display
- Receives POST from pipeline for lowest-latency streaming

Usage:
    python3 web/server.py

    # With camera (set CAMERA_URL env var to your RTSP stream):
    CAMERA_URL=<your-rtsp-url> python3 web/server.py

    # Custom port:
    PORT=9090 python3 web/server.py
"""

import glob
import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from queue import Queue, Empty

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ── Configuration ──────────────────────────────────────────
PORT = int(os.environ.get("PORT", "9090"))
CAMERA_URL = os.environ.get("CAMERA_URL", "")
DETECTIONS_DIR = os.environ.get("DETECTIONS_DIR",
    str(Path(__file__).parent.parent / "detections"))
STATIC_DIR = str(Path(__file__).parent / "static")

# ── Shared State ───────────────────────────────────────────
latest_frame_jpg = None
frame_lock = threading.Lock()
sse_clients = []
sse_lock = threading.Lock()
recent_detections = []
MAX_HISTORY = 50


def broadcast_detection(data: dict):
    """Send a detection to all connected SSE clients."""
    msg = f"data: {json.dumps(data)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)

    recent_detections.insert(0, data)
    while len(recent_detections) > MAX_HISTORY:
        recent_detections.pop()


# ── Camera Thread ──────────────────────────────────────────
def camera_loop():
    global latest_frame_jpg
    if not HAS_CV2 or not CAMERA_URL:
        return

    while True:
        try:
            cap = cv2.VideoCapture(CAMERA_URL)
            if not cap.isOpened():
                print(f"[camera] Cannot open {CAMERA_URL}, retrying in 5s...")
                time.sleep(5)
                continue

            print(f"[camera] Connected to {CAMERA_URL}")
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[camera] Lost frame, reconnecting...")
                    break
                _, buf = cv2.imencode(".jpg", frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 75])
                with frame_lock:
                    latest_frame_jpg = buf.tobytes()
                time.sleep(0.5)  # 2 FPS for display
            cap.release()
        except Exception as e:
            print(f"[camera] Error: {e}, retrying in 5s...")
            time.sleep(5)


# ── JSONL Watcher Thread ──────────────────────────────────
def jsonl_watcher():
    """Watch detections/ dir for new JSONL lines."""
    last_pos = {}
    while True:
        try:
            files = sorted(glob.glob(os.path.join(DETECTIONS_DIR, "*.jsonl")))
            if not files:
                time.sleep(1)
                continue

            f_path = files[-1]  # Latest file
            if f_path not in last_pos:
                # Start from end of file
                last_pos[f_path] = os.path.getsize(f_path)

            size = os.path.getsize(f_path)
            if size > last_pos[f_path]:
                with open(f_path, "r") as f:
                    f.seek(last_pos[f_path])
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                broadcast_detection(data)
                            except json.JSONDecodeError:
                                pass
                    last_pos[f_path] = f.tell()
        except Exception as e:
            print(f"[watcher] Error: {e}")
        time.sleep(0.5)


# ── HTTP Handler ───────────────────────────────────────────
class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif self.path == "/api/stream":
            self._handle_sse()
        elif self.path == "/api/snapshot":
            self._handle_snapshot()
        elif self.path == "/api/history":
            self._handle_history()
        elif self.path.startswith("/static/"):
            fname = self.path[8:]
            self._serve_file(fname)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/detection":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                broadcast_detection(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception:
                self.send_error(400)
        else:
            self.send_error(404)

    def _serve_file(self, name, content_type=None):
        fpath = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        if not content_type:
            if name.endswith(".html"):
                content_type = "text/html"
            elif name.endswith(".css"):
                content_type = "text/css"
            elif name.endswith(".js"):
                content_type = "application/javascript"
            else:
                content_type = "application/octet-stream"
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = Queue()
        with sse_lock:
            sse_clients.append(q)

        try:
            # Send recent history as initial burst
            for det in reversed(recent_detections[-10:]):
                self.wfile.write(f"data: {json.dumps(det)}\n\n".encode())
            self.wfile.flush()

            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except Empty:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)

    def _handle_snapshot(self):
        with frame_lock:
            jpg = latest_frame_jpg
        if jpg is None:
            self.send_error(204, "No frame available")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpg)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(jpg)

    def _handle_history(self):
        body = json.dumps(recent_detections[:MAX_HISTORY]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ThreadedHTTPServer(HTTPServer):
    """Handle requests in separate threads."""
    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle,
                             args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def main():
    # Start background threads
    if CAMERA_URL and HAS_CV2:
        t = threading.Thread(target=camera_loop, daemon=True)
        t.start()
        print(f"[camera] Streaming from {CAMERA_URL}")
    else:
        print("[camera] No CAMERA_URL set or opencv not installed — snapshots disabled")

    t = threading.Thread(target=jsonl_watcher, daemon=True)
    t.start()
    print(f"[watcher] Watching {DETECTIONS_DIR}/ for JSONL output")

    server = ThreadedHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  SSE stream: http://localhost:{PORT}/api/stream")
    print(f"  Snapshot:   http://localhost:{PORT}/api/snapshot\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
