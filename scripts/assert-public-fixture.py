#!/usr/bin/env -S uv run -s
"""Assert the bounded Expanso Edge fixture output and HTTP receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_single_jsonl(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    if len(rows) != 1:
        raise AssertionError(f"expected one output row, found {len(rows)}")
    return rows[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    output = load_single_jsonl(args.output)
    receipt = json.loads(args.receipt.read_text())

    assert output == receipt, "file output and HTTP fan-out receipt differ"
    assert output["node_id"] == "public-bar-fixture"
    assert output["mode"] == "multi"
    assert output["detect"]["labels"] == ["person", "bottle"]
    assert output["read_text"]["text"] == "GEMMA 4"
    assert output["describe"]["summary"] == (
        "A person holds a bottle beside an edge camera."
    )
    assert output["safety"]["safe"] is True
    assert output["integrity"]["frame_sha256"]
    assert output["attestation"]["subject"][0]["digest"]["recordCount"] == "4"
    print(f"validated frame {output['frame_id']} across file and HTTP outputs")


if __name__ == "__main__":
    main()
