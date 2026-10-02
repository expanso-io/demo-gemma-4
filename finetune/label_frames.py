#!/usr/bin/env python3
"""Label a bounded set of training frames with the local Gemma server.

This is an edge-vision workload, so frames stay local. Calls are sequential
and the default run processes at most 12 frames. The script never invokes a
provider CLI or reads a provider credential.
"""

import argparse
import base64
import json
import os
import random
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RECORDINGS_DIR = ROOT / "recordings"
OUTPUT_DIR = ROOT / "labels"
DEFAULT_MAX_FRAMES = 12

PROMPT = """\
Analyze the image and return one JSON object with:
- objects: label, bbox [y1, x1, y2, x2] as percentages, confidence, and text_visible
- scene_description: one sentence, at most 15 words
- safety_assessment: "safe" or "alert: [reason]"
Labels must be box, bottle, sign, person, or none. Return JSON only.
"""


def request_label(
    image_path: Path,
    inference_url: str,
    model: str,
    timeout: float = 120,
) -> dict:
    """Send one image to the local OpenAI-compatible Gemma endpoint."""
    encoded = base64.b64encode(image_path.read_bytes()).decode()
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                    },
                ],
            }
        ],
        "max_tokens": 512,
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        f"{inference_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read(400).decode(errors="replace")
        raise RuntimeError(f"local inference HTTP {error.code}: {detail}") from error
    except (OSError, ValueError) as error:
        raise RuntimeError(f"local inference unavailable: {error}") from error

    raw = str(payload["choices"][0]["message"]["content"]).strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```")
        raw = raw.removesuffix("```").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("local model returned non-JSON labels") from error
    if not isinstance(result.get("objects"), list):
        raise TypeError("local model response has no objects array")
    return result


def select_frames(
    recordings_dir: Path,
    category: str | None,
    sample: int,
    max_frames: int,
) -> list[tuple[str, Path]]:
    """Select a bounded, category-balanced list of frame paths."""
    if not recordings_dir.exists():
        return []
    candidates: list[tuple[str, Path]] = []
    for directory in sorted(recordings_dir.iterdir()):
        if not directory.is_dir() or (category and directory.name != category):
            continue
        frames = sorted(directory.glob("*.jpg"))
        if sample and len(frames) > sample:
            frames = sorted(random.sample(frames, sample))
        candidates.extend((directory.name, frame) for frame in frames)
    return candidates[:max_frames]


def existing_images(path: Path) -> set[str]:
    if not path.exists():
        return set()
    found = set()
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" not in record:
            found.add(str(record.get("image", "")))
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Label training frames with the local Gemma server"
    )
    parser.add_argument("--category")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--inference-url",
        default=os.environ.get("INFERENCE_URL", "http://127.0.0.1:8081"),
    )
    parser.add_argument("--model", default="gemma4")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_frames < 1 or args.max_frames > 100:
        raise SystemExit("--max-frames must be between 1 and 100")
    if args.sample < 0:
        raise SystemExit("--sample must be non-negative")

    selected = select_frames(
        RECORDINGS_DIR,
        args.category,
        args.sample,
        args.max_frames,
    )
    print(f"Selected {len(selected)} frame(s); cap {args.max_frames}")
    if args.dry_run:
        for category, frame in selected:
            print(f"  {category}: {frame.name}")
        return 0
    if not selected:
        print(f"No frames found under {RECORDINGS_DIR}")
        return 0

    OUTPUT_DIR.mkdir(exist_ok=True)
    completed = 0
    for category, frame in selected:
        output = OUTPUT_DIR / f"{category}.jsonl"
        if str(frame) in existing_images(output):
            print(f"skip {category}/{frame.name}: already labeled")
            continue
        try:
            result = request_label(frame, args.inference_url, args.model)
        except RuntimeError as error:
            print(f"stop {category}/{frame.name}: {error}")
            return 1
        record = {
            "image": str(frame),
            "model": args.model,
            "source": "local",
            "category": category,
            **result,
        }
        with output.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        completed += 1
        labels = [item.get("label") for item in result["objects"]]
        print(f"[{completed}/{len(selected)}] {category}/{frame.name}: {labels}")

    print(f"Wrote {completed} local label record(s) to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
