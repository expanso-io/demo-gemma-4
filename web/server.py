#!/usr/bin/env python3
"""
Gemma 4 × Expanso Edge — Live Dashboard + Recording Server

Standalone web server that displays pipeline output in real-time
and supports recording camera frames organized by object label
for fine-tuning dataset creation.

Usage:
    python3 web/server.py

    # With camera:
    CAMERA_URL=<your-rtsp-url> python3 web/server.py

    # Custom port:
    PORT=9090 python3 web/server.py
"""

import glob
import json
import os
import threading
import time
from datetime import datetime
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
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
DETECTIONS_DIR = os.environ.get("DETECTIONS_DIR",
    str(Path(__file__).parent.parent / "detections"))
STATIC_DIR = str(Path(__file__).parent / "static")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR",
    str(Path(__file__).parent.parent / "recordings"))

# ── Shared State ───────────────────────────────────────────
latest_frame_jpg = None
latest_frame_raw = None  # Raw cv2 frame for recording at full quality
frame_lock = threading.Lock()
sse_clients = []
sse_lock = threading.Lock()
recent_detections = []
MAX_HISTORY = 20

# Recording state
recording_lock = threading.Lock()
recording_active = False
recording_label = ""
recording_count = 0
recording_session_dir = ""


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
    global latest_frame_jpg, latest_frame_raw
    source = CAMERA_URL if CAMERA_URL else CAMERA_INDEX
    source_label = CAMERA_URL if CAMERA_URL else f"device {CAMERA_INDEX}"

    while True:
        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                print(f"[camera] Cannot open {source_label}, retrying in 5s...")
                time.sleep(5)
                continue

            print(f"[camera] Connected to {source_label}")
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[camera] Lost frame, reconnecting...")
                    break

                _, buf = cv2.imencode(".jpg", frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 75])
                with frame_lock:
                    latest_frame_jpg = buf.tobytes()
                    latest_frame_raw = frame.copy()

                # Save frame if recording (at lower rate)
                save_recording_frame(frame)

                time.sleep(0.05)  # 20 FPS capture
            cap.release()
        except Exception as e:
            print(f"[camera] Error: {e}, retrying in 5s...")
            time.sleep(5)


_rec_frame_counter = 0

def save_recording_frame(frame):
    """Save frame to disk if recording is active (~7 FPS)."""
    global recording_count, _rec_frame_counter
    _rec_frame_counter += 1
    if _rec_frame_counter % 3 != 0:
        return
    with recording_lock:
        if not recording_active or not recording_session_dir:
            return
        count = recording_count
        recording_count += 1
        session_dir = recording_session_dir

    fname = f"frame_{count:06d}.jpg"
    fpath = os.path.join(session_dir, fname)
    cv2.imwrite(fpath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])


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

            f_path = files[-1]
            if f_path not in last_pos:
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
        pass

    def do_GET(self):
        # Strip query string for routing
        path = self.path.split("?")[0]

        if path == "/" or path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif path == "/record" or path == "/record.html":
            self._serve_file("record.html", "text/html")
        elif path == "/api/stream":
            self._handle_sse()
        elif path == "/api/snapshot":
            self._handle_snapshot()
        elif path == "/api/history":
            self._handle_history()
        elif path == "/api/recording/status":
            self._handle_recording_status()
        elif path == "/api/recording/labels":
            self._handle_recording_labels()
        elif path.startswith("/static/"):
            fname = path[8:]
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
                self._json_response({"ok": True})
            except Exception:
                self.send_error(400)

        elif self.path == "/api/recording/start":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                label = data.get("label", "").strip().lower().replace(" ", "_")
                if not label:
                    self._json_response({"error": "label required"}, 400)
                    return
                result = start_recording(label)
                self._json_response(result)
            except Exception as e:
                self._json_response({"error": str(e)}, 400)

        elif self.path == "/api/recording/stop":
            result = stop_recording()
            self._json_response(result)

        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
            while True:
                try:
                    msg = q.get(timeout=5)
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except Empty:
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(jpg)

    def _handle_history(self):
        body = json.dumps(recent_detections[:MAX_HISTORY]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_recording_status(self):
        with recording_lock:
            data = {
                "active": recording_active,
                "label": recording_label,
                "count": recording_count,
                "dir": recording_session_dir,
            }
        self._json_response(data)

    def _handle_recording_labels(self):
        """List all recorded labels and their frame counts."""
        labels = {}
        rec_path = Path(RECORDINGS_DIR)
        if rec_path.exists():
            for d in sorted(rec_path.iterdir()):
                if d.is_dir():
                    count = len(list(d.glob("*.jpg")))
                    if count > 0:
                        labels[d.name] = count
        self._json_response(labels)


# ── Recording Control ─────────────────────────────────────
def start_recording(label: str):
    global recording_active, recording_label, recording_count, recording_session_dir

    if not HAS_CV2:
        return {"error": "opencv not installed"}

    with recording_lock:
        if recording_active:
            return {"error": f"already recording: {recording_label}"}

        session_dir = os.path.join(RECORDINGS_DIR, label)
        os.makedirs(session_dir, exist_ok=True)

        # Count existing frames to continue numbering
        existing = len(list(Path(session_dir).glob("*.jpg")))

        recording_active = True
        recording_label = label
        recording_count = existing
        recording_session_dir = session_dir

    print(f"[recording] Started: {label} → {session_dir} (existing: {existing} frames)")
    return {"ok": True, "label": label, "dir": session_dir, "existing": existing}


def stop_recording():
    global recording_active, recording_label, recording_count, recording_session_dir

    with recording_lock:
        if not recording_active:
            return {"ok": True, "label": "", "count": 0}

        result = {
            "ok": True,
            "label": recording_label,
            "count": recording_count,
            "dir": recording_session_dir,
        }

        recording_active = False
        label = recording_label
        count = recording_count
        recording_label = ""
        recording_count = 0
        recording_session_dir = ""

    print(f"[recording] Stopped: {label} — {count} frames saved")
    return result


class ThreadedHTTPServer(HTTPServer):
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
    if HAS_CV2:
        t = threading.Thread(target=camera_loop, daemon=True)
        t.start()
        if CAMERA_URL:
            print(f"[camera] Streaming from {CAMERA_URL}")
        else:
            print(f"[camera] Streaming from device {CAMERA_INDEX}")
    else:
        print("[camera] opencv not installed — camera disabled")

    t = threading.Thread(target=jsonl_watcher, daemon=True)
    t.start()
    print(f"[watcher] Watching {DETECTIONS_DIR}/ for JSONL output")
    print(f"[recording] Frames will be saved to {RECORDINGS_DIR}/")

    server = ThreadedHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  SSE stream: http://localhost:{PORT}/api/stream")
    print(f"  Recording API: POST /api/recording/start, /api/recording/stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
