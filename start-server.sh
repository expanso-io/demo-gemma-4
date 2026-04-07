#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Start Gemma 4 E2B inference server (llama.cpp)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Runs llama-server with Gemma 4 E2B (Q4_K_M) on GPU.
# OpenAI-compatible API on port 8081.
#
# Usage:
#   ./start-server.sh          # Start in background
#   ./start-server.sh stop     # Stop server
#   ./start-server.sh test     # Quick inference test
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

MODEL_DIR="${HOME}/models/gemma4-demo"
LLAMA_SERVER="/opt/llama-server/llama-server"
LLAMA_SERVER_LEGACY="/tmp/llama.cpp/build/bin/llama-server"
PORT="${LLAMA_PORT:-8081}"
LOG="/tmp/llama-server.log"

# Prefer persistent install, fall back to /tmp build
if [ ! -x "$LLAMA_SERVER" ] && [ -x "$LLAMA_SERVER_LEGACY" ]; then
    LLAMA_SERVER="$LLAMA_SERVER_LEGACY"
    export LD_LIBRARY_PATH="/tmp/llama.cpp/build/bin:/tmp/llama.cpp/build/ggml/src:${LD_LIBRARY_PATH:-}"
else
    export LD_LIBRARY_PATH="/opt/llama-server/lib:${LD_LIBRARY_PATH:-}"
fi

stop_server() {
    pkill -f "llama-server.*gemma" 2>/dev/null && echo "Stopped." || echo "Not running."
}

start_server() {
    if curl -s "http://localhost:${PORT}/health" 2>/dev/null | grep -q "ok"; then
        echo "Server already running on port ${PORT}"
        return 0
    fi

    stop_server 2>/dev/null

    echo "Starting Gemma 4 E2B on port ${PORT}..."
    ${LLAMA_SERVER} \
        --model "${MODEL_DIR}/gemma-4-E2B-it.Q4_K_M.gguf" \
        --mmproj "${MODEL_DIR}/gemma-4-E2B-it.BF16-mmproj.gguf" \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --n-gpu-layers 99 \
        --ctx-size 2048 \
        --threads 4 \
        --flash-attn true \
        --reasoning off \
        --reasoning-budget 0 \
        > "${LOG}" 2>&1 &

    echo "Waiting for model to load..."
    for i in $(seq 1 30); do
        if curl -s "http://localhost:${PORT}/health" 2>/dev/null | grep -q "ok"; then
            echo "Ready: http://localhost:${PORT}"
            return 0
        fi
        sleep 1
        printf "."
    done
    echo ""
    echo "Check logs: tail -f ${LOG}"
}

test_server() {
    echo "Testing text inference..."
    time curl -s "http://localhost:${PORT}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"gemma4","messages":[{"role":"user","content":"Say hello in 5 words"}],"max_tokens":20}' \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
}

case "${1:-start}" in
    start)  start_server ;;
    stop)   stop_server ;;
    test)   test_server ;;
    *)      echo "Usage: $0 [start|stop|test]"; exit 1 ;;
esac
