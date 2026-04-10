#!/usr/bin/env python3
"""
Label recorded frames using Claude CLI (already authenticated).

Sends each frame to Claude and asks for bounding box annotations + labels.
Outputs JSONL for fine-tuning.

Usage:
    python3 label_frames.py                     # Label all
    python3 label_frames.py --category box      # One category
    python3 label_frames.py --sample 30         # Sample per category
    python3 label_frames.py --dry-run           # Preview only
"""

import argparse
import json
import random
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RECORDINGS_DIR = Path(__file__).parent / "recordings"
OUTPUT_DIR = Path(__file__).parent / "labels"

PROMPT = """Analyze this image and identify all objects present.

For each object, provide:
- label: one of [box, bottle, sign, person] or "none" if the category doesn't apply
- bounding box: [y1, x1, y2, x2] as percentages (0-100) of image dimensions
- confidence: 0.0-1.0
- text_visible: any text you can read on the object (empty string if none)

Also provide:
- scene_description: one sentence, 15 words max
- safety_assessment: "safe" or "alert: [reason]"

Return ONLY valid JSON, no markdown fences:
{
  "objects": [
    {"label": "box", "bbox": [10, 20, 80, 90], "confidence": 0.95, "text_visible": "FedEx Express"}
  ],
  "scene_description": "A person holds a shipping box at a table.",
  "safety_assessment": "safe"
}"""


def label_frame(image_path: str, model: str) -> dict:
    """Send a frame to Claude CLI and get structured labels."""
    schema = json.dumps({
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "enum": ["box", "bottle", "sign", "person", "none"]},
                        "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                        "confidence": {"type": "number"},
                        "text_visible": {"type": "string"}
                    },
                    "required": ["label", "bbox", "confidence"]
                }
            },
            "scene_description": {"type": "string"},
            "safety_assessment": {"type": "string"}
        },
        "required": ["objects", "scene_description", "safety_assessment"]
    })

    full_prompt = f"Read the file {image_path} and analyze the image.\n\n{PROMPT}"
    result = subprocess.run(
        [
            "claude", "-p", full_prompt,
            "--model", model,
            "--output-format", "json",
            "--json-schema", schema,
            "--allowedTools", "Read",
        ],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")

    raw = result.stdout.strip()

    try:
        outer = json.loads(raw)
    except json.JSONDecodeError:
        return {"image": str(image_path), "model": model, "raw": raw, "parse_error": True}

    # Extract structured_output from CLI JSON envelope
    structured = outer.get("structured_output", {})
    cost = outer.get("total_cost_usd", 0)

    return {
        "image": str(image_path),
        "model": model,
        "cost_usd": cost,
        **structured,
    }


def main():
    parser = argparse.ArgumentParser(description="Label frames with Claude CLI")
    parser.add_argument("--category", type=str, help="Label only this category")
    parser.add_argument("--model", type=str, default="claude-opus-4-6",
                        help="Model to use (default: claude-opus-4-6)")
    parser.add_argument("--sample", type=int, default=0,
                        help="Sample N frames per category (0=all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be labeled without calling API")
    parser.add_argument("--parallel", type=int, default=4,
                        help="Number of parallel claude calls (default: 4)")
    args = parser.parse_args()

    # Verify claude CLI is available and authenticated
    if not args.dry_run:
        check = subprocess.run(["claude", "auth", "status"],
                               capture_output=True, text=True)
        if "loggedIn" not in check.stdout or "true" not in check.stdout:
            print("Claude CLI not authenticated. Run: claude auth login")
            sys.exit(1)
        print("Claude CLI: authenticated")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Gather frames
    categories = {}
    for d in sorted(RECORDINGS_DIR.iterdir()):
        if not d.is_dir():
            continue
        if args.category and d.name != args.category:
            continue
        frames = sorted(d.glob("*.jpg"))
        if args.sample > 0 and len(frames) > args.sample:
            frames = sorted(random.sample(frames, args.sample))
        categories[d.name] = frames

    total = sum(len(f) for f in categories.values())
    print(f"Categories: {list(categories.keys())}")
    print(f"Total frames: {total}")
    print(f"Model: {args.model}")

    if args.dry_run:
        for cat, frames in categories.items():
            print(f"  {cat}: {len(frames)} frames")
        return

    print()

    done = 0
    errors = 0
    for cat, frames in categories.items():
        out_path = OUTPUT_DIR / f"{cat}.jsonl"

        # Skip already-labeled frames
        existing = set()
        if out_path.exists():
            with open(out_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        if "error" not in rec:
                            existing.add(rec.get("image", ""))
                    except json.JSONDecodeError:
                        pass
        remaining = [f for f in frames if str(f) not in existing]

        if not remaining:
            print(f"{cat}: all {len(frames)} frames already labeled, skipping")
            done += len(frames)
            continue

        print(f"Labeling {cat}: {len(remaining)} frames ({len(existing)} already done) → {out_path}")

        write_lock = threading.Lock()

        def process_frame(frame):
            try:
                result = label_frame(str(frame), args.model)
                result["category"] = cat
                return frame, result, None
            except Exception as e:
                return frame, None, e

        with open(out_path, "a") as out_f, \
             ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(process_frame, f): f for f in remaining}
            for future in as_completed(futures):
                done += 1
                frame, result, err = future.result()
                if err:
                    errors += 1
                    print(f"  [{done}/{total}] {frame.name}: ERROR - {err}")
                    with write_lock:
                        out_f.write(json.dumps({
                            "image": str(frame),
                            "category": cat,
                            "error": str(err),
                        }) + "\n")
                else:
                    with write_lock:
                        out_f.write(json.dumps(result) + "\n")
                        out_f.flush()
                    labels = [o["label"] for o in result.get("objects", [])]
                    text = [o.get("text_visible", "") for o in result.get("objects", []) if o.get("text_visible")]
                    extra = f" text={text}" if text else ""
                    cost = result.get("cost_usd", 0)
                    print(f"  [{done}/{total}] {frame.name}: {labels}{extra} (${cost:.3f})")

    print(f"\nDone! {done} labeled, {errors} errors")
    print(f"Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
