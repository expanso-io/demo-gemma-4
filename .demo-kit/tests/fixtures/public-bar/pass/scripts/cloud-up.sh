#!/usr/bin/env bash
set -euo pipefail

expanso-cli job deploy --force pipelines/normalize.yaml
