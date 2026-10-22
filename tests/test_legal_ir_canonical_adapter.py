"""Canonical compiler adapter: identities, source maps, and cache invalidation."""

from __future__ import annotations

import pytest

from integrations.ipfs_datasets import logic
from lib.formal_logic.capabilities import (
    CanonicalCompilerSupport,
    LogicCapabilityState,
    classify_canonical_compiler_capability,
)


_VOCABULARY = {
    "actors": ("agency", "company_a"),
    "actions": ("file", "submit", "withdraw"),
    "objects": ("backup_report", "notice"),
    "qualifiers": ("emergency", "natural_disaster", "within_10_days"),
}
_LEGAL_TEXT = "Company A shall submit backup report within 10 days unless emergency."
_UNICODE_TEXT = _LEGAL_TEXT + " café"


@pytest.fixture(autouse=True)
def _clear_canonical_cache() -> None:
    logic.reset_canonical_formalization_cache()
    yield
    logic.reset_canonical_formalization_cache()


def _compile(text: str = _LEGAL_TEXT, **kwargs):
    return logic.compile_canonical_legal_ir(
        text,
        request_id=kwargs.pop("request_id", "proof01-synthetic"),
        vocabulary=kwargs.pop("vocabulary", _VOCABULARY),
        legal_context=kwargs.pop(
            "legal_context",
            {
                "citation": "Synthetic Authority §1",
                "authority_locator": "synthetic:authority-1",
                "authority_version": "law04-synthetic-1",
                "corpus_version": "law04-synthetic-1",
                "source_text": text,
            },
        ),
        **kwargs,
    )


def test_import_alone_is_not_an_implemented_canonical_capability() -> None:
    capability = logic.get_canonical_compiler_capability()
    assert capability.support is not CanonicalCompilerSupport.MISSING_MODULE
    assert capability.state is LogicCapabilityState.DEGRADED
    assert capability.support is CanonicalCompilerSupport.NOT_EXECUTED
    assert capability.implemented is False
    assert capability.executed is False

    imported_only = classify_canonical_compiler_capability(
        {"module_present": True, "executed": False, "status": "success", "traceable": True, "source_map_valid": True}
    )
    assert imported_only.implemented is False
    assert imported_only.support is CanonicalCompilerSupport.NOT_EXECUTED


def test_supported_compile_stores_identities_diagnostics_and_traces() -> None:
    user_fact = "The complainant missed a filing on 1 March 2024."
    payload = _compile(user_facts=[user_fact])

    assert payload["status"] == "success"
    assert payload["capability"]["status"] == "implemented"
    assert payload["capability"]["executed"] is True
    assert payload["capability"]["support"] == "executed"
    assert payload["reused"] is False
    identities = payload["identities"]
    assert identities["compiler_interface"]
    assert identities["compiler_config_cid"]
    assert identities["policy_cid"]
    assert identities["pipeline_interface"]
    assert identities["pipeline_cid"] == payload["pipeline_cid"]
    assert identities["source_map_schema"]
    assert identities["stage_ids"]
    assert [stage["stage_id"] for stage in payload["stages"]] == identities["stage_ids"]
    assert payload["unsupported_diagnostics"]
    assert any(item.get("origin", "").startswith("stage.") for item in payload["unsupported_diagnostics"])
    assert payload["source_map_validation"]["valid"] is True
    assert payload["built_source_map_validation"]["valid"] is True
    assert payload["traceability"]["traceable"] is True
    assert payload["traceability"]["missing_fact_ids"] == []
    assert payload["formula_ids"]
    assert payload["entails_applicability"] is False
    assert payload["entails_claim"] is False
    assert payload["user_facts_included_in_source"] is False
    assert user_fact not in payload["source_text"]
    assert payload["authority_version"] == "law04-synthetic-1"
    assert payload["legal_text_origin"] == "legal_context"

    for formula_id in payload["formula_ids"]:
        trace = next(item for item in payload["traces"] if item["fact_id"] == formula_id)
        assert trace["traceable"] is True
        assert trace["source_spans"]
        assert trace["transformation_steps"]
        assert trace["source_spans"][0]["normalized_text"]
    for passage in payload["passages"]:
        assert payload["source_text"][passage["start"]:passage["end"]] == passage["passage"]
        assert passage["span_unit"] == "character"
        assert passage["source_cid"] == payload["source_cid"]

    assert logic.get_canonical_compiler_capability().implemented is True
    stored = logic.inspect_canonical_formalization_receipt(payload["receipt_id"])
    assert stored is not None
    assert stored["status"] == "success"
    assert stored["result_cid"] == payload["result_cid"]


def test_cache_reuse_and_schema_mismatch_keeps_old_receipt() -> None:
    first = _compile()
    assert first["status"] == "success"
    second = _compile()
    assert second["reused"] is True
    assert second["cache_outcome"] == "reused"
    assert second["receipt_id"] == first["receipt_id"]

    mismatched = _compile(expected_pipeline_cid="baguqeera" + "a" * 50)
    assert mismatched["status"] == "schema_mismatch"
    assert mismatched["reused"] is False
    assert mismatched["cache_outcome"] == "invalidated"
    assert "pipeline_cid" in mismatched["mismatched_fields"]
    assert mismatched["capability"]["implemented"] is False
    assert mismatched["capability"]["support"] == "schema_mismatch"
    assert mismatched["prior_receipt_id"] == first["receipt_id"]
    inspected = logic.inspect_canonical_formalization_receipt(first["receipt_id"])
    assert inspected is not None
    assert inspected["status"] == "success"
    assert inspected["source_map_validation"]["valid"] is True

    schema_mismatch = _compile(expected_schema_version="legal-ir-source-map-v0")
    assert schema_mismatch["status"] == "schema_mismatch"
    assert "source_map_schema" in schema_mismatch["mismatched_fields"]
    assert logic.inspect_canonical_formalization_receipt(first["receipt_id"])["status"] == "success"


def test_unicode_spans_are_characters_and_tamper_is_typed() -> None:
    payload = _compile(_UNICODE_TEXT)
    assert payload["status"] == "success"
    assert payload["source_character_length"] == len(_UNICODE_TEXT)
    assert payload["source_byte_length"] == len(_UNICODE_TEXT.encode("utf-8"))
    assert payload["source_character_length"] != payload["source_byte_length"]
    assert any(passage["end"] == len(_UNICODE_TEXT) for passage in payload["passages"])
    assert all(passage["end"] <= len(_UNICODE_TEXT) for passage in payload["passages"])
    assert "café" in payload["source_text"]
    cafe_passages = [item for item in payload["passages"] if "café" in item["passage"]]
    assert cafe_passages
    assert cafe_passages[0]["passage"] == _UNICODE_TEXT[cafe_passages[0]["start"]:cafe_passages[0]["end"]]

    audited = logic.verify_canonical_formalization_receipt(
        payload["receipt_id"],
        source_text=_UNICODE_TEXT.replace("café", "cafe"),
    )
    assert audited["status"] == "tampered"
    assert audited["tampered"] is True
    assert audited["capability"]["support"] == "tampered"
    assert audited["capability"]["implemented"] is False
    assert logic.inspect_canonical_formalization_receipt(payload["receipt_id"])["status"] == "success"

    mutated = dict(payload)
    mutated["passages"] = [dict(payload["passages"][0], passage="not-the-source")]
    mutated_audit = logic.audit_canonical_formalization_payload(mutated)
    assert mutated_audit["tampered"] is True
    assert any(item["code"] == "passage_tampered" for item in mutated_audit["issues"])


def test_abstain_partial_and_failed_compiles_are_not_success() -> None:
    empty = _compile("This paragraph contains no normative rule.")
    assert empty["status"] == "failed"
    assert empty["capability"]["implemented"] is False
    assert empty["source_map"] is None

    unmapped = "Company A shall submit backup report. Unknown party must invent widgets."
    abstained = _compile(unmapped, allow_explicit_partial=False)
    assert abstained["status"] == "abstained"
    assert abstained["capability"]["support"] == "unsupported"
    assert abstained["unsupported_diagnostics"]

    partial = _compile(unmapped, allow_explicit_partial=True, request_id="proof01-partial")
    assert partial["status"] == "partial"
    assert partial["capability"]["support"] == "partial"
    assert partial["capability"]["implemented"] is False
    assert partial["source_map_validation"]["valid"] is True
    assert partial["traceability"]["traceable"] is True


def test_missing_module_stays_typed_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logic, "_canonical_pipeline_module", None)
    monkeypatch.setattr(logic, "_canonical_pipeline_error", RuntimeError("canonical pipeline missing"))
    monkeypatch.setattr(logic, "_canonical_contracts_module", None)
    monkeypatch.setattr(logic, "_canonical_compiler_module", None)
    monkeypatch.setattr(logic, "_canonical_source_map_module", None)

    capability = logic.get_canonical_compiler_capability()
    assert capability.state is LogicCapabilityState.UNAVAILABLE
    assert capability.support is CanonicalCompilerSupport.MISSING_MODULE
    assert capability.implemented is False

    payload = _compile()
    assert payload["status"] == "unavailable"
    assert payload["capability"]["status"] == "unavailable"
    assert payload["metadata"]["backend_available"] is False
    assert "canonical pipeline missing" in payload["reason"]


def test_user_facts_do_not_replace_versioned_legal_text() -> None:
    payload = logic.compile_canonical_legal_ir(
        "The complainant says the company was unfair.",
        request_id="proof01-separation",
        vocabulary=_VOCABULARY,
        legal_context={
            "citation": "Synthetic Authority §1",
            "authority_version": "law04-synthetic-1",
            "source_text": _LEGAL_TEXT,
        },
        user_facts=["The complainant says the company was unfair."],
    )
    assert payload["status"] == "success"
    assert payload["source_text"] == _LEGAL_TEXT
    assert payload["legal_text_origin"] == "legal_context"
    assert payload["entails_applicability"] is False
    assert payload["entails_claim"] is False
