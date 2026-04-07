#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Gemma 4 Demo — Health Watchdog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Monitors:
#   1. Inference server health endpoint
#   2. Swap thrashing (vmstat si+so rate)
#   3. Swap capacity (approaching limit)
#
# Actions:
#   - Restarts inference server if health check fails repeatedly
#   - Logs warnings on elevated swap I/O
#   - Restarts the full stack if swap is critically thrashing
#
# Designed to be lightweight (<1MB RSS). Runs every CHECK_INTERVAL.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

CHECK_INTERVAL="${WATCHDOG_INTERVAL:-30}"   # seconds between checks
HEALTH_URL="http://localhost:8081/health"
THRASH_THRESHOLD=5000                        # pages/s si+so = thrashing
THRASH_WARN=1000                             # pages/s si+so = warning
HEALTH_FAIL_LIMIT=3                          # consecutive failures before restart
THRASH_FAIL_LIMIT=3                          # consecutive thrash readings before restart

health_fails=0
thrash_fails=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

check_health() {
    if curl -sf --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
        if [ "$health_fails" -gt 0 ]; then
            log "INFO: Inference server recovered after ${health_fails} failed checks"
        fi
        health_fails=0
        return 0
    else
        health_fails=$((health_fails + 1))
        log "WARN: Inference health check failed (${health_fails}/${HEALTH_FAIL_LIMIT})"

        if [ "$health_fails" -ge "$HEALTH_FAIL_LIMIT" ]; then
            log "ACTION: Restarting gemma4-server after ${HEALTH_FAIL_LIMIT} consecutive failures"
            sudo systemctl restart gemma4-server || log "ERROR: Failed to restart gemma4-server"
            health_fails=0
            # Give it time to load the model
            sleep 30
        fi
        return 1
    fi
}

check_swap() {
    # Sample vmstat over 2 seconds, take the second line (not the boot average)
    local si so
    read -r si so < <(vmstat 1 2 2>/dev/null | tail -1 | awk '{print $7, $8}')
    local total=$((si + so))

    if [ "$total" -gt "$THRASH_THRESHOLD" ]; then
        thrash_fails=$((thrash_fails + 1))
        log "WARN: Swap thrashing si=${si} so=${so} total=${total} pages/s (${thrash_fails}/${THRASH_FAIL_LIMIT})"

        if [ "$thrash_fails" -ge "$THRASH_FAIL_LIMIT" ]; then
            log "ACTION: Swap thrashing sustained — restarting stack to recover"
            # Stop pipeline first to reduce pressure, then restart server
            sudo systemctl stop gemma4-pipeline 2>/dev/null || true
            sudo systemctl restart gemma4-server || log "ERROR: Failed to restart gemma4-server"
            sleep 30
            sudo systemctl start gemma4-pipeline 2>/dev/null || true
            thrash_fails=0
        fi
    elif [ "$total" -gt "$THRASH_WARN" ]; then
        log "INFO: Elevated swap I/O si=${si} so=${so} total=${total} pages/s"
        # Don't reset thrash_fails — let consecutive high readings accumulate
    else
        thrash_fails=0
    fi

    # Also check swap capacity
    local swap_used swap_total
    read -r swap_total swap_used < <(free -m | awk '/Swap:/ {print $2, $3}')
    if [ "$swap_total" -gt 0 ]; then
        local pct=$((swap_used * 100 / swap_total))
        if [ "$pct" -gt 90 ]; then
            log "WARN: Swap ${pct}% full (${swap_used}MB/${swap_total}MB)"
        fi
    fi
}

# ── Main loop ─────────────────────────────────────────────

log "Watchdog starting (interval=${CHECK_INTERVAL}s, thrash_threshold=${THRASH_THRESHOLD})"

while true; do
    # Only check health if the server is supposed to be running
    if systemctl is-active gemma4-server >/dev/null 2>&1 || [ "$health_fails" -gt 0 ]; then
        check_health
    fi

    check_swap

    sleep "$CHECK_INTERVAL"
done
