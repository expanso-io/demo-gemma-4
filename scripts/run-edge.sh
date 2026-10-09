#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Run Expanso Edge with local config (no global settings)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Uses .edge/ directory for all config, credentials,
# and state. Does not read from ~/.expanso/edge/.
#
# Usage:
#   ./run-edge.sh          # Connect to Expanso Cloud
#   ./run-edge.sh --verbose
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EDGE_DIR="${PROJECT_ROOT}/.edge"

# Load .env if present
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

source "$PROJECT_ROOT/scripts/port-env.sh"
demo_ports_load "$PROJECT_ROOT" --allow-bound

exec expanso-edge run \
    --data-dir "${EDGE_DIR}" \
    --api-listen "127.0.0.1:$EDGE_API_PORT" \
    --config "${EDGE_DIR}/config.d" \
    "$@"
