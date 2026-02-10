import json

from ipfs_datasets_py import llm_router


def test_classify_codex_error_kind_quota_exceeded_from_jsonl() -> None:
    stdout = json.dumps(
        {
            "type": "error",
            "message": "You exceeded your current quota, please check your plan and billing details.",
        }
    )
    kind = llm_router._classify_codex_error_kind(stdout=stdout, stderr="")
    assert kind == "quota_exceeded"


def test_classify_codex_error_kind_usage_limit_from_text() -> None:
    kind = llm_router._classify_codex_error_kind(stdout="", stderr="HTTP 429 usage_limit_reached")
    assert kind == "usage_limit"
