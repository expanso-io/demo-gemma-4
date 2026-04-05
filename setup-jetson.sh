#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Gemma 4 × Expanso Edge — Jetson Setup Script
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Sets up everything needed to run the demo on a Jetson Orin:
#   1. Downloads Gemma 4 E2B GGUF model (3.2GB total)
#   2. Pulls llama.cpp Docker container with CUDA
#   3. Starts the inference server on port 8081
#
# Prerequisites:
#   - Jetson Orin with JetPack 6.x
#   - Docker with NVIDIA runtime
#   - Expanso Edge installed
#
# Usage:
#   ./setup-jetson.sh          # Full setup
#   ./setup-jetson.sh start    # Start inference server only
#   ./setup-jetson.sh stop     # Stop inference server
#   ./setup-jetson.sh test     # Test inference
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Configuration ──────────────────────────────────
MODEL_DIR="${HOME}/models/gemma4-e2b"
CONTAINER_NAME="gemma4-server"
CONTAINER_IMAGE="dustynv/llama_cpp:r36.4.0"
MODEL_FILE="gemma-4-E2B-it-Q3_K_S.gguf"
MMPROJ_FILE="mmproj-BF16.gguf"
HF_BASE="https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main"
PORT=8081

# ── Functions ──────────────────────────────────────

stop_server() {
    echo "Stopping inference server..."
    docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
    # Stop ollama if running to free memory
    sudo systemctl stop ollama 2>/dev/null || true
    pkill -f "ollama serve" 2>/dev/null || true
    sleep 2
    echo "Stopped."
}

start_server() {
    stop_server

    if [ ! -f "${MODEL_DIR}/${MODEL_FILE}" ] || [ ! -f "${MODEL_DIR}/${MMPROJ_FILE}" ]; then
        echo "ERROR: Model files not found. Run: $0  (no arguments) to download."
        exit 1
    fi

    echo "Starting Gemma 4 E2B inference server on port ${PORT}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --runtime nvidia \
        --gpus all \
        --network host \
        -v "${MODEL_DIR}:/models" \
        "${CONTAINER_IMAGE}" \
        llama-server \
            --model "/models/${MODEL_FILE}" \
            --mmproj "/models/${MMPROJ_FILE}" \
            --host 0.0.0.0 \
            --port "${PORT}" \
            --n-gpu-layers 99 \
            --ctx-size 4096 \
            --threads 4

    echo "Waiting for model to load..."
    for i in $(seq 1 60); do
        if curl -s "http://localhost:${PORT}/health" 2>/dev/null | grep -q "ok"; then
            echo "Server ready on port ${PORT}"
            return 0
        fi
        sleep 2
        echo -n "."
    done
    echo ""
    echo "WARNING: Server may still be loading. Check: docker logs ${CONTAINER_NAME}"
}

test_server() {
    echo "Testing text inference..."
    time curl -s "http://localhost:${PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"gemma4","messages":[{"role":"user","content":"Say hello in 5 words"}],"max_tokens":20}' \
        | python3 -m json.tool
}

download_model() {
    mkdir -p "${MODEL_DIR}"

    if [ -f "${MODEL_DIR}/${MODEL_FILE}" ]; then
        echo "Model already downloaded: ${MODEL_FILE}"
    else
        echo "Downloading ${MODEL_FILE} (2.45GB)..."
        wget -q --show-progress -c "${HF_BASE}/${MODEL_FILE}" -O "${MODEL_DIR}/${MODEL_FILE}"
    fi

    if [ -f "${MODEL_DIR}/${MMPROJ_FILE}" ]; then
        echo "Vision projector already downloaded: ${MMPROJ_FILE}"
    else
        echo "Downloading ${MMPROJ_FILE} (987MB)..."
        wget -q --show-progress -c "${HF_BASE}/${MMPROJ_FILE}" -O "${MODEL_DIR}/${MMPROJ_FILE}"
    fi

    echo ""
    echo "Model files:"
    ls -lh "${MODEL_DIR}/"
}

pull_container() {
    echo "Pulling llama.cpp container (${CONTAINER_IMAGE})..."
    docker pull "${CONTAINER_IMAGE}"
}

# ── Main ───────────────────────────────────────────

case "${1:-setup}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    test)
        test_server
        ;;
    setup|"")
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Gemma 4 × Expanso Edge — Jetson Setup"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        download_model
        echo ""
        pull_container
        echo ""
        start_server
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Setup complete!"
        echo ""
        echo "  Inference: http://localhost:${PORT}"
        echo "  Dashboard: python3 web/server.py"
        echo "  Pipeline:  expanso-cli job deploy job.yaml"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ;;
    *)
        echo "Usage: $0 [setup|start|stop|test]"
        exit 1
        ;;
esac
