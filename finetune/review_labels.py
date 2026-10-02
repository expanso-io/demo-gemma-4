#!/usr/bin/env python3
"""Ask the demo-kit gateway once to review the label inventory."""

import argparse
import json
import os
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
LABELS_DIR = ROOT / "labels"
GATEWAY_URL = os.environ.get("MODEL_GATEWAY_URL", "http://127.0.0.1:18153")
FIXTURE_NAME = "training-label-review"
SYSTEM_PROMPT = """\
You review a small computer-vision training-label inventory. Use only the
provided counts. Identify concrete coverage gaps and recommend the next three
collection actions. Do not claim to have seen the images. Return concise
Markdown with headings: Inventory, Gaps, Next collection actions.
"""


def build_inventory(labels_dir: Path = LABELS_DIR) -> dict:
    categories: dict[str, dict] = {}
    total = 0
    for path in sorted(labels_dir.glob("*.jsonl")):
        labels: Counter[str] = Counter()
        scenes = 0
        safe = 0
        alerts = 0
        errors = 0
        records = 0
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                errors += 1
                continue
            records += 1
            if record.get("error"):
                errors += 1
                continue
            if record.get("scene_description"):
                scenes += 1
            assessment = str(record.get("safety_assessment", "")).lower()
            safe += assessment == "safe"
            alerts += assessment.startswith("alert")
            for item in record.get("objects") or []:
                labels[str(item.get("label") or "missing")] += 1
        total += records
        categories[path.stem] = {
            "records": records,
            "object_labels": dict(sorted(labels.items())),
            "scene_descriptions": scenes,
            "safe": safe,
            "alerts": alerts,
            "errors": errors,
        }
    return {"total_records": total, "categories": categories}


def ask_gateway(
    inventory: dict,
    gateway_url: str = GATEWAY_URL,
    timeout: float = 300,
) -> dict:
    prompt = "Review this training-label inventory:\n\n" + json.dumps(
        inventory,
        sort_keys=True,
        separators=(",", ":"),
    )
    body = json.dumps(
        {
            "prompt": prompt,
            "system": SYSTEM_PROMPT,
            "fixture": FIXTURE_NAME,
        }
    ).encode()
    request = urllib.request.Request(
        f"{gateway_url.rstrip('/')}/ask",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read() or b"{}")
        reason = detail.get("reason") or detail.get("status") or str(error)
        raise RuntimeError(f"model gateway refused the review: {reason}") from error
    except (OSError, ValueError) as error:
        raise RuntimeError(f"model gateway unavailable: {error}") from error
    if result.get("status") != "ok" or not str(result.get("text", "")).strip():
        raise RuntimeError(f"model gateway returned an invalid response: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Review the label inventory")
    parser.add_argument("--labels-dir", type=Path, default=LABELS_DIR)
    parser.add_argument("--output", type=Path, default=ROOT / "label-review.md")
    parser.add_argument("--gateway-url", default=GATEWAY_URL)
    args = parser.parse_args()

    inventory = build_inventory(args.labels_dir)
    if not inventory["total_records"]:
        print(f"No labels found in {args.labels_dir}")
        return 1
    try:
        result = ask_gateway(inventory, args.gateway_url)
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 1
    args.output.write_text(str(result["text"]).strip() + "\n")
    print(
        f"Review saved to {args.output} "
        f"({result.get('source')}, {result.get('backend') or 'recorded'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
