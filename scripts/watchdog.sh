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

# ── Memory snapshot logging ──────────────────────────────
MEMLOG_DIR="${MEMLOG_DIR:-/var/log/gemma4}"
MEMLOG_FILE="${MEMLOG_DIR}/memory.log"
MEMLOG_MAX_SIZE=$((10 * 1024 * 1024))       # 10MB before rotation
MEMLOG_KEEP=3                                # keep 3 rotated files

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
            log "ACTION: Swap thrashing sustained — dumping state then restarting"
            # Capture full state before we kill anything
            {
                echo "!!! OOM INCIDENT $(date '+%Y-%m-%d %H:%M:%S') !!!"
                echo "--- All processes by RSS ---"
                ps -eo pid,rss,%mem,comm --sort=-rss 2>/dev/null | head -20
                echo "--- /proc/meminfo ---"
                cat /proc/meminfo 2>/dev/null | head -15
                echo "--- vmstat ---"
                vmstat 1 3 2>/dev/null
                echo "--- dmesg OOM (last 10) ---"
                dmesg 2>/dev/null | grep -i "oom\|killed process\|out of memory" | tail -10
                echo "!!! END INCIDENT !!!"
                echo ""
            } >> "$MEMLOG_FILE"

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

# ── Memory snapshot logging ───────────────────────────────

rotate_log() {
    if [ ! -f "$MEMLOG_FILE" ]; then return; fi
    local size
    size=$(stat -c%s "$MEMLOG_FILE" 2>/dev/null || echo 0)
    if [ "$size" -ge "$MEMLOG_MAX_SIZE" ]; then
        for i in $(seq $((MEMLOG_KEEP - 1)) -1 1); do
            [ -f "${MEMLOG_FILE}.$i" ] && mv "${MEMLOG_FILE}.$i" "${MEMLOG_FILE}.$((i + 1))"
        done
        mv "$MEMLOG_FILE" "${MEMLOG_FILE}.1"
        log "Rotated memory log"
    fi
}

snapshot_memory() {
    rotate_log

    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')

    {
        echo "=== ${ts} ==="

        # Free/swap summary
        free -m | awk '/Mem:/ {printf "RAM: %dMB/%dMB used (%dMB avail)\n", $3, $2, $7}
                       /Swap:/ {printf "Swap: %dMB/%dMB used\n", $3, $2}'

        # Swap I/O rate
        vmstat 1 2 2>/dev/null | tail -1 | awk '{printf "Swap I/O: si=%s so=%s pages/s\n", $7, $8}'

        # Top 8 processes by RSS (pid, rss_mb, %mem, command)
        echo "Top processes by RSS:"
        ps -eo pid,rss,%mem,comm --sort=-rss 2>/dev/null | head -9

        # OOM scores of our key processes (use pidof for exact binary match)
        echo "OOM scores:"
        for proc in sshd llama-server expanso-edge esc-server earlyoom; do
            local pid
            pid=$(pidof -s "$proc" 2>/dev/null || true)
            if [ -n "$pid" ]; then
                local score adj rss_kb
                score=$(cat "/proc/$pid/oom_score" 2>/dev/null || echo "?")
                adj=$(cat "/proc/$pid/oom_score_adj" 2>/dev/null || echo "?")
                rss_kb=$(awk '/VmRSS/ {print $2}' "/proc/$pid/status" 2>/dev/null || echo "?")
                printf "  %-20s PID=%-6s score=%-4s adj=%-5s rss=%sKB\n" "$proc" "$pid" "$score" "$adj" "$rss_kb"
            fi
        done

        echo ""
    } >> "$MEMLOG_FILE"
}

# ── Main loop ─────────────────────────────────────────────

# Ensure log directory exists
sudo mkdir -p "$MEMLOG_DIR"
sudo chown "$(id -u):$(id -g)" "$MEMLOG_DIR"

log "Watchdog starting (interval=${CHECK_INTERVAL}s, thrash_threshold=${THRASH_THRESHOLD})"
log "Memory snapshots → ${MEMLOG_FILE}"

while true; do
    # Only check health if the server is supposed to be running
    if systemctl is-active gemma4-server >/dev/null 2>&1 || [ "$health_fails" -gt 0 ]; then
        check_health
    fi

    check_swap
    snapshot_memory

    sleep "$CHECK_INTERVAL"
done
