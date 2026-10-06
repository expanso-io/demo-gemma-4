#!/usr/bin/env -S uv run -s
"""Render the Cloud job from the validated local pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_PATH = ROOT / "pipeline.yaml"
DEFAULT_OUTPUT = ROOT / "scripts" / "job.yaml"


def render(name: str) -> str:
    pipeline = yaml.safe_load(PIPELINE_PATH.read_text())
    job = {
        "name": name,
        "type": "pipeline",
        "namespace": "demo",
        "selector": {"match_labels": {"hardware": "nvidia-jetson"}},
        "config": pipeline,
    }
    return yaml.safe_dump(job, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="gemma4-vision-demo")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    expected = render(args.name)
    output = args.output.resolve()

    if args.check:
        if not output.exists() or output.read_text() != expected:
            print(f"{output} is stale; run scripts/render-job.py", file=sys.stderr)
            return 1
        print(f"{output} matches pipeline.yaml")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
