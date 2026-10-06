import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "web" / "static" / "index.html").read_text()
SERVER = (ROOT / "web" / "server.py").read_text()
EXPLORER = json.loads(
    (ROOT / "web" / "static" / "explorer.json").read_text()
)


def test_explorer_covers_every_pipeline_stage():
    assert [stage["id"] for stage in EXPLORER["stages"]] == [
        "capture",
        "detect",
        "read",
        "describe",
        "safety",
        "schema",
        "attest",
        "fanout",
    ]
    for stage in EXPLORER["stages"]:
        assert stage["input"]
        assert stage["output"]
        assert f'data-stage-id="{stage["id"]}"' in INDEX


def test_light_is_default_and_dark_has_explicit_toggle():
    root_tokens = INDEX.split("html[data-theme=\"dark\"]", maxsplit=1)[0]
    assert "color-scheme: light" in root_tokens
    assert "color-scheme: dark" in INDEX
    assert 'id="themeToggle"' in INDEX


def test_explorer_has_keyboard_paging_and_scroll_retention():
    assert "event.key === 'ArrowLeft'" in INDEX
    assert "event.key === 'ArrowRight'" in INDEX
    assert "window.scrollTo(0, previousScroll)" in INDEX


def test_copy_and_download_report_local_results():
    for message in (
        "Copied",
        "Copy failed",
        "Download started",
        "Download failed",
    ):
        assert message in INDEX


def test_history_is_replayed_to_new_sse_connections():
    assert "reversed(recent_detections[-10:])" in SERVER


def test_published_page_has_all_public_bar_sections():
    for selector_id in (
        "explanation",
        "stageExplorer",
        "runInstructions",
        "deployInstructions",
    ):
        assert f'id="{selector_id}"' in INDEX
