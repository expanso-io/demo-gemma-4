export MODEL_GATEWAY_URL := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound | jq -r '"http://127.0.0.1:" + (.GATEWAY_PORT|tostring)'`
export PORT := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound --format json | jq -r .PORT`
export EDGE_API_PORT := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound --format json | jq -r .EDGE_API_PORT`
export LLAMA_PORT := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound --format json | jq -r .LLAMA_PORT`
export GATEWAY_PORT := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound --format json | jq -r .GATEWAY_PORT`
export PUBLIC_DASHBOARD_PORT := `uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound --format json | jq -r .PUBLIC_DASHBOARD_PORT`

set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

# Deploy or update the generated pipeline in Expanso Cloud.
up:
    ./scripts/deploy.sh

# Stop this demo's Cloud job.
down:
    expanso-cli job stop gemma4-vision-demo --force

restart: down up

# Local presenter and local Edge replay.
up-local:
    @just _up-mac

down-local:
    @just _down-mac

restart-local:
    @just _restart-mac

# Jetson systemd stack; Cloud deployment remains `just up`.
up-jetson:
    @just _up-jetson

down-jetson:
    @just _down-jetson

restart-jetson:
    @just _restart-jetson

# One-time Jetson setup: model server, node label, systemd units.
setup-jetson:
    ./scripts/setup-jetson.sh
    ./scripts/demo-ctl install

_up-jetson:
    ./scripts/demo-ctl start

_down-jetson:
    ./scripts/demo-ctl stop

_restart-jetson:
    ./scripts/demo-ctl restart

_restart-mac:
    just _down-mac
    just _up-mac

# Start inference server (if none answers), dashboard on :9090, and pipeline.
_up-mac: ports-preflight
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -f .env ]]; then set -a; source .env; set +a; fi
    source scripts/port-env.sh
    demo_ports_load "$PWD" --allow-bound
    mkdir -p .runtime
    url="${INFERENCE_URL:-http://localhost:$LLAMA_PORT}"
    if ! curl -fsS --connect-timeout 3 "$url/health" 2>/dev/null | grep -q ok; then
        touch .runtime/started-inference
        ./scripts/start-server.sh
    fi
    nohup uv run web/server.py > .runtime/dashboard.log 2>&1 &
    echo $! > .runtime/dashboard.pid
    for _ in {1..100}; do
        curl -fsS -o /dev/null http://127.0.0.1:${PORT:-9090}/ 2>/dev/null && break
        sleep 0.2
    done
    curl -fsS -o /dev/null http://127.0.0.1:${PORT:-9090}/
    nohup ./run.sh > .runtime/pipeline.log 2>&1 &
    echo $! > .runtime/pipeline.pid
    sleep 5
    if ! kill -0 "$(cat .runtime/pipeline.pid)" 2>/dev/null; then
        tail -20 .runtime/pipeline.log
        echo "FAIL: pipeline stopped; see .runtime/pipeline.log, then just down"
        exit 1
    fi
    echo "dashboard on http://localhost:${PORT:-9090} (just down stops everything)"

# Stop everything _up-mac started and fail unless its ports are free.
_down-mac:
    #!/usr/bin/env bash
    set -uo pipefail
    if [[ -f .env ]]; then set -a; source .env; set +a; fi
    source scripts/port-env.sh
    demo_ports_load "$PWD" --allow-bound
    for name in pipeline dashboard; do
        if [[ -f .runtime/$name.pid ]]; then
            kill "$(cat .runtime/$name.pid)" 2>/dev/null || true
            rm -f .runtime/$name.pid
        fi
    done
    ports="${PORT:-9090} ${EDGE_API_PORT:-18156}"
    if [[ -f .runtime/started-inference ]]; then
        ./scripts/start-server.sh stop || true
        rm -f .runtime/started-inference
        ports="$ports ${LLAMA_PORT:-8081}"
    fi
    just gateway-down
    # run.sh keeps its local Edge job here; a stale copy refuses the next deploy.
    rm -rf .runtime/local-edge
    for _ in {1..40}; do
        busy=""
        for port in $ports; do
            lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && busy="$busy $port"
        done
        [[ -z "$busy" ]] && break
        sleep 0.2
    done
    if [[ -n "$busy" ]]; then echo "FAIL: still listening on$busy"; exit 1; fi
    echo "down: ports $ports are free"

test:
    uv run pytest -q

lint:
    uv run ruff check \
        finetune/label_frames.py \
        finetune/review_labels.py \
        scripts/assert-public-fixture.py \
        scripts/fixture_server.py \
        scripts/render-job.py

validate:
    expanso-edge validate pipeline.yaml scripts/job.yaml

job-check:
    uv run -s scripts/render-job.py --check

fixture-run:
    ./scripts/run-public-fixture.sh

provider-check:
    @uv run -s ../_demo-kit/lint-demo-providers.py .

gateway-up:
    #!/usr/bin/env bash
    uv run --no-project scripts/demo-ports.py resolve --demo-dir . --service GATEWAY_PORT >/dev/null
    mkdir -p .runtime
    nohup uv run -s ../_demo-kit/model-gateway.py serve \
        --config model-gateway.toml --port "$GATEWAY_PORT" > .runtime/gateway.log 2>&1 &
    echo $! > .runtime/gateway.pid
    for attempt in 1 2 3 4 5; do
        curl -fsS http://127.0.0.1:${GATEWAY_PORT}/status >/dev/null && break
        sleep 1
    done
    curl -fsS http://127.0.0.1:${GATEWAY_PORT}/status >/dev/null
    echo "model gateway on http://127.0.0.1:${GATEWAY_PORT} (${GATEWAY_MODE:-fixture})"

gateway-down:
    #!/usr/bin/env bash
    if [[ -f .runtime/gateway.pid ]]; then
        kill "$(cat .runtime/gateway.pid)" 2>/dev/null || true
        rm -f .runtime/gateway.pid
    fi

gateway-status:
    @uv run -s ../_demo-kit/model-gateway.py status --config model-gateway.toml --port "$GATEWAY_PORT"

review-labels:
    uv run finetune/review_labels.py

check: lint test validate job-check provider-check

# everything that must be true before a take: gates + live dashboard + checklist
record-check: check
    curl -fsS "http://localhost:${PORT}/" > /dev/null || { echo "FAIL: dashboard not reachable — just up first"; exit 1; }
    @echo ""
    @echo "RECORD CHECKLIST"
    @echo "  [ ] demo-guidance/RECORDING.md read; RECORDING_SCRIPT.md setup done"
    @echo "  [ ] Opera, no browser chrome in frame"
    @echo "  [ ] one frame already processed so the structure is visible"
    @echo "  [ ] RECORDING_PREFLIGHT.md warnings reviewed"

# human story/proof declaration; validates only and never starts anything
recording-preflight:
    @uv run -s ../_demo-kit/recording-preflight.py .

ports:
    @uv run --no-project scripts/demo-ports.py resolve --demo-dir . --allow-bound

ports-preflight:
    @uv run --no-project scripts/demo-ports.py resolve --demo-dir . --service PORT --service EDGE_API_PORT --service LLAMA_PORT >/dev/null
