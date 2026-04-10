#!/usr/bin/env python3
"""
Convert labeled frames into Unsloth-compatible training dataset.

Reads labels/*.jsonl + recordings/*/*.jpg and produces a HuggingFace
Dataset saved to training_data/ that can be loaded directly by the
fine-tuning notebook.

Each training example has 4 conversation pairs (one per mode) so the
model learns all 4 tasks from each frame.

Usage:
    python3 prepare_training_data.py
    python3 prepare_training_data.py --output training_data
"""

import argparse
import json
import glob
import os
from pathlib import Path

LABELS_DIR = Path(__file__).parent / "labels"
OUTPUT_DIR = Path(__file__).parent / "training_data"

# The 4 prompts that match pipeline.yaml
PROMPTS = {
    "detect": "Which are visible? person, box, bottle, sign. CSV only, no explanation.",
    "read_text": "Read all text visible in this image. Return only the text strings, comma-separated. Nothing else.",
    "describe": "Describe this scene in one sentence, 15 words max.",
    "safety": "Is this scene safe? Reply: safe OR alert: [reason]. Nothing else.",
}


def format_detect_response(objects):
    """Format detection as terse CSV labels."""
    labels = sorted(set(
        o["label"] for o in objects
        if o["label"] in ("person", "box", "bottle", "sign") and o.get("confidence", 0) >= 0.5
    ))
    return ", ".join(labels) if labels else "none"


def format_read_response(objects):
    """Format text reading as comma-separated strings."""
    texts = [
        o["text_visible"] for o in objects
        if o.get("text_visible") and o["text_visible"].strip()
    ]
    return ", ".join(texts) if texts else "none"


def format_describe_response(scene_description):
    """Clean up scene description to be terse."""
    desc = scene_description.strip()
    # Remove trailing period for consistency
    if desc.endswith("."):
        desc = desc[:-1]
    # Truncate to ~15 words
    words = desc.split()
    if len(words) > 15:
        desc = " ".join(words[:15])
    return desc


def format_safety_response(safety_assessment):
    """Format safety as terse safe/alert."""
    s = safety_assessment.strip().lower()
    if s.startswith("alert"):
        return safety_assessment.strip()
    return "safe"


def build_training_examples(label_file):
    """Build training examples from a label JSONL file."""
    examples = []

    for line in open(label_file):
        record = json.loads(line)
        image_path = record.get("image", "")
        objects = record.get("objects", [])
        scene_desc = record.get("scene_description", "")
        safety = record.get("safety_assessment", "safe")

        if not os.path.exists(image_path):
            continue

        # Generate 4 training pairs from this frame
        detect_resp = format_detect_response(objects)
        read_resp = format_read_response(objects)
        describe_resp = format_describe_response(scene_desc)
        safety_resp = format_safety_response(safety)

        for mode, prompt in PROMPTS.items():
            if mode == "detect":
                response = detect_resp
            elif mode == "read_text":
                response = read_resp
            elif mode == "describe":
                response = describe_resp
            elif mode == "safety":
                response = safety_resp

            examples.append({
                "image_path": image_path,
                "mode": mode,
                "prompt": prompt,
                "response": response,
            })

    return examples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    all_examples = []
    for label_file in sorted(glob.glob(str(LABELS_DIR / "*.jsonl"))):
        cat = Path(label_file).stem
        examples = build_training_examples(label_file)
        print(f"  {cat}: {len(examples)} training pairs ({len(examples)//4} frames × 4 modes)")
        all_examples.extend(examples)

    print(f"\nTotal training pairs: {len(all_examples)}")

    # Save as JSONL (portable, works everywhere)
    jsonl_path = output_dir / "train.jsonl"
    with open(jsonl_path, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    print(f"Saved: {jsonl_path} ({len(all_examples)} records)")

    # Also save a summary
    from collections import Counter
    mode_counts = Counter(ex["mode"] for ex in all_examples)
    response_samples = {}
    for ex in all_examples:
        if ex["mode"] not in response_samples:
            response_samples[ex["mode"]] = ex["response"]

    summary = {
        "total_examples": len(all_examples),
        "frames": len(all_examples) // 4,
        "mode_counts": dict(mode_counts),
        "response_samples": response_samples,
    }
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== Response samples ===")
    for mode, sample in response_samples.items():
        print(f"  {mode}: \"{sample}\"")


if __name__ == "__main__":
    main()
