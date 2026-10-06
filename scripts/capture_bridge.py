#!/usr/bin/env python3
"""Keep capture diagnostics outside the pipeline's JSON-lines protocol."""

from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    child_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "capture_frame.py"
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    log_path = runtime / f"capture-{os.getpid()}.stderr.log"
    child = None
    try:
        environment = dict(os.environ, OPENCV_LOG_LEVEL="ERROR")
        with log_path.open("wb") as errors:
            child = subprocess.Popen(
                [sys.executable, "-u", str(child_path)],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
                bufsize=1,
            )
            with selectors.DefaultSelector() as ready:
                ready.register(child.stdout, selectors.EVENT_READ)
                for line in sys.stdin:
                    child.stdin.write(line)
                    child.stdin.flush()
                    if not ready.select(timeout=60):
                        raise RuntimeError("Capture response timed out")
                    response = child.stdout.readline()
                    if not response:
                        code = child.wait(timeout=5)
                        raise RuntimeError(
                            f"Capture process ended before responding (exit {code})"
                        )
                    record = json.loads(response)
                    if not isinstance(record, dict):
                        raise ValueError("Capture response must be a JSON object")
                    print(json.dumps(record, separators=(",", ":")), flush=True)
            child.stdin.close()
            code = child.wait(timeout=10)
            if code:
                raise RuntimeError(f"Capture process exited with status {code}")
    except Exception as error:
        detail = f"{type(error).__name__}: {error}; diagnostics: {log_path}"
        print(json.dumps({"error": detail}, separators=(",", ":")), flush=True)
        return 1
    finally:
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            for stream in (child.stdin, child.stdout):
                if stream is not None:
                    stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
