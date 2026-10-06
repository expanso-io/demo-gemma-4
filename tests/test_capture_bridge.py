import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts" / "capture_bridge.py"


def run_bridge(tmp_path, response):
    child = tmp_path / "capture_child.py"
    child.write_text(
        "import sys\n"
        "for line in sys.stdin:\n"
        "    print('native startup warning', file=sys.stderr, flush=True)\n"
        f"    {response}\n"
    )
    return subprocess.run(
        [sys.executable, str(BRIDGE), str(child)],
        input='{"fixture":true}\n',
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=15,
    )


def test_bridge_keeps_stderr_out_of_json_output(tmp_path):
    result = run_bridge(
        tmp_path,
        "print('{\"image_base64\":\"fixture\"}', flush=True)",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"image_base64": "fixture"}


def test_bridge_fails_loudly_on_malformed_stdout(tmp_path):
    result = run_bridge(tmp_path, "print('not-json', flush=True)")
    assert result.returncode == 1
    assert result.stderr == ""
    error = json.loads(result.stdout)["error"]
    assert "JSONDecodeError" in error
