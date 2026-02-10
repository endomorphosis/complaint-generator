import json


def test_clean_codex_output_preserves_apply_patch_header():
    from ipfs_datasets_py.llm_router import _clean_codex_output

    raw = "*** Begin Patch\n*** Update File: /tmp/x\n*** End Patch\n"
    cleaned = _clean_codex_output(raw)
    assert cleaned.startswith("*** Begin Patch")


def test_clean_copilot_output_preserves_apply_patch_header():
    from ipfs_datasets_py.llm_router import _clean_copilot_output

    raw = "*** Begin Patch\n*** End Patch\n"
    cleaned = _clean_copilot_output(raw)
    assert cleaned.startswith("*** Begin Patch")


def test_extract_last_agent_message_from_codex_jsonl_item_completed_agent_message():
    from ipfs_datasets_py.llm_router import _extract_last_agent_message_from_codex_jsonl

    patch_text = "*** Begin Patch\n*** End Patch"
    jsonl = "\n".join(
        [
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": patch_text},
                }
            ),
            json.dumps({"type": "turn.completed"}),
        ]
    )
    extracted = _extract_last_agent_message_from_codex_jsonl(jsonl)
    assert extracted == patch_text


def test_extract_last_agent_message_from_codex_jsonl_message_content_output_text():
    from ipfs_datasets_py.llm_router import _extract_last_agent_message_from_codex_jsonl

    jsonl = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Hello"},
                            {"type": "output_text", "text": " world"},
                        ],
                    },
                }
            )
        ]
    )
    extracted = _extract_last_agent_message_from_codex_jsonl(jsonl)
    assert extracted == "Hello world"
