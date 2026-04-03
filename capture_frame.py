#!/usr/bin/env python3
"""
Webcam Frame Capture for Expanso Edge Pipeline
================================================

Runs as a long-lived subprocess inside an Expanso Edge pipeline.
For each line received on stdin (the trigger), captures one frame
from the webcam and writes a single-line JSON object to stdout:

    {"image_base64": "/9j/4AAQ..."}

The camera stays open between captures for fast response times.

Usage:
    # Standalone test (Ctrl+C to stop):
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
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "640"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "480"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "80"))
WARMUP_FRAMES = int(os.environ.get("WARMUP_FRAMES", "5"))


def main():
    # ── Open camera ────────────────────────────────────────────
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(
            json.dumps({"error": f"Could not open camera {CAMERA_INDEX}"}),
            flush=True,
        )
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    # Warmup: let auto-exposure settle
    for _ in range(WARMUP_FRAMES):
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
