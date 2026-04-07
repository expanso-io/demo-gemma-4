# Jetson Orin NX — Operations & Performance Guide

**Device:** NVIDIA Jetson Orin NX (Super) — 6 cores, 7.4GB unified RAM, 116GB NVMe
**Swap:** 8GB swapfile + 3.8GB zram (6×635MB) = ~12GB total
**GPU:** Shared memory with CPU — no separate VRAM budget

## The Golden Rule

**This machine has 7.4GB of RAM shared between CPU and GPU. There is no room for mistakes.**

Running two heavy processes at once (e.g., llama-server + a Python training script, or two model servers) will push into swap, thrash the NVMe, and grind everything to a halt. On this machine, swap is a sign something went wrong — not a safety net.

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

That leaves ~5.8GB for the model in GPU memory. The Q4_K_M GGUF (3.2GB) fits well, with ~2.6GB headroom for context, KV cache, and temporary allocations.

## Before Starting Anything

```bash
# Check what's using memory RIGHT NOW
free -h
ps aux --sort=-%mem | head -10

# Quick one-liner: anything using >100MB?
ps aux --sort=-%rss | awk 'NR<=1 || $6>100000' | head -15

# Is swap being used? If >100MB, something's wrong
swapon --show

# GPU memory (Jetson shares RAM, so this is part of the 7.4GB)
cat /sys/devices/gpu.0/load 2>/dev/null   # 0-1000 scale

# Full system snapshot
tegrastats --interval 1000 | head -3
```

## Starting the Demo Stack

**Always start in this order** — model server first, then pipeline:

```bash
# 1. Stop anything that shouldn't be running
pkill -f "python3.*train" 2>/dev/null       # Kill any training scripts
pkill -f "ollama" 2>/dev/null               # Kill Ollama if running
docker stop $(docker ps -q) 2>/dev/null     # Stop stray containers

# 2. Verify memory is clean
free -h   # Should show <2GB used before starting the model

# 3. Start the model server
cd ~/demo-gemma-4
./start-server.sh start

# 4. Verify it's healthy
./start-server.sh test

# 5. Start the pipeline
./run.sh
```

## Stopping Cleanly

```bash
# Stop pipeline first, then model server
pkill -f "expanso-edge" 2>/dev/null
./start-server.sh stop

# Verify everything released
sleep 2 && free -h
```

## Things That Will Kill This Machine

| Action | Why it's bad | What to do instead |
|---|---|---|
| Running `ollama` alongside `llama-server` | Both load the model into GPU memory = 6.4GB+ | Pick one. We use llama-server. |
| Running `pip install` with a build step | Compilation eats all 6 cores + RAM | Install on Hetzner, scp the wheel |
| Running `docker build` | Layer caching + compilation = RAM bomb | Build on Hetzner, push to registry |
| Opening a browser on the Jetson | Chromium alone eats 500MB+ | SSH from laptop, view dashboard remotely |
| Running `claude` (this CLI) + inference | Claude uses ~500MB; combined with model = tight | Stop the model server while doing dev work, restart after |
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

### Swap alarm — if swap usage climbs, something's wrong
```bash
while true; do
  SWAP_USED=$(free -m | awk '/Swap:/ {print $3}')
  if [ "$SWAP_USED" -gt 500 ]; then
    echo "WARNING: Swap usage ${SWAP_USED}MB — check processes!"
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

Running `claude` (this CLI) uses ~500MB RSS. Combined with the model server (~1GB) and system baseline (~600MB), that's ~2.1GB before the model loads into GPU memory.

**Guidelines:**
- It's fine to run Claude Code while the model server is running — just don't also run training or docker builds
- If you need to do heavy dev work (installing packages, running tests), stop the model server first: `./start-server.sh stop`
- When done with dev work, restart: `./start-server.sh start`

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
