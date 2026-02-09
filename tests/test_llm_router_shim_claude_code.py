import pytest
from unittest.mock import patch


def test_claude_code_missing_binary_raises_helpful_error():
    from ipfs_datasets_py.llm_router import generate_text, LLMRouterError

    with patch("ipfs_datasets_py.llm_router.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(LLMRouterError) as exc_info:
            generate_text(
                prompt="Hello",
                provider="claude_code",
                model_name="sonnet",
            )

    assert "not found" in str(exc_info.value).lower()
