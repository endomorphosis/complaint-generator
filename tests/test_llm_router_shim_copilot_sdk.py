import pytest


def test_copilot_sdk_missing_dependency_raises_helpful_error():
    # The Copilot Python SDK is an optional dependency.
    # This test ensures we fail with a clear message when it's not installed.
    from ipfs_datasets_py.llm_router import generate_text, LLMRouterError

    with pytest.raises(LLMRouterError) as exc_info:
        generate_text(
            prompt="Hello",
            provider="copilot_sdk",
            model_name="gpt-5-mini",
        )

    msg = str(exc_info.value).lower()
    assert "python sdk" in msg
    assert "not installed" in msg
