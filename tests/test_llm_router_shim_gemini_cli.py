import pytest
from unittest.mock import patch
import subprocess


def test_gemini_cli_missing_binary_raises_helpful_error():
    from ipfs_datasets_py.llm_router import generate_text, LLMRouterError

    with patch("ipfs_datasets_py.llm_router.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(LLMRouterError) as exc_info:
            generate_text(
                prompt="Hello",
                provider="gemini_cli",
                model_name="gemini-1.5-pro",
            )

    msg = str(exc_info.value).lower()
    assert "gemini cli" in msg
    assert "not found" in msg


def test_gemini_cli_retries_with_node20_overlay_on_node18_regexp_error():
    from ipfs_datasets_py.llm_router import generate_text

    err = "SyntaxError: Invalid regular expression flags\n\nNode.js v18.19.1"
    ok = subprocess.CompletedProcess(args=["npx"], returncode=0, stdout="OK\n", stderr="")

    side_effects = [
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["some-gemini"],
            output="",
            stderr=err,
        ),
        ok,
    ]

    with patch("ipfs_datasets_py.llm_router.subprocess.run", side_effect=side_effects) as mock_run:
        out = generate_text(
            prompt="Hello",
            provider="gemini_cli",
            model_name="gemini-1.5-pro",
            gemini_cmd=["some-gemini"],
        )

    assert out.strip() == "OK"
    assert mock_run.call_count == 2
