"""Executable privacy policy for complaint data classes and remote egress."""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path

import pytest

MARKER = "SYNTHETIC_COMPLAINT_MARKER_priv001"
TOKEN = "sk-synthetic-privacy-token-priv001"
PRIVATE_CLASS_IDS = {
    "raw_intake",
    "attachments",
    "fact_kg",
    "claim_dependency_evaluations",
    "annotations",
    "drafts_proofs",
    "embeddings",
    "exports",
    "logs",
    "caches",
    "temporary_files",
    "backups",
}


class _Spy:
    def __init__(self) -> None:
        self.prepare = 0
        self.architecture = 0
        self.provider = 0
        self.socket = 0
        self.process = 0
        self.backend = 0
        self.prompts: list[str] = []
        self.backend_kwargs: list[dict] = []


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    import integrations.ipfs_datasets.llm as llm

    spy = _Spy()
    original_prepare = llm._prepare_generate_text_call

    def _prepare(*args, **kwargs):
        spy.prepare += 1
        return original_prepare(*args, **kwargs)

    def _architecture(*args, **kwargs):
        spy.architecture += 1
        raise AssertionError("architecture selector ran")

    def _provider(*args, **kwargs):
        spy.provider += 1
        prompt = kwargs.get("prompt", args[0] if args else "")
        spy.prompts.append(str(prompt))
        return "local-stub-response"

    def _socket(*args, **kwargs):
        spy.socket += 1
        raise AssertionError("socket opened")

    def _popen(*args, **kwargs):
        spy.process += 1
        raise AssertionError("process spawned")

    monkeypatch.setattr(llm, "_prepare_generate_text_call", _prepare)
    monkeypatch.setattr(llm, "_select_huggingface_arch_route", _architecture)
    monkeypatch.setattr(llm, "generate_text", _provider)
    monkeypatch.setattr(socket, "socket", _socket)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    return spy


def _assert_quiet(spy: _Spy, payload: object) -> None:
    encoded = json.dumps(payload, default=str)
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert spy.prepare == 0
    assert spy.architecture == 0
    assert spy.provider == 0
    assert spy.socket == 0
    assert spy.process == 0


def _service(root: Path):
    from applications.complaint_workspace import ComplaintWorkspaceService

    return ComplaintWorkspaceService(root_dir=root)


def _seed_draft(service, user_id: str, body: str) -> None:
    state = service._load_state(user_id)
    state["draft"] = {"title": "Synthetic", "body": body, "requested_relief": ["Compensatory damages"]}
    state["intake_answers"] = {"party_name": MARKER}
    service._save_state(state)


def test_inventory_separates_private_claim_graph_from_public_law(tmp_path: Path) -> None:
    from complaint_generator.workspace import get_privacy_policy, inventory_private_data_classes

    inventory = inventory_private_data_classes("user-inventory", root_dir=tmp_path)
    private_ids = {item["id"] for item in inventory["private_claim_fact_graph"]}
    assert private_ids == PRIVATE_CLASS_IDS
    assert inventory["public_legal_source_graph"]["id"] == "public_legal_source_graph"
    assert inventory["public_legal_source_graph"]["classification"] == "public"
    assert inventory["public_legal_source_graph"]["distinct_from"] == "private_claim_fact_graph"
    assert inventory["at_rest_protection"] == "plaintext_pending"
    assert inventory["encryption_at_rest_blocks_remote_llm"] is False
    assert inventory["authenticates_tenant"] is False
    assert inventory["reads_existing_private_paths"] is False
    assert inventory["agent_context"]["fixtures_only"] is True
    assert inventory["agent_context"]["excluded_path_classes"] == [
        "session",
        "evidence",
        "export",
        "secret",
    ]
    policy = get_privacy_policy("user-inventory", root_dir=tmp_path)
    assert policy["policy"]["cloud_processing_enabled"] is False
    assert policy["policy"]["processing_mode"] == "local_private"
    assert policy["authenticates_tenant"] is False
    assert "PRIV002" in policy["authorization_note"]


def test_parser_rejects_version_scope_case_and_malformed_consent() -> None:
    from integrations.ipfs_datasets.llm import (
        inspect_privacy_policy,
        privacy_policy_for_mode,
    )

    base = privacy_policy_for_mode("user-a", "case-a", "grok")
    assert inspect_privacy_policy(base, user_id="user-a", case_id="case-a")["admitted"] is True

    wrong_version = dict(base)
    wrong_version["version"] = "0"
    version = inspect_privacy_policy(wrong_version, user_id="user-a", case_id="case-a")
    assert version["admitted"] is False
    assert version["reason"] == "privacy_denied:version"
    assert version["cloud_processing_enabled"] is False

    wrong_scope = dict(base)
    wrong_scope["scope"] = "global"
    scope = inspect_privacy_policy(wrong_scope, user_id="user-a", case_id="case-a")
    assert scope["reason"] == "privacy_denied:scope"
    assert scope["cloud_processing_enabled"] is False

    wrong_case = inspect_privacy_policy(base, user_id="user-a", case_id="case-b")
    assert wrong_case["reason"] == "privacy_denied:case_binding"
    assert wrong_case["policy"]["cloud_processing_enabled"] is False

    malformed = dict(base)
    malformed["consent"] = {"status": "assumed", "cloud_processing": True, "note": MARKER}
    malformed["encryption_at_rest_blocks_remote_llm"] = True
    denied = inspect_privacy_policy(malformed, user_id="user-a", case_id="case-a")
    assert denied["admitted"] is False
    assert denied["cloud_processing_enabled"] is False
    assert MARKER not in json.dumps(denied["policy"])
    assert denied["policy"]["encryption_at_rest_blocks_remote_llm"] is False

    legacy = inspect_privacy_policy(None, user_id="user-a", case_id="case-a")
    assert legacy["reason"] == "legacy_missing"
    assert legacy["cloud_processing_enabled"] is False


def test_legacy_and_malformed_session_permit_no_cloud(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = ComplaintWorkspaceService(root_dir=tmp_path)
    path = service._session_path("legacy-user")
    path.write_text(
        json.dumps(
            {
                "user_id": "legacy-user",
                "intake_answers": {"party_name": "Legacy Person"},
                "privacy_policy": {
                    "version": "9",
                    "consent": {"status": "yes", "secret": TOKEN, "narrative": MARKER},
                    "cloud_processing_enabled": True,
                },
            }
        )
    )
    reloaded = ComplaintWorkspaceService(root_dir=tmp_path)
    state = reloaded._load_state("legacy-user")
    assert state["privacy_policy"]["cloud_processing_enabled"] is False
    assert state["privacy_policy"]["processing_mode"] == "local_private"
    assert state["privacy_policy_load"]["cloud_processing_enabled"] is False
    assert state["privacy_policy_load"]["admitted"] is False
    encoded = json.dumps(state["privacy_policy_load"])
    assert MARKER not in encoded
    assert TOKEN not in encoded
    assert state["intake_answers"]["party_name"] == "Legacy Person"

    missing = service._session_path("older-user")
    missing.write_text(json.dumps({"user_id": "older-user", "intake_answers": {"party_name": "Older"}}))
    older = ComplaintWorkspaceService(root_dir=tmp_path)._load_state("older-user")
    assert older["privacy_policy_load"]["reason"] == "legacy_missing"
    assert older["privacy_policy"]["cloud_processing_enabled"] is False


def test_privacy_commands_do_not_consume_answers_and_persist(tmp_path: Path) -> None:
    from complaint_generator.workspace import get_privacy_policy, set_privacy_policy

    service = _service(tmp_path)
    opening = service.run_intake_chat_turn("chat-user")
    assert opening["privacy_notice"]
    assert "Let's start with the basics." in opening["message"]
    assert opening["inquiry"]["question_id"] == "party_name"
    assert opening["accepted_answer"] is None

    switched = service.run_intake_chat_turn("chat-user", message="/privacy grok")
    assert switched["accepted_answer"] is None
    assert switched["privacy_command"]["stored_as_answer"] is False
    assert switched["privacy_command"]["processing_mode"] == "grok_cloud"
    assert switched["inquiry"]["question_id"] == "party_name"
    assert "/privacy grok" not in json.dumps(switched["session"]["intake_answers"])
    assert "/privacy grok" not in json.dumps(switched["session"]["intake_history"])

    first = service.run_intake_chat_turn("chat-user", message="Ada Example")
    second = service.run_intake_chat_turn("chat-user", message="Opposing Example")
    assert first["accepted_answer"]["question_id"] == "party_name"
    assert second["accepted_answer"]["question_id"] == "opposing_party"
    assert second["session"]["intake_answers"]["party_name"] == "Ada Example"
    assert "privacy_notice" not in second or second.get("privacy_notice") in {None, ""}

    fresh = _service(tmp_path)
    persisted = get_privacy_policy("chat-user", root_dir=tmp_path, service=fresh)
    assert persisted["policy"]["cloud_processing_enabled"] is True
    assert persisted["policy"]["permitted_remote"] == {"provider": "grok_cli", "model": "grok-4.7"}

    disabled = set_privacy_policy("chat-user", "local", root_dir=tmp_path)
    assert disabled["updated"] is True
    assert disabled["policy"]["cloud_processing_enabled"] is False
    again = get_privacy_policy("chat-user", service=_service(tmp_path))
    assert again["policy"]["processing_mode"] == "local_private"
    assert again["policy"]["cloud_processing_enabled"] is False

    wrong = set_privacy_policy("chat-user", "grok", case_id="some-other-case", root_dir=tmp_path)
    assert wrong["updated"] is False
    assert wrong["load"]["cloud_processing_enabled"] is False
    assert get_privacy_policy("chat-user", service=_service(tmp_path))["policy"]["cloud_processing_enabled"] is False


def test_local_mode_blocks_three_egresses_and_status(
    tmp_path: Path,
    spies: _Spy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.ipfs_datasets.llm as llm
    from applications.complaint_workspace import _llm_router_status_snapshot

    monkeypatch.setenv("IPFS_DATASETS_PY_LLM_PROVIDER", "hf_router")
    monkeypatch.setenv("COMPLAINT_LLM_PROVIDER", "hf_router")
    monkeypatch.setenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "openrouter")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    monkeypatch.setenv("COMPLAINT_USE_IPFS_LLM_ROUTER_STATUS", "1")

    service = _service(tmp_path)
    user_id = "egress-user"
    _seed_draft(service, user_id, f"Draft body that must stay local. {MARKER}")

    grounded = service.generate_grounded_text(
        user_id,
        prompt=f"Rewrite {MARKER}",
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
    )
    _assert_quiet(spies, grounded)
    assert grounded["generation"]["error"] == "privacy_denied:cloud_processing_disabled"
    assert grounded["text"] == ""

    def _score(*_args, **_kwargs):
        return {
            "grade": "C",
            "overall_score": 10,
            "suggestions": [{"priority": "high", "action": f"tighten {MARKER}", "dimension": "form"}],
        }

    monkeypatch.setattr("integrations.ipfs_datasets.quality.score_draft_quality", _score)
    improved = service.improve_draft(user_id, provider="openrouter", model="other-model")
    _assert_quiet(spies, {"errors": improved["llm_errors"], "improved": improved["improved"]})
    assert improved["improved"] is False
    assert improved["llm_errors"] == ["privacy_denied:cloud_processing_disabled"]
    assert MARKER not in json.dumps(improved["llm_errors"])

    class _Backend:
        def __init__(self, **kwargs):
            spies.backend += 1
            spies.backend_kwargs.append(kwargs)

        def __call__(self, prompt: str) -> str:
            spies.prompts.append(prompt)
            return "unused"

    monkeypatch.setattr("backends.LLMRouterBackend", _Backend)
    draft = service.generate_complaint(user_id, use_llm=True, provider="hf_router", model="some-model")
    assert spies.backend == 0
    _assert_quiet(spies, {"reason": draft["draft"].get("draft_fallback_reason")})
    assert draft["draft"]["draft_fallback_reason"] == "privacy_denied:cloud_processing_disabled"

    status = llm.llm_router_status(
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
        prompt=MARKER,
        perform_probe=False,
        base_url="https://router.huggingface.co/v1",
    )
    snapshot = _llm_router_status_snapshot()
    _assert_quiet(spies, {"status": status, "snapshot": snapshot})
    assert status["static_capability_only"] is True
    assert status["dispatch"] == "none"
    assert status["probe_performed"] is False
    assert snapshot["probe_performed"] is False

    probed = llm.llm_router_status(
        provider="hf_router",
        model_name="katanemo/Arch-Router-1.5B",
        prompt=MARKER,
        perform_probe=True,
        complaint_privacy_context=llm.build_complaint_privacy_context(
            service.get_privacy_policy(user_id)["policy"],
            user_id=user_id,
            case_id=user_id,
            data_class="raw_intake",
        ),
    )
    _assert_quiet(spies, probed)
    assert probed["error"] == "privacy_denied:cloud_processing_disabled"
    assert probed["probe_performed"] is False


def test_grok_opt_in_is_exact_and_does_not_fall_back(
    tmp_path: Path,
    spies: _Spy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.ipfs_datasets.llm as llm

    monkeypatch.setenv("IPFS_DATASETS_PY_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("HF_TOKEN", TOKEN)
    service = _service(tmp_path)
    user_id = "grok-user"
    service.set_privacy_policy(user_id, "grok")
    _seed_draft(service, user_id, f"Filed body {MARKER}")
    policy = service.get_privacy_policy(user_id)["policy"]
    context = llm.build_complaint_privacy_context(
        policy,
        user_id=user_id,
        case_id=user_id,
        data_class="drafts_proofs",
    )

    denied = llm.generate_text_with_metadata(
        f"send {MARKER} {TOKEN}",
        provider="openrouter",
        model_name="grok-4.7",
        complaint_privacy_context=context,
    )
    _assert_quiet(spies, denied)
    assert denied["error"] == "privacy_denied:grok_scope_mismatch"

    mismatched_model = llm.generate_text_with_metadata(
        MARKER,
        provider="grok_cli",
        model_name="grok-4",
        complaint_privacy_context=context,
    )
    _assert_quiet(spies, mismatched_model)
    assert mismatched_model["error"] == "privacy_denied:grok_scope_mismatch"

    with pytest.raises(RuntimeError) as raised:
        llm.generate_text_via_router(
            f"{MARKER} {TOKEN}",
            provider="grok_cli",
            model_name="grok-4",
            complaint_privacy_context=context,
        )
    assert MARKER not in str(raised.value)
    assert TOKEN not in str(raised.value)
    assert spies.prepare == 0

    allowed = llm.generate_text_with_metadata(
        f"{MARKER} stays in the prompt argument only",
        provider="grok_cli",
        model_name="grok-4.7",
        complaint_privacy_context=context,
    )
    assert spies.provider == 1
    assert spies.architecture == 0
    assert spies.socket == 0
    assert spies.process == 0
    assert allowed["status"] == "available"
    assert MARKER not in json.dumps({key: value for key, value in allowed.items() if key != "prompt"})

    class _Backend:
        def __init__(self, **kwargs):
            spies.backend += 1
            spies.backend_kwargs.append(kwargs)
            self.provider = kwargs.get("provider")
            self.model = kwargs.get("model")
            self.last_result_metadata = {}

        def __call__(self, prompt: str) -> str:
            spies.prompts.append(prompt)
            return "not-a-formal-complaint"

    monkeypatch.setattr("backends.LLMRouterBackend", _Backend)
    refused = service.generate_complaint(user_id, use_llm=True, provider="openrouter", model="grok-4.7")
    assert spies.backend == 0
    assert refused["draft"]["draft_fallback_reason"] == "privacy_denied:grok_scope_mismatch"
    assert MARKER not in str(refused["draft"]["draft_fallback_reason"])

    service.generate_complaint(user_id, use_llm=True, provider="grok_cli", model="grok-4.7")
    assert spies.backend == 1
    assert spies.backend_kwargs[0]["complaint_privacy_context"]["policy"]["permitted_remote"]["provider"] == "grok_cli"
    assert spies.architecture == 0

    probed = llm.llm_router_status(
        provider="grok_cli",
        model_name="grok-4.7",
        prompt=MARKER,
        perform_probe=True,
        complaint_privacy_context=context,
    )
    assert probed["probe_performed"] is True
    assert spies.architecture == 0
    assert spies.socket == 0
    assert spies.process == 0
    assert MARKER not in json.dumps(probed)

    bare_probe = llm.llm_router_status(provider="grok_cli", model_name="grok-4.7", prompt=MARKER, perform_probe=True)
    assert bare_probe["error"] == "privacy_denied:cloud_processing_disabled"
    assert spies.socket == 0
    assert spies.process == 0
