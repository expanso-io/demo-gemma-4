#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${ROOT}/.runtime/public-bar"
INFERENCE_PORT=18154
EDGE_API_PORT=18155
OUTPUT="${RUNTIME}/output.jsonl"
RECEIPT="${RUNTIME}/receipt.json"
SERVER_LOG="${RUNTIME}/fixture-server.log"
EDGE_LOG="${RUNTIME}/edge.log"
SERVER_PID=""
EDGE_PID=""

cleanup() {
    if [[ -n "${EDGE_PID}" ]]; then
        kill "${EDGE_PID}" 2>/dev/null || true
        wait "${EDGE_PID}" 2>/dev/null || true
    fi
    if [[ -n "${SERVER_PID}" ]]; then
        kill "${SERVER_PID}" 2>/dev/null || true
        wait "${SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if lsof -nP -iTCP:"${INFERENCE_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port ${INFERENCE_PORT} is already in use" >&2
    exit 1
fi
if lsof -nP -iTCP:"${EDGE_API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port ${EDGE_API_PORT} is already in use" >&2
    exit 1
fi

mkdir -p "${RUNTIME}"
rm -f "${OUTPUT}" "${RECEIPT}" "${SERVER_LOG}" "${EDGE_LOG}"

cd "${ROOT}"
uv run -s scripts/fixture_server.py \
    --port "${INFERENCE_PORT}" \
    --receipt "${RECEIPT}" >"${SERVER_LOG}" 2>&1 &
SERVER_PID=$!

for _ in {1..40}; do
    if curl -fsS "http://127.0.0.1:${INFERENCE_PORT}/health" \
        >/dev/null; then
        break
    fi
    sleep 0.1
done
curl -fsS "http://127.0.0.1:${INFERENCE_PORT}/health" >/dev/null

CAMERA_URL="${ROOT}/Gemma-Short.gif" \
CAPTURE_INTERVAL=10ms \
MAX_FRAMES=1 \
NODE_ID=public-bar-fixture \
INFERENCE_URL="http://127.0.0.1:${INFERENCE_PORT}" \
DASHBOARD_URL="http://127.0.0.1:${INFERENCE_PORT}" \
DETECTIONS_FILE="${OUTPUT}" \
expanso-edge run \
    --local \
    --no-watch \
    --data-dir "${RUNTIME}/edge" \
    --api-listen "127.0.0.1:${EDGE_API_PORT}" \
    >"${EDGE_LOG}" 2>&1 &
EDGE_PID=$!

for _ in {1..80}; do
    if curl -fsS \
        "http://127.0.0.1:${EDGE_API_PORT}/api/v1/jobs" >/dev/null; then
        break
    fi
    if ! kill -0 "${EDGE_PID}" 2>/dev/null; then
        tail -80 "${EDGE_LOG}" >&2
        exit 1
    fi
    sleep 0.1
done
curl -fsS "http://127.0.0.1:${EDGE_API_PORT}/api/v1/jobs" >/dev/null
expanso-cli \
    --endpoint "http://127.0.0.1:${EDGE_API_PORT}" \
    job deploy scripts/job.yaml >>"${EDGE_LOG}" 2>&1

for _ in {1..240}; do
    if [[ -s "${OUTPUT}" && -s "${RECEIPT}" ]]; then
        break
    fi
    if ! kill -0 "${EDGE_PID}" 2>/dev/null; then
        tail -80 "${EDGE_LOG}" >&2
        exit 1
    fi
    sleep 0.25
done

if [[ ! -s "${OUTPUT}" || ! -s "${RECEIPT}" ]]; then
    tail -80 "${EDGE_LOG}" >&2
    echo "fixture run did not produce both outputs" >&2
    exit 1
fi

uv run -s scripts/assert-public-fixture.py \
    --output "${OUTPUT}" \
    --receipt "${RECEIPT}"

cleanup
EDGE_PID=""
SERVER_PID=""

if lsof -nP -iTCP:"${INFERENCE_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "fixture server still owns port ${INFERENCE_PORT}" >&2
    exit 1
fi
if lsof -nP -iTCP:"${EDGE_API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "edge agent still owns port ${EDGE_API_PORT}" >&2
    exit 1
fi

echo "fixture run complete; logs and outputs are in ${RUNTIME}"
