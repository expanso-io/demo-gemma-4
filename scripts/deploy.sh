#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Deploy pipeline to Expanso Cloud
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Inlines pipeline.yaml into job.yaml and deploys
# via expanso-cli. Run after any pipeline changes.
#
# Usage:
#   ./deploy.sh                    # deploy default job
#   ./deploy.sh gemma4-custom      # deploy with custom name
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB_NAME="${1:-gemma4-vision-demo}"

cd "$PROJECT_ROOT"

python3 << 'PYEOF' > /tmp/_deploy_job.yaml
import yaml, sys

with open('pipeline.yaml') as f:
    pipeline = yaml.safe_load(f)

job = {
    'name': 'gemma4-vision-demo',
    'type': 'pipeline',
    'count': 1,
    'constraints': [{'key': 'host', 'operator': '=', 'values': ['mac']}],
    'config': pipeline,
}

yaml.dump(job, sys.stdout, default_flow_style=False, allow_unicode=True)
PYEOF

expanso-cli job deploy /tmp/_deploy_job.yaml
rm -f /tmp/_deploy_job.yaml
