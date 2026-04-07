# Jetson Orin NX — Operations & Performance Guide

**Device:** NVIDIA Jetson Orin NX (Super) — 6 cores, 7.4GB unified RAM, 116GB NVMe
**Swap:** 8GB swapfile + 3.8GB zram (6×635MB) = ~12GB total
**GPU:** Shared memory with CPU — no separate VRAM budget

## The Golden Rule

**This machine has 7.4GB of RAM shared between CPU and GPU. Swap is your friend — use it aggressively.**

With only 7.4GB unified RAM, the model server + system baseline already consume most of physical memory. Swap on NVMe is fast enough to keep things running smoothly — the 8GB swapfile + 3.8GB zram gives us 12GB of overflow. The key is making sure the *hot path* (GPU inference, KV cache) stays in physical RAM while less-critical memory (Python overhead, file caches, idle process pages) gets paged out.

What kills this machine isn't swap usage — it's running **two GPU-hungry processes at once** (e.g., llama-server + Ollama, or two model loads). The GPU can't page to swap; once physical RAM is exhausted for GPU allocations, the OOM killer arrives.

## What's Running (Normal State)

| Process | ~RAM | Purpose | Must Run? |
|---|---|---|---|
| `llama-server` (Gemma 4 GGUF) | ~1.0GB | Inference API on :8081 | Yes (for demo) |
| `esc-server` | ~48MB | Security camera dashboard on :8080 | Yes (for demo) |
| `expanso-edge` | ~75MB | Expanso Edge agent | Yes (for pipeline) |
| `gnome-shell` + X11 | ~150MB | Desktop (if display attached) | Optional |
| `docker` + `containerd` | ~120MB | Container runtime | Optional |
| System (journald, NetworkManager, etc.) | ~200MB | OS baseline | Yes |
| **Total baseline** | **~1.6GB** | | |

That leaves ~5.8GB of physical RAM for the model's GPU memory. The Q4_K_M GGUF (3.2GB) fits, with ~2.6GB headroom for context and KV cache. CPU-side allocations from Python, the pipeline, and system services happily spill into swap — this is expected and fine on NVMe.

## Before Starting Anything

```bash
# Check what's using memory RIGHT NOW
free -h
ps aux --sort=-%mem | head -10

# Quick one-liner: anything using >100MB?
ps aux --sort=-%rss | awk 'NR<=1 || $6>100000' | head -15

# Swap usage (expected — NVMe swap is fast)
swapon --show

# GPU memory (Jetson shares RAM, so this is part of the 7.4GB)
cat /sys/devices/gpu.0/load 2>/dev/null   # 0-1000 scale

# Full system snapshot
tegrastats --interval 1000 | head -3
```

## Managing the Demo Stack

The stack is managed via `demo-ctl` and systemd services. This handles dependency ordering,
health checks, conflict detection, and automatic restarts.

### First-time setup (run once)
```bash
cd ~/demo-gemma-4
./demo-ctl install     # Installs systemd services, enables on boot
```

### Daily operations
```bash
./demo-ctl start       # Start full stack (server → pipeline → dashboard → watchdog)
./demo-ctl stop        # Stop everything cleanly (reverse order)
./demo-ctl restart     # Stop then start
./demo-ctl status      # Health check + memory + swap + disk
./demo-ctl logs        # Tail all logs (or: logs server|pipeline|dashboard|watchdog)
./demo-ctl doctor      # Full system diagnosis
```

### What `demo-ctl start` does
1. **Preflight** — checks for conflicting processes (Ollama, stray llama-servers), verifies model files exist
2. **Starts gemma4-server** — loads GGUF into GPU, waits for health endpoint
3. **Starts gemma4-pipeline** — Expanso Edge running pipeline.yaml (depends on server)
4. **Starts gemma4-dashboard** — Web UI on :9090
5. **Starts gemma4-watchdog** — Monitors health + swap thrashing, auto-restarts if needed

### systemd services

| Service | Purpose | OOM Priority | Restart |
|---|---|---|---|
| `gemma4-server` | llama.cpp inference on :8081 | -500 (last to kill) | on-failure, 10s |
| `gemma4-pipeline` | Expanso Edge vision pipeline | +200 (kill before server) | on-failure, 15s |
| `gemma4-dashboard` | Web dashboard on :9090 | +500 (first to kill) | on-failure, 5s |
| `gemma4-watchdog` | Health + swap monitoring | — | always, 30s |

The pipeline `BindsTo` the server — if the server stops, the pipeline stops automatically.
The server `Conflicts` with Ollama — systemd won't let both run.

### Manual start (without systemd)
If you need to run things manually (e.g., debugging):
```bash
./start-server.sh start    # Start llama-server in background
./start-server.sh test     # Verify inference works
./run.sh                   # Start pipeline (foreground)
```

### Stopping cleanly
```bash
./demo-ctl stop            # Recommended: stops in reverse dependency order

# Or manually:
sudo systemctl stop gemma4-pipeline gemma4-server
```

## Things That Will Kill This Machine

| Action | Why it's bad | What to do instead |
|---|---|---|
| Running `ollama` alongside `llama-server` | Both load the model into GPU memory = 6.4GB+ | Pick one. We use llama-server. |
| Running `pip install` with a build step | Compilation eats all 6 cores + RAM | Install on Hetzner, scp the wheel |
| Running `docker build` | Layer caching + compilation = RAM bomb | Build on Hetzner, push to registry |
| Opening a browser on the Jetson | Chromium alone eats 500MB+ | SSH from laptop, view dashboard remotely |
| Running `claude` (this CLI) + inference | Claude uses ~500MB; pushes more into swap but usually OK | Monitor with `free -h`; stop model server if swap thrashing starts |
| Two SSH sessions both running heavy things | Easy to forget what's running where | Use `tmux` and keep one session |
| `git clone` of a large repo | Git can spike to 1GB+ during clone | Clone on Hetzner, rsync what you need |
| Running any Python ML library (torch, etc.) | `import torch` alone = 500MB+ | Do ML work on Hetzner |

## Monitoring

### Quick health check
```bash
# One command to check everything
echo "=== Memory ===" && free -h && echo "=== Swap ===" && swapon --show && echo "=== Top 5 ===" && ps aux --sort=-%mem | head -6 && echo "=== GPU ===" && cat /sys/devices/gpu.0/load 2>/dev/null && echo "=== Disk ===" && df -h /
```

### Watch mode (leave in a tmux pane)
```bash
tegrastats --interval 2000
```

### Swap monitoring — normal usage is fine, thrashing is the problem
```bash
# Check swap I/O rate (si/so columns = pages swapped in/out per second)
# Sustained high si+so = thrashing. Occasional spikes are fine.
vmstat 2 5

# Watch swap usage over time — steady is OK, rapidly climbing is not
while true; do
  SWAP_USED=$(free -m | awk '/Swap:/ {print $3}')
  echo "$(date +%H:%M:%S) Swap: ${SWAP_USED}MB"
  if [ "$SWAP_USED" -gt 8000 ]; then
    echo "WARNING: Swap nearly full (${SWAP_USED}MB/12000MB) — check processes!"
    ps aux --sort=-%mem | head -5
  fi
  sleep 10
done
```

## Recovery: Machine Is Thrashing

If the machine becomes unresponsive (heavy swap, ssh is slow):

```bash
# 1. Kill the biggest offender
pkill -9 -f "llama-server"     # Frees ~1GB immediately
pkill -9 -f "python3"          # If a script ran away

# 2. Drop caches to reclaim buffer/cache memory
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'

# 3. Check what's left
free -h && ps aux --sort=-%mem | head -10

# 4. If truly stuck, reboot is faster than debugging
sudo reboot
```

## Claude Code Sessions

Running `claude` (this CLI) uses ~500MB RSS. This will push some system memory into swap — that's expected and fine on NVMe.

**Guidelines:**
- It's fine to run Claude Code while the model server is running — CPU-side memory pages out to swap, GPU memory stays pinned
- If you're also running the pipeline + Claude Code + model server and things feel sluggish, check `vmstat 2` for swap thrashing (high si/so columns)
- For heavy work (large package installs, docker builds), stop the model server to free physical RAM: `./start-server.sh stop`

## Disk Space

The NVMe is 116GB with 48GB free. Watch out for:
- `/tmp/llama.cpp/` — build artifacts (~2GB)
- `recordings/` — grows with each capture session
- Docker images if any get pulled
- `~/.cache/` — pip, huggingface, etc.

```bash
# Check disk hogs
du -sh /tmp/* ~/.cache/* ~/models/* 2>/dev/null | sort -hr | head -10
```
