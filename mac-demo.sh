#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# mac-demo.sh — Start/stop the Gemma 4 demo stack on Mac
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Starts inference server (via start-server.sh) + web dashboard.
# Pipeline runs through Expanso Cloud (deploy with ./deploy.sh).
#
# Usage:
#   ./mac-demo.sh start     Start inference server + dashboard
#   ./mac-demo.sh stop      Stop everything
#   ./mac-demo.sh status    Check what's running
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env so dashboard + server get CAMERA_URL etc.
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

PORT="${LLAMA_PORT:-8081}"
DASHBOARD_PORT="${DASHBOARD_PORT:-9090}"
DASHBOARD_LOG="/tmp/dashboard-mac.log"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

# ── Start ─────────────────────────────────────────────────
cmd_start() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Starting Gemma 4 Demo (Mac)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # ── Inference server (via start-server.sh) ────────────
    "${SCRIPT_DIR}/start-server.sh" start
    echo ""

    # ── Dashboard ─────────────────────────────────────────
    if curl -sf "http://localhost:${DASHBOARD_PORT}/" >/dev/null 2>&1; then
        ok "Dashboard already running on :${DASHBOARD_PORT}"
    else
        pkill -f "web/server.py" 2>/dev/null || true
        sleep 1

        echo "  Starting dashboard..."
        uv run "${SCRIPT_DIR}/web/server.py" \
            > "$DASHBOARD_LOG" 2>&1 &

        for i in $(seq 1 15); do
            if curl -sf "http://localhost:${DASHBOARD_PORT}/" >/dev/null 2>&1; then
                ok "Dashboard ready on :${DASHBOARD_PORT} (${i}s)"
                break
            fi
            if [ "$i" -eq 15 ]; then
                fail "Dashboard didn't start — check: tail -f $DASHBOARD_LOG"
                exit 1
            fi
            sleep 1
        done
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Dashboard:  http://localhost:${DASHBOARD_PORT}"
    echo "  Inference:  http://localhost:${PORT}"
    echo ""
    echo "  Run edge agent: ./run-edge.sh"
    echo "  Deploy pipeline: ./deploy.sh"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ── Stop ──────────────────────────────────────────────────
cmd_stop() {
    echo "Stopping demo stack..."

    if pkill -f "web/server.py" 2>/dev/null; then
        ok "Stopped dashboard"
    else
        ok "Dashboard not running"
    fi

    "${SCRIPT_DIR}/start-server.sh" stop

    # Clean up shared frame
    rm -f /tmp/gemma4-latest.jpg

    # Verify ports are free
    sleep 1
    local clean=true
    if lsof -i ":${PORT}" -P -n 2>/dev/null | grep -q LISTEN; then
        warn "Port ${PORT} still in use"
        clean=false
    fi
    if lsof -i ":${DASHBOARD_PORT}" -P -n 2>/dev/null | grep -q LISTEN; then
        warn "Port ${DASHBOARD_PORT} still in use"
        clean=false
    fi

    if $clean; then
        ok "Ports ${PORT} and ${DASHBOARD_PORT} are free"
    fi
}

# ── Status ────────────────────────────────────────────────
cmd_status() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Gemma 4 Demo (Mac) — Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        ok "Inference: http://localhost:${PORT}  (healthy)"
    else
        fail "Inference: http://localhost:${PORT}  (not running)"
    fi

    if curl -sf "http://localhost:${DASHBOARD_PORT}/" >/dev/null 2>&1; then
        ok "Dashboard: http://localhost:${DASHBOARD_PORT}  (up)"
    else
        fail "Dashboard: http://localhost:${DASHBOARD_PORT}  (not running)"
    fi

    echo ""
}

# ── Main ──────────────────────────────────────────────────
case "${1:-help}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    help|*)
        echo "Usage: $0 {start|stop|status}"
        echo ""
        echo "  start    Start inference server + dashboard"
        echo "  stop     Stop everything"
        echo "  status   Check what's running"
        echo ""
        echo "  Run edge agent: ./run-edge.sh"
        echo "  Deploy pipeline via Expanso Cloud: ./deploy.sh"
        ;;
esac
