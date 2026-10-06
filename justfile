set shell := ["bash", "-euo", "pipefail", "-c"]

_default:
    @just --list

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
    mkdir -p .runtime
    nohup uv run -s ../_demo-kit/model-gateway.py serve \
        --config model-gateway.toml > .runtime/gateway.log 2>&1 &
    echo $! > .runtime/gateway.pid
    for attempt in 1 2 3 4 5; do
        curl -fsS http://127.0.0.1:18153/status >/dev/null && break
        sleep 1
    done
    curl -fsS http://127.0.0.1:18153/status >/dev/null
    echo "model gateway on http://127.0.0.1:18153 (${GATEWAY_MODE:-fixture})"

gateway-down:
    #!/usr/bin/env bash
    if [[ -f .runtime/gateway.pid ]]; then
        kill "$(cat .runtime/gateway.pid)" 2>/dev/null || true
        rm -f .runtime/gateway.pid
    fi

gateway-status:
    @uv run -s ../_demo-kit/model-gateway.py status --config model-gateway.toml

review-labels:
    uv run finetune/review_labels.py

check: lint test validate job-check provider-check
