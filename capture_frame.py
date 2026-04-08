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
CAMERA_URL = os.environ.get("CAMERA_URL", "")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "320"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "240"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "70"))
WARMUP_FRAMES = int(os.environ.get("WARMUP_FRAMES", "5"))


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
        ret, frame = cap.read()

        if not ret:
            print(json.dumps({"error": "Failed to capture frame"}), flush=True)
            continue

        # Resize to target dimensions (ensures small images for fast inference)
        frame = cv2.resize(frame, (CAPTURE_WIDTH, CAPTURE_HEIGHT))

        # Encode frame as JPEG → base64
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        success, buffer = cv2.imencode(".jpg", frame, encode_params)

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
