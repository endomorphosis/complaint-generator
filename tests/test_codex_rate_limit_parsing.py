import json
import os
import pytest
from datetime import datetime, timezone

import importlib.util


def _load_codex_autopatch_module():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "examples", "codex_autopatch_from_run.py")
    spec = importlib.util.spec_from_file_location("codex_autopatch_from_run", path)
    assert spec and spec.loader, f"Failed to load spec for: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_codex_autopatch = _load_codex_autopatch_module()
_debug_extract_reset_info_from_message = _codex_autopatch._debug_extract_reset_info_from_message
_extract_rate_limit_reset_info_with_exec_fallback = _codex_autopatch._extract_rate_limit_reset_info_with_exec_fallback
_pick_reset_at_raw_from_rate_limit_artifact = _codex_autopatch._pick_reset_at_raw_from_rate_limit_artifact


def test_parse_try_again_at_human_timestamp() -> None:
    msg = (
        "You've hit your usage limit. "
        "Upgrade to Pro, or try again at Feb 11th, 2026 11:46 PM."
    )
    info = _debug_extract_reset_info_from_message(msg)
    assert info["source"] == "try_again_at"
    assert info["reset_at_iso"] == "2026-02-11T23:46:00+00:00"
    assert isinstance(info["resets_in_seconds"], int)
    assert info["resets_in_seconds"] > 0


def test_parse_iso_reset_at_and_derive_seconds() -> None:
    # Use a near-future timestamp so derived seconds are stable.
    now = datetime.now(timezone.utc)
    future = now.replace(microsecond=0)  # keep formatting stable
    future = future + (future - future)  # no-op to keep type checkers happy
    # Add ~30 seconds without importing timedelta to keep this test tiny.
    future = datetime.fromtimestamp(now.timestamp() + 30, tz=timezone.utc).replace(microsecond=0)

    msg = f"http 429 usage_limit reset_at={future.isoformat()}"
    info = _debug_extract_reset_info_from_message(msg)
    assert info["source"] == "reset_at"
    assert info["reset_at_iso"] == future.isoformat()
    assert isinstance(info["resets_in_seconds"], int)
    # Allow small clock skew.
    assert 0 < info["resets_in_seconds"] <= 35


def test_parse_resets_in_seconds_jsonish() -> None:
    msg = json.dumps({"error": "usage_limit_reached", "resets_in_seconds": 123})
    info = _debug_extract_reset_info_from_message(msg)
    assert info["resets_in_seconds"] == 123


def test_parse_real_codex_exec_jsonl_if_present() -> None:
    """Optional local test: verify parsing against a real Codex exec JSONL artifact.

    This is skipped in clean environments/CI where the artifact doesn't exist.
    """
    default_path = (
        "statefiles/_runs/autopatch_loop_0001_20260210_042146_run_00/_patches/"
        "codex_exec_gpt-5.3-codex_20260210_042449_2254399.jsonl"
    )
    jsonl_path = os.environ.get("CODEX_EXEC_JSONL_PATH", default_path)
    if not os.path.isfile(jsonl_path):
        pytest.skip(f"Codex exec JSONL not present: {jsonl_path}")

    message = None
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "error" and isinstance(obj.get("message"), str):
                message = obj["message"]
                break

    assert message, "No error.message found in JSONL"

    info = _debug_extract_reset_info_from_message(message)
    assert info["source"] in {"try_again_at", "reset_at", "resets_in_seconds"}
    # The known artifact contains a human 'try again at Feb 11th, 2026 11:46 PM' string.
    if info["source"] == "try_again_at":
        assert info["reset_at_iso"] == "2026-02-11T23:46:00+00:00"


def test_exec_jsonl_fallback_provides_reset_at() -> None:
    now = datetime.now(timezone.utc)
    future = datetime.fromtimestamp(now.timestamp() + 30, tz=timezone.utc).replace(microsecond=0)

    # Exception string lacks reset timing; exec JSONL has provider message with reset_at.
    msg = "HTTP 429 usage_limit"
    exec_jsonl = {
        "type": "error",
        "message": f"You've hit your usage limit. reset_at={future.isoformat()}"
    }

    # Write a minimal JSONL file.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "codex_exec_test.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(exec_jsonl) + "\n")

        reset_s, reset_at, source = _extract_rate_limit_reset_info_with_exec_fallback(
            msg=msg,
            exec_jsonl_path=p,
        )
        assert source == "reset_at"
        assert isinstance(reset_at, datetime)
        assert reset_at.isoformat() == future.isoformat()
        assert isinstance(reset_s, int)
        assert 0 < reset_s <= 35


def test_exec_jsonl_fallback_provides_try_again_at_human_timestamp() -> None:
    def _ordinal_suffix(n: int) -> str:
        if 11 <= (n % 100) <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    now = datetime.now(timezone.utc)
    # Use a near-future timestamp so derived seconds are stable.
    future = datetime.fromtimestamp(now.timestamp() + 2 * 3600, tz=timezone.utc).replace(
        microsecond=0, second=0
    )
    expected_iso = future.isoformat()

    month = future.strftime("%b")
    day_i = int(future.strftime("%d"))
    day = f"{future.strftime('%d')}{_ordinal_suffix(day_i)}"
    year = future.strftime("%Y")
    time_part = future.strftime("%I:%M %p")
    human = f"{month} {day}, {year} {time_part}"

    # Exception string lacks reset timing; exec JSONL has provider message with 'try again at ...'.
    msg = "HTTP 429 usage_limit"
    exec_jsonl = {
        "type": "error",
        "message": f"You've hit your usage limit. Upgrade to Pro, or try again at {human}.",
    }

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "codex_exec_test.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps(exec_jsonl) + "\n")

        reset_s, reset_at, source = _extract_rate_limit_reset_info_with_exec_fallback(
            msg=msg,
            exec_jsonl_path=p,
        )
        assert source == "try_again_at"
        assert isinstance(reset_at, datetime)
        assert reset_at.isoformat() == expected_iso
        assert isinstance(reset_s, int)
        assert 0 < reset_s <= 3 * 3600


def test_pick_reset_at_prefers_provider_reset_at() -> None:
    data = {
        "reset_at": "2026-02-10T00:00:00+00:00",
        "provider_reset_at": "2026-02-11T23:46:00+00:00",
    }
    assert _pick_reset_at_raw_from_rate_limit_artifact(data) == "2026-02-11T23:46:00+00:00"
