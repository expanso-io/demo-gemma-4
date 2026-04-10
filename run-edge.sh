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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDGE_DIR="${SCRIPT_DIR}/.edge"

# Load .env if present
if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

exec expanso-edge run \
    --data-dir "${EDGE_DIR}" \
    --config "${EDGE_DIR}/config.d" \
    "$@"
