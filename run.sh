#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Gemma 4 × Expanso Edge — Multi-Modal Demo Launcher
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Runs the "Sees, Reads, Thinks" multi-modal pipeline.
# One frame → four Gemma 4 analyses (detect, read, describe, safety).
#
# Usage:
#   ./run.sh              # Start multi-modal pipeline
#
# Camera: set CAMERA_URL for RTSP/HTTP, or CAMERA_INDEX for USB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env if present ──────────────────────────────────
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

# ── Configurable defaults ─────────────────────────────────
export NODE_ID="${NODE_ID:-edge-cam-001}"
export INFERENCE_URL="${INFERENCE_URL:-http://localhost:8081}"
export CAPTURE_INTERVAL="${CAPTURE_INTERVAL:-12s}"
export PIPELINE_VERSION="${PIPELINE_VERSION:-2.0.0}"
export CAMERA_URL="${CAMERA_URL:-}"
export CAMERA_INDEX="${CAMERA_INDEX:-0}"

# ── Print banner ──────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Google Gemma 4 × Expanso Edge"
echo "  Sees, Reads, Thinks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Pipeline:  Multi-Modal (4 analyses per frame)"
echo "  Modes:     DETECT → READ → DESCRIBE → SAFETY"
echo "  Model:     Gemma 4 E2B (Q4_K_M)"
echo "  Server:    ${INFERENCE_URL}"
echo "  Interval:  ${CAPTURE_INTERVAL}"
echo "  Node:      ${NODE_ID}"
if [ -n "$CAMERA_URL" ]; then
    echo "  Camera:    $(echo "$CAMERA_URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"
else
    echo "  Camera:    /dev/video${CAMERA_INDEX}"
fi
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Preflight checks ─────────────────────────────────────
if ! command -v expanso-edge &>/dev/null; then
    echo "  expanso-edge not found. Install from: https://docs.expanso.io/getting-started/quickstart/"
    exit 1
fi

if ! python3 -c "import cv2" 2>/dev/null; then
    echo "  opencv-python not installed. Run: pip install opencv-python"
    exit 1
fi

if ! curl -s --connect-timeout 3 "${INFERENCE_URL}/health" 2>/dev/null | grep -q "ok"; then
    echo "  Inference server not reachable at ${INFERENCE_URL}"
    echo "   Start llama-server:  ./scripts/start-server.sh"
    echo ""
    echo "   Continuing anyway (will retry on each frame)..."
    echo ""
fi

# ── Launch pipeline ───────────────────────────────────────
cd "$SCRIPT_DIR"
exec expanso-edge run pipeline.yaml
