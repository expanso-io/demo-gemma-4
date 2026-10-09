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

source "$SCRIPT_DIR/scripts/port-env.sh"
demo_ports_load "$SCRIPT_DIR" --allow-bound

# ── Configurable defaults ─────────────────────────────────
export NODE_ID="${NODE_ID:-edge-cam-001}"
export INFERENCE_URL="${INFERENCE_URL:-http://localhost:$LLAMA_PORT}"
export CAPTURE_INTERVAL="${CAPTURE_INTERVAL:-12s}"
export MAX_FRAMES="${MAX_FRAMES:-3}"
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
echo "  Run cap:   ${MAX_FRAMES} frames"
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

if ! uv run -- python -c "import cv2" 2>/dev/null; then
    echo "  opencv-python not installed. Run: uv sync"
    exit 1
fi

if ! curl -s --connect-timeout 3 "${INFERENCE_URL}/health" 2>/dev/null | grep -q "ok"; then
    echo "  Inference server not reachable at ${INFERENCE_URL}"
    echo "  Start llama-server: ./scripts/start-server.sh"
    exit 1
fi

# ── Launch pipeline ───────────────────────────────────────
cd "$SCRIPT_DIR"
RUNTIME_DIR="${SCRIPT_DIR}/.runtime/local-edge"
EDGE_API_PORT="${EDGE_API_PORT:-18156}"
EDGE_PID=""

cleanup() {
    if [[ -n "${EDGE_PID}" ]]; then
        kill "${EDGE_PID}" 2>/dev/null || true
        wait "${EDGE_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if lsof -nP -iTCP:"${EDGE_API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  Local Edge API port ${EDGE_API_PORT} is already in use"
    exit 1
fi

mkdir -p "${RUNTIME_DIR}"
uv run -s scripts/render-job.py --check
expanso-edge run \
    --local \
    --no-watch \
    --data-dir "${RUNTIME_DIR}" \
    --api-listen "127.0.0.1:${EDGE_API_PORT}" &
EDGE_PID=$!

for _ in {1..80}; do
    if curl -fsS \
        "http://127.0.0.1:${EDGE_API_PORT}/api/v1/jobs" >/dev/null; then
        break
    fi
    if ! kill -0 "${EDGE_PID}" 2>/dev/null; then
        echo "  Expanso Edge stopped before its local API became ready"
        exit 1
    fi
    sleep 0.1
done

curl -fsS "http://127.0.0.1:${EDGE_API_PORT}/api/v1/jobs" >/dev/null
expanso-cli \
    --endpoint "http://127.0.0.1:${EDGE_API_PORT}" \
    job deploy scripts/job.yaml
wait "${EDGE_PID}"
