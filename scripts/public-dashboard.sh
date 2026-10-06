#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT}/.runtime/public-dashboard.pid"
PORT=19090

stop_dashboard() {
    if [[ ! -f "${PID_FILE}" ]]; then
        return 0
    fi
    local pid
    pid="$(<"${PID_FILE}")"
    if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
        rm -f "${PID_FILE}"
        return 0
    fi
    if kill -0 "${pid}" 2>/dev/null; then
        local command
        command="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
        if [[ "${command}" != *"web/server.py"* ]]; then
            echo "refusing to stop PID ${pid}: not the public dashboard" >&2
            return 1
        fi
        kill "${pid}"
        for _ in {1..40}; do
            if ! kill -0 "${pid}" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done
    fi
    rm -f "${PID_FILE}"
}

case "${1:-start}" in
    start)
        mkdir -p "${ROOT}/.runtime"
        echo "$$" > "${PID_FILE}"
        cd "${ROOT}"
        exec env PORT="${PORT}" uv run -s web/server.py
        ;;
    stop)
        stop_dashboard
        ;;
    *)
        echo "usage: $0 [start|stop]" >&2
        exit 2
        ;;
esac
