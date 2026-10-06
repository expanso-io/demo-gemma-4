#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Deploy pipeline to Expanso Cloud
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Renders pipeline.yaml into a current job spec and deploys it with expanso-cli.
#
# Usage:
#   ./deploy.sh                    # deploy default job
#   ./deploy.sh gemma4-custom      # deploy with custom name
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB_NAME="${1:-gemma4-vision-demo}"
RUNTIME_DIR="${PROJECT_ROOT}/.runtime"
JOB_PATH="${RUNTIME_DIR}/deploy-job.yaml"

cd "$PROJECT_ROOT"

mkdir -p "${RUNTIME_DIR}"
uv run -s scripts/render-job.py \
    --name "${JOB_NAME}" \
    --output "${JOB_PATH}"
expanso-edge validate "${JOB_PATH}"
expanso-cli job validate "${JOB_PATH}"
expanso-cli job deploy "${JOB_PATH}"
rm -f "${JOB_PATH}"
