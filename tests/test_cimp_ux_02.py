"""Inventory pinned A/Data/Kit origins against the thirteen mediator hooks.

Observations use the declared checkouts, synthetic sources, and the real
private-artifact sealer. Registered operations stay unavailable. Newer
upstream methods are recorded and not adopted.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from applications.complaint_workspace import WorkspaceAccess
from integrations.ipfs_accelerate.routers import pinned_grok47_dispatch_kwargs
from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS, record_sdk_owner_identities
from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode
from integrations.private_storage import store_private_artifact
from mediator.claim_support_hooks import ClaimSupportHook
from mediator.evidence_hooks import EvidenceAnalysisHook, EvidenceStateHook, EvidenceStorageHook
from mediator.hook_runtime import (
    LEGAL_EVIDENCE_OPERATIONS,
    bind_hook_execution_context,
    dispatch_registered_hook_operation,
    operation_handler_call_count,
    register_legal_evidence_operations,
)
from mediator.legal_authority_hooks import (
    LegalAuthorityAnalysisHook,
    LegalAuthoritySearchHook,
    LegalAuthorityStorageHook,
)
from mediator.legal_hooks import (
    LegalClassificationHook,
    QuestionGenerationHook,
    StatuteRetrievalHook,
    SummaryJudgmentHook,
)
from mediator.web_evidence_hooks import WebEvidenceIntegrationHook, WebEvidenceSearchHook


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "ux" / "complaint_ux_overhaul" / "sdk_hook_inventory.json"
_COMMIT = __import__("re").compile(r"^[0-9a-f]{40}$")
_PLAINTEXT = b"synthetic-cimp-ux-02-private-source"
_SENTENCE = "Ada met Bob at the office."

_HOOKS = (
    (LegalClassificationHook, "classify_complaint", "legal_classifier"),
    (StatuteRetrievalHook, "retrieve_statutes", "statute_retriever"),
    (SummaryJudgmentHook, "generate_requirements", "summary_judgment"),
    (QuestionGenerationHook, "generate_questions", "question_generator"),
    (EvidenceStorageHook, "store_evidence", "evidence_storage"),
    (EvidenceStateHook, "upsert_evidence_record", "evidence_state"),
    (EvidenceAnalysisHook, "analyze_evidence_for_claim", "evidence_analysis"),
    (ClaimSupportHook, "get_claim_support_gaps", "claim_support"),
    (LegalAuthoritySearchHook, "lookup_bounded_corpus", "legal_authority_search"),
    (LegalAuthorityStorageHook, "store_acquired_authority", "legal_authority_storage"),
    (LegalAuthorityAnalysisHook, "analyze_authorities_for_claim", "legal_authority_analysis"),
    (WebEvidenceSearchHook, "search_for_evidence", "web_evidence_search"),
    (WebEvidenceIntegrationHook, "discover_and_store_evidence", "web_evidence_integration"),
)


def _inventory() -> dict:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _prefer_pinned_checkout(owner: str) -> None:
    checkout = ROOT / "external" / owner
    entry = str(checkout)
    if checkout.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
    loaded = sys.modules.get(owner)
    origin = str(getattr(loaded, "__file__", "") or "")
    if loaded is not None and f"/external/{owner}/" not in origin.replace("\\", "/"):
        for name in list(sys.modules):
            if name == owner or name.startswith(owner + "."):
                del sys.modules[name]
        if entry not in sys.path:
            sys.path.insert(0, entry)


class _CipherBackend:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.seen: list[bytes] = []

    def add_bytes(self, data: bytes, pin: bool = True) -> dict[str, object]:
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        self.blobs["bafysyntheticcimpux02"] = blob
        return {"success": True, "cid": "bafysyntheticcimpux02", "pinned": False, "stored_local": True, "backend_name": "synthetic"}

    def cat(self, cid: str) -> bytes:
        if cid not in self.blobs:
            raise FileNotFoundError(cid)
        return self.blobs[cid]


def _legal_context() -> dict:
    empty = {"role": "event_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True}
    return {
        "status": "unknown",
        "jurisdiction": "unknown",
        "jurisdiction_explicit": False,
        "context_revision": 1,
        "applicable_law_date": dict(empty, role="applicable_law_date"),
        "event_date": empty,
        "filing_reference_date": dict(empty, role="filing_reference_date"),
        "corpus_retrieval_date": dict(empty, role="corpus_retrieval_date"),
    }


def _privacy(owner_id: str, case_id: str) -> dict:
    policy = privacy_policy_for_mode(owner_id, case_id, "local")
    return build_complaint_privacy_context(policy, user_id=owner_id, case_id=case_id, data_class="fact_kg")


def _authorized_request(operation: str) -> tuple[object, dict, dict]:
    owner_id = "synthetic-ux02-owner"
    case_id = "synthetic-ux02-case"
    privacy = _privacy(owner_id, case_id)
    source_hash = "ab" * 32
    context = bind_hook_execution_context(
        operation=operation,
        owner_id=owner_id,
        case_id=case_id,
        session_id="session-ux02",
        session_revision=1,
        graph_revision="gr-ux02-1",
        legal_context=_legal_context(),
        purpose=operation,
        deadline=datetime(2026, 12, 1, tzinfo=timezone.utc),
        source_bindings=[{"source_id": "src-ux02", "content_hash": source_hash}],
        privacy_context=privacy,
    )
    request = {
        "operation": operation,
        "role": "extract_facts",
        "target_ref": "target.ux02",
        "source_refs": [{"source_id": "src-ux02", "content_hash": source_hash}],
    }
    if operation == "acquire_legal_sources":
        request["citation_ref"] = "citation.ux02"
    elif operation == "ingest_private_evidence":
        request["evidence_ref"] = "evidence.ux02"
    else:
        request["graph_revision"] = "gr-ux02-1"
    return context, request, privacy


def test_inventory_matches_pinned_origins_and_unreadable_revisions() -> None:
    inventory = _inventory()
    observed = {row["name"]: row for row in record_sdk_owner_identities()}
    assert [row["name"] for row in inventory["owners"]] == ["ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"]
    for row in inventory["owners"]:
        live = observed[row["name"]]
        assert row["declared_pin"] == DECLARED_OWNER_PINS[row["name"]] == live["declared_pin"]
        assert _COMMIT.fullmatch(row["declared_pin"])
        assert row["relative_path"] == live["relative_path"]
        assert row["checkout_kind"] == live["checkout_kind"]
        assert row["populated"] == live["populated"]
        assert row["checked_out_commit"] == live["checked_out_commit"] == ""
        assert row["checked_out_commit_status"] == live["checked_out_commit_status"] == "unavailable"
        assert row["checked_out_commit_error_type"] == live["checked_out_commit_error_type"]
        assert row["pin_is_observed_head"] is False
        assert live["pin_is_observed_head"] is False
        canonical = ROOT / row["canonical_source_path"]
        assert canonical.is_file() is bool(row["populated"])
    assert inventory["owners"][0]["qualification"] == "unavailable"
    assert inventory["owners"][1]["module_origin"].endswith("ipfs_datasets_py/__init__.py")
    assert inventory["owners"][2]["module_origin"].endswith("ipfs_kit_py/__init__.py")


def test_thirteen_hooks_are_callable_and_not_marked_active() -> None:
    inventory = _inventory()
    rows = inventory["mediator_hooks"]
    assert len(rows) == 13
    assert len({row["hook"] for row in rows}) == 13
    assert [row["mediator_attribute"] for row in rows] == [item[2] for item in _HOOKS]
    mediator_source = (ROOT / "mediator" / "mediator.py").read_text(encoding="utf-8")
    for recorded, (cls, method_name, attribute) in zip(rows, _HOOKS):
        method = getattr(cls, method_name)
        assert callable(method)
        assert recorded["hook"] == cls.__name__
        assert recorded["method"] == method_name
        assert recorded["signature"] == str(inspect.signature(method))
        assert recorded["qualification"] == "callable"
        assert recorded["effect_qualification"] == "unavailable"
        assert f"self.{attribute} = {cls.__name__}(" in mediator_source
        origin = Path(inspect.getfile(cls)).resolve()
        assert origin.is_relative_to(ROOT)
        assert recorded["owner"] == origin.relative_to(ROOT).as_posix()


def test_bounded_adapter_probes_use_synthetic_sources_and_real_private_storage() -> None:
    inventory = _inventory()
    _prefer_pinned_checkout("ipfs_datasets_py")
    from ipfs_datasets_py.knowledge_graphs.extraction.extractor import KnowledgeGraphExtractor
    from ipfs_datasets_py.processors.legal_scrapers.legal_dataset_api import (
        search_us_code_corpus_from_parameters,
    )

    extractor_origin = Path(inspect.getfile(KnowledgeGraphExtractor)).resolve()
    assert "external/ipfs_datasets_py/" in extractor_origin.as_posix()
    basic = getattr(KnowledgeGraphExtractor, "extract_knowledge_graph")
    enhanced = getattr(KnowledgeGraphExtractor, "extract_enhanced_knowledge_graph")
    symbols = {row["symbol"]: row for row in inventory["callable_symbols"]}
    assert symbols["KnowledgeGraphExtractor.extract_knowledge_graph"]["signature"] == str(inspect.signature(basic))
    assert symbols["KnowledgeGraphExtractor.extract_enhanced_knowledge_graph"]["signature"] == str(inspect.signature(enhanced))
    assert symbols["KnowledgeGraphExtractor.extract_enhanced_knowledge_graph"]["qualification"] == "unsupported"
    extractor = KnowledgeGraphExtractor(use_spacy=False, use_transformers=False, use_tracer=False, use_srl=False)
    graph = extractor.extract_knowledge_graph(_SENTENCE, 0.1, 0.1)
    assert type(graph).__name__ == "KnowledgeGraph"
    assert len(getattr(graph, "entities", {}) or {}) == inventory["adapter_probes"]["knowledge_graph"]["entity_count"]
    assert inventory["adapter_probes"]["knowledge_graph"]["enhanced_called"] is False

    legal = asyncio.run(search_us_code_corpus_from_parameters({}))
    assert legal["status"] == "error"
    assert legal["error"] == "query_vector is required"
    assert inventory["adapter_probes"]["legal_search"]["effect_qualification"] == "unavailable"
    assert symbols["search_us_code_corpus_from_parameters"]["signature"] == str(
        inspect.signature(search_us_code_corpus_from_parameters)
    )

    backend = _CipherBackend()
    receipt = store_private_artifact(
        _PLAINTEXT,
        access=WorkspaceAccess.authenticated("tenant-ux02", case_id="case-ux02"),
        tenant_id="tenant-ux02",
        case_id="case-ux02",
        artifact_kind="intake-note",
        revision="rev-ux02",
        key=bytes(range(32)),
        key_id="case-key-ux02",
        backend=backend,
        pin_content=True,
    )
    assert receipt["verified"] is True
    assert _PLAINTEXT not in b"".join(backend.seen)
    assert backend.seen and backend.seen[0] != _PLAINTEXT
    assert symbols["store_private_artifact"]["qualification"] == "active"
    assert symbols["store_private_artifact"]["signature"] == str(inspect.signature(store_private_artifact))
    assert inventory["adapter_probes"]["private_storage"]["plaintext_left_backend"] is False
    assert inventory["adapter_probes"]["private_storage"]["kit_network_enabled"] is False


def test_registered_operations_stay_unavailable_until_prerequisites_are_real() -> None:
    inventory = _inventory()
    calls: list[str] = []
    before = operation_handler_call_count()
    registered = register_legal_evidence_operations()
    assert registered["dispatch_enabled"] is False
    assert [row["operation"] for row in registered["operations"]] == list(LEGAL_EVIDENCE_OPERATIONS)
    recorded = {row["operation"]: row for row in inventory["registered_operations"]}
    for row in registered["operations"]:
        assert recorded[row["operation"]]["owner"] == row["owner"]
        assert recorded[row["operation"]]["qualification"] == "unavailable"
        assert row["handler_enabled"] is False
        assert row["effect_enabled"] is False
        assert all(item["implemented"] is False and item["verified"] is False for item in row["prerequisites"])
        context, request, privacy = _authorized_request(row["operation"])
        result = dispatch_registered_hook_operation(
            request,
            context=context,
            host_targets=("target.ux02",),
            owner_id=context.owner_id,
            case_id=context.case_id,
            session_id=context.session_id,
            session_revision=context.session_revision,
            graph_revision=context.graph_revision,
            legal_context=_legal_context(),
            purpose=context.purpose,
            source_bindings=[{"source_id": "src-ux02", "content_hash": "ab" * 32}],
            privacy_context=privacy,
            now=datetime(2026, 10, 26, tzinfo=timezone.utc),
            key_available=True,
            private_store_available=True,
            derived_index_ready=True,
            persisted_consent_verified=True,
            effect=lambda _receipt: calls.append("effect"),
            handler=lambda _request: calls.append("handler"),
        )
        assert result["status"] == "unavailable"
        assert result["code"] == "prerequisite_unavailable"
        assert result["effect_dispatched"] is False
        assert result["handler_invoked"] is False
        assert result["storage_invoked"] is False
        assert result["writes"] == 0
    unknown = dispatch_registered_hook_operation(
        {"operation": "float_upstream_pin", "role": "extract_facts", "target_ref": "target.ux02", "source_refs": []},
        context=None,
        host_targets=("target.ux02",),
        owner_id="synthetic-ux02-owner",
        case_id="synthetic-ux02-case",
        session_id="session-ux02",
        session_revision=1,
        graph_revision="gr-ux02-1",
        legal_context=_legal_context(),
        purpose="float_upstream_pin",
        source_bindings=[],
        privacy_context=None,
        now=datetime(2026, 10, 26, tzinfo=timezone.utc),
        effect=lambda _receipt: calls.append("effect"),
    )
    assert unknown["status"] == "refused"
    assert unknown["code"] == "unsupported_operation"
    assert calls == []
    assert operation_handler_call_count() == before


def test_kit_router_rejects_unsupported_and_unbound_operations() -> None:
    inventory = _inventory()
    _prefer_pinned_checkout("ipfs_kit_py")
    from ipfs_kit_py.core.operation_registry import (
        AuthorizationRequirement,
        CapabilityTier,
        OperationDefinition,
        OperationRegistry,
        UnsupportedOperationError,
    )
    from ipfs_kit_py.core.service_router import HandlerNotBoundError, ServiceRouter

    origin = Path(inspect.getfile(ServiceRouter)).resolve().as_posix()
    assert "/external/ipfs_kit_py/" in origin
    recorded = next(row for row in inventory["callable_symbols"] if row["symbol"] == "ServiceRouter.dispatch")
    assert recorded["signature"] == str(inspect.signature(ServiceRouter.dispatch))
    assert recorded["qualification"] == "callable"

    def definition(operation_id: str, tier: CapabilityTier) -> OperationDefinition:
        return OperationDefinition(
            operation_id=operation_id,
            version=1,
            request_schema=f"{operation_id}.request",
            result_schema=f"{operation_id}.result",
            error_schema=f"{operation_id}.error",
            capability=f"{operation_id}.capability",
            authorization=AuthorizationRequirement.public(),
            handler_route=f"{operation_id}.route",
            support_tier=tier,
        )

    router = ServiceRouter(OperationRegistry((
        definition("storage.object.experimental", CapabilityTier.UNSUPPORTED),
        definition("storage.object.read", CapabilityTier.PRODUCTION),
    )))
    touched: list[str] = []
    with pytest.raises(UnsupportedOperationError):
        router.dispatch("storage.object.experimental", {"body": _PLAINTEXT})
    with pytest.raises(HandlerNotBoundError):
        router.dispatch("storage.object.read", {"body": _PLAINTEXT})
    assert touched == []
    assert recorded["unsupported_operation_qualification"] == "unsupported"
    assert recorded["unbound_operation_qualification"] == "unavailable"


def test_compatibility_decision_keeps_exact_pins_and_refuses_newer_paths() -> None:
    inventory = _inventory()
    decision = inventory["compatibility_decision"]
    assert decision["policy"] == "exact_declared_pins"
    assert decision["floating_pins"] is False
    assert decision["submodule_update"] is False
    assert decision["branch_or_tag_pins"] is False
    assert decision["adopted_newer_capabilities"] == []
    deferred = {row["capability"]: row for row in decision["deferred"]}
    assert deferred["KnowledgeGraphExtractor.extract_enhanced_knowledge_graph"]["qualification"] == "unsupported"
    assert deferred["site_packages_ipfs_accelerate_py"]["qualification"] == "unsupported"
    accelerate_router = ROOT / "external" / "ipfs_accelerate_py" / "ipfs_accelerate_py" / "llm_router.py"
    assert accelerate_router.is_file() is False
    kwargs = pinned_grok47_dispatch_kwargs()
    facade = next(row for row in inventory["callable_symbols"] if row["symbol"] == "pinned_grok47_dispatch_kwargs")
    assert facade["provider"] == kwargs["provider"] == "grok_cli"
    assert facade["model_name"] == kwargs["model_name"] == "grok-4.7"
    assert kwargs["allow_local_fallback"] is False
    assert kwargs["allow_cross_provider_fallback"] is False
    assert facade["qualification"] == "callable"
    manifest = json.loads((ROOT / inventory["experience_binding"]["baseline_manifest"]).read_text(encoding="utf-8"))
    workspace = next(row for row in manifest["screenshots"] if row["id"] == "02-workspace-desktop")
    assert workspace["state"] == inventory["experience_binding"]["preserved_baseline_state"]
    assert inventory["experience_binding"]["pixels_observed_by_this_inventory"] is False
    assert "No case selected" in inventory["experience_binding"]["preserved_defect"]
