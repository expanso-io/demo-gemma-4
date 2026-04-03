#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Gemma 4 × Expanso Edge — Pipeline Launcher
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Usage:
#   ./run.sh                     # default: detect_objects
#   ./run.sh detect_shapes       # geometric shape detection
#   ./run.sh read_text           # OCR / handwriting recognition
#   ./run.sh safety_check        # safety monitoring mode
#   ./run.sh describe_scene      # scene description
#
# The prompt is loaded from prompts/<mode>.txt and injected
# as an environment variable. To hot-swap during the demo:
#   1. Stop the pipeline (Ctrl+C)
#   2. Run with a different mode: ./run.sh safety_check
#
# Or edit the prompt file directly for custom behavior.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Mode selection ─────────────────────────────────────────
MODE="${1:-detect_objects}"
PROMPT_FILE="${SCRIPT_DIR}/prompts/${MODE}.txt"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "❌ Unknown mode: ${MODE}"
    echo ""
    echo "Available modes:"
    for f in "${SCRIPT_DIR}"/prompts/*.txt; do
        name=$(basename "$f" .txt)
        echo "  ./run.sh ${name}"
    done
    exit 1
fi

# ── Load prompt from file ─────────────────────────────────
export VISION_PROMPT
VISION_PROMPT="$(cat "$PROMPT_FILE")"
export DETECTION_MODE="$MODE"

# ── Configurable defaults ─────────────────────────────────
export NODE_ID="${NODE_ID:-edge-cam-001}"
export INFERENCE_URL="${INFERENCE_URL:-http://localhost:11434}"
export GEMMA_MODEL="${GEMMA_MODEL:-gemma4-e4b-it}"
export CAPTURE_INTERVAL="${CAPTURE_INTERVAL:-3s}"
export PIPELINE_VERSION="${PIPELINE_VERSION:-1.0.0}"

# ── Print banner ──────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎥  Gemma 4 × Expanso Edge"
echo "  📋  See, Think, Ship"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Mode:     ${MODE}"
echo "  Model:    ${GEMMA_MODEL}"
echo "  Server:   ${INFERENCE_URL}"
echo "  Interval: ${CAPTURE_INTERVAL}"
echo "  Node:     ${NODE_ID}"
echo ""
echo "  Prompt:"
echo "  $(head -1 "$PROMPT_FILE")"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Preflight checks ─────────────────────────────────────
if ! command -v expanso-edge &>/dev/null; then
    echo "❌ expanso-edge not found. Install from: https://docs.expanso.io/getting-started/quickstart/"
    exit 1
fi

if ! python3 -c "import cv2" 2>/dev/null; then
    echo "⚠️  opencv-python not installed. Run: pip install opencv-python"
    exit 1
fi

# Check if inference server is reachable
if ! curl -s --connect-timeout 3 "${INFERENCE_URL}" >/dev/null 2>&1; then
    echo "⚠️  Inference server not reachable at ${INFERENCE_URL}"
    echo "   Start Ollama:  ollama serve"
    echo "   Pull model:    ollama pull gemma4-e4b-it"
    echo ""
    echo "   Continuing anyway (will retry on each frame)..."
    echo ""
fi

# ── Launch pipeline ───────────────────────────────────────
cd "$SCRIPT_DIR"
exec expanso-edge run pipeline.yaml
