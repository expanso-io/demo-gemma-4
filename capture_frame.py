#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python"]
# ///
"""
Frame Capture for Expanso Edge Pipeline
========================================

Runs as a long-lived subprocess inside an Expanso Edge pipeline.
For each line received on stdin (the trigger), captures one frame
and writes a single-line JSON object to stdout:

    {"image_base64": "/9j/4AAQ..."}

Supports USB webcams, RTSP IP cameras, and HTTP MJPEG streams.
The camera stays open between captures for fast response times.

Usage:
    # USB webcam (default):
    echo "" | python3 capture_frame.py

    # RTSP IP camera:
    CAMERA_URL="rtsp://user:pass@192.168.2.10:554/h264Preview_01_sub" \
      echo "" | python3 capture_frame.py

    # Inside Expanso Edge pipeline (see pipeline.yaml):
    #   subprocess:
    #     name: python3
    #     args: ["-u", "capture_frame.py"]
"""

import sys
import json
import base64
import signal
import os
import time

try:
    import cv2
except ImportError:
    print(
        json.dumps({"error": "opencv-python not installed. Run: pip install opencv-python"}),
        flush=True,
    )
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────
# CAMERA_URL takes priority: supports rtsp://, http://, or file paths.
# Falls back to CAMERA_INDEX (integer) for local USB/CSI cameras.
# SHARED_FRAME: if the dashboard writes frames to this file, read from
# there instead of opening the camera (avoids macOS camera contention).
CAMERA_URL = os.environ.get("CAMERA_URL", "")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "320"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "240"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "70"))
WARMUP_FRAMES = int(os.environ.get("WARMUP_FRAMES", "5"))
SHARED_FRAME = os.environ.get("SHARED_FRAME", "/tmp/gemma4-latest.jpg")
SHARED_FRAME_MAX_AGE = 5  # seconds — fall back to camera if stale


def open_camera():
    """Open camera from URL (RTSP/HTTP) or device index."""
    source = CAMERA_URL if CAMERA_URL else CAMERA_INDEX
    source_label = CAMERA_URL if CAMERA_URL else f"device {CAMERA_INDEX}"

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(
            json.dumps({"error": f"Could not open camera: {source_label}"}),
            flush=True,
        )
        sys.exit(1)

    # Set resolution (only applies to USB/CSI cameras, ignored by RTSP)
    if not CAMERA_URL:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    return cap, source_label


def _try_shared_frame():
    """Read from shared frame file as fallback (written by dashboard)."""
    try:
        age = time.time() - os.path.getmtime(SHARED_FRAME)
        if age >= SHARED_FRAME_MAX_AGE:
            return None
        with open(SHARED_FRAME, "rb") as f:
            jpg_bytes = f.read()
        if not jpg_bytes:
            return None
        import numpy as np
        arr = cv2.imdecode(np.frombuffer(jpg_bytes, dtype="uint8"), cv2.IMREAD_COLOR)
        if arr is None:
            return None
        arr = cv2.resize(arr, (CAPTURE_WIDTH, CAPTURE_HEIGHT))
        _, buffer = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if buffer is None:
            return None
        return base64.b64encode(buffer).decode("utf-8")
    except (OSError, ValueError):
        return None


def main():
    # ── Open camera ────────────────────────────────────────────
    cap, source_label = open_camera()

    # Warmup: let auto-exposure settle (skip for RTSP — already streaming)
    warmup = 1 if CAMERA_URL else WARMUP_FRAMES
    for _ in range(warmup):
        cap.read()

    # Graceful shutdown
    def shutdown(sig, frame):
        cap.release()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # ── Main loop: one trigger in → one frame out ──────────────
    for line in sys.stdin:
        # Direct camera capture (RTSP or USB — always preferred when available)
        ret, frame = cap.read()
        if not ret:
            # If direct capture fails, try shared frame file (dashboard writes it)
            b64 = _try_shared_frame()
            if b64 is None:
                print(json.dumps({"error": "Failed to capture frame"}), flush=True)
                continue
        else:
            frame = cv2.resize(frame, (CAPTURE_WIDTH, CAPTURE_HEIGHT))
            success, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not success:
                print(json.dumps({"error": "JPEG encoding failed"}), flush=True)
                continue
            b64 = base64.b64encode(buffer).decode("utf-8")

        # Single-line JSON output (required by Expanso subprocess codec)
        print(json.dumps({"image_base64": b64}), flush=True)

    # ── Cleanup ────────────────────────────────────────────────
    cap.release()


if __name__ == "__main__":
    main()
