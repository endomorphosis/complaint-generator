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


def _modal_document(text: str | None = None, *, formula_id: str = "f1", end: int | None = None, duplicate: bool = False):
    from ipfs_datasets_py.optimizers.logic_theorem_optimizer.modal_ir import (
        ModalIRDocument,
        ModalIRFormula,
        ModalIROperator,
        ModalIRPredicate,
        ModalIRProvenance,
    )

    body = text if text is not None else "The agency shall provide notice unless emergency conditions exist within 30 days."
    stop = len(body) if end is None else end
    formulas = [
        ModalIRFormula(
            formula_id=formula_id,
            operator=ModalIROperator(family="deontic", system="KD", symbol="shall", label="shall"),
            predicate=ModalIRPredicate(name="provide_notice", arguments=["agency", "notice"], role="obligation"),
            provenance=ModalIRProvenance(source_id="doc-proof02", start_char=0, end_char=stop, citation="Synthetic §1"),
            conditions=["within 30 days"],
            exceptions=["emergency conditions exist"],
        )
    ]
    if duplicate:
        formulas.append(
            ModalIRFormula(
                formula_id=formula_id,
                operator=ModalIROperator(family="deontic", system="KD", symbol="may", label="may"),
                predicate=ModalIRPredicate(name="delay_notice", arguments=["agency"], role="permission"),
                provenance=ModalIRProvenance(source_id="doc-proof02", start_char=0, end_char=len(body), citation="Synthetic §1"),
                conditions=[],
                exceptions=[],
            )
        )
    return ModalIRDocument(document_id="doc-proof02", source="synthetic", normalized_text=body, formulas=formulas)


def _premise_kwargs(text: str):
    return dict(
        claim_id="claim-retaliation",
        element_id="element-protected-activity",
        legal_context_version="law06-v1",
        coverage_status="supported",
        asserted_facts=[
            {
                "fact_id": "fact-asserted",
                "text": "The agency",
                "revision": "fact-rev-1",
                "span_unit": "character",
                "char_start": 0,
                "char_end": len("The agency"),
            }
        ],
        disputed_facts=[
            {
                "fact_id": "fact-disputed",
                "text": "The company denies the report.",
                "revision": "fact-rev-1",
                "disputed": True,
            }
        ],
        selected_legal_rules=[
            {
                "rule_id": "rule-notice",
                "citation": "Synthetic Authority §1",
                "version": "law06-v1",
                "authority_version": "law06-v1",
                "applicable": True,
                "text": text,
                "span_unit": "character",
                "char_start": 0,
                "char_end": len(text),
            }
        ],
        assumptions=[
            {
                "assumption_id": "assume-deadline",
                "label": "deadline-runs-from-notice",
                "text": "PRIVATE-ASSUMPTION-TEXT deadline runs from notice.",
                "revision": "assumption-rev-1",
            }
        ],
        missing_facts=[{"fact_id": "fact-missing", "text": "Date of the decision.", "revision": "missing"}],
        structural_validation={"valid": True, "coverage_status": "supported"},
        source_text=text,
    )


def test_generator_replay_is_stable_and_structural_only() -> None:
    document = _modal_document()
    text = document.normalized_text
    first = logic.generate_bound_legal_ir_proof_obligations(document, **_premise_kwargs(text))
    second = logic.generate_bound_legal_ir_proof_obligations(document, **_premise_kwargs(text))

    assert first["status"] == "success"
    assert second["reused"] is True
    assert second["receipt_id"] == first["receipt_id"]
    assert second["execution_identity"] == first["execution_identity"]
    assert first["native_obligation_ids"] == [item["obligation_id"] for item in first["obligations"]]
    assert first["native_schema_versions"] == ["legal-ir-proof-obligation-v1"]
    assert first["obligations"][0]["obligation_id"].startswith("lir-obligation-")
    assert first["entails_claim_element"] is False
    assert first["substantive_entailment"] is False
    assert first["structural_validation_is_entailment"] is False
    assert first["coverage_status_promoted_to_proof"] is False
    assert first["complete_coverage"] is False
    assert first["complete_coverage_certificate"] is None
    assert first["trust_level"] == "structural"
    assert first["backend"]["identity"].endswith("generate_legal_ir_proof_obligations")
    assert first["backend"]["available"] is True
    assert first["versions"]["checker_version"]
    assert first["versions"]["policy_version"]
    assert first["versions"]["claim_id"] == "claim-retaliation"
    assert first["versions"]["element_id"] == "element-protected-activity"
    assert first["source_spans_verified"] is True
    assert first["source_span_checks"][0]["native_hash_matches_verified_source"] is True
    kinds = set(first["obligation_kinds"])
    assert "modal_well_formedness" in kinds
    assert "provenance_preservation" in kinds
    inventory = first["premise_inventory"]
    assert [item["premise_id"] for item in inventory["asserted_facts"]] == ["fact-asserted"]
    assert inventory["asserted_facts"][0]["epistemic_status"] == "allegation"
    assert inventory["asserted_facts"][0]["axiom"] is False
    assert inventory["asserted_facts"][0]["source_validated"] is True
    assert inventory["disputed_facts"][0]["epistemic_status"] == "disputed"
    assert inventory["disputed_facts"][0]["axiom"] is False
    assert inventory["selected_legal_rules"][0]["premise_id"] == "rule-notice"
    assert inventory["selected_legal_rules"][0]["source_validated"] is True
    assert inventory["assumptions"][0]["label"] == "deadline-runs-from-notice"
    assert inventory["missing_facts"][0]["epistemic_status"] == "missing"
    assert inventory["axioms"] == []
    assert inventory["coverage_status_is_proof"] is False
    assert first["assumptions"] == [
        {"premise_id": "assume-deadline", "label": "deadline-runs-from-notice", "revision": "assumption-rev-1"}
    ]
    trace_blob = str(first["operational_trace"]) + str(first["reason"])
    assert "PRIVATE-ASSUMPTION-TEXT" not in trace_blob
    assert "The company denies" not in trace_blob


def test_metadata_and_source_version_changes_keep_native_ids_and_old_receipt() -> None:
    document = _modal_document()
    text = document.normalized_text
    original = logic.generate_bound_legal_ir_proof_obligations(document, **_premise_kwargs(text))
    changed = logic.generate_bound_legal_ir_proof_obligations(
        document,
        **{**_premise_kwargs(text), "legal_context_version": "law06-v2"},
    )
    assert changed["reused"] is False
    assert changed["execution_identity"] != original["execution_identity"]
    assert changed["native_obligation_ids"] == original["native_obligation_ids"]
    assert changed["prior_receipt_id"] == original["receipt_id"]
    inspected = logic.inspect_bound_proof_obligation_receipt(original["receipt_id"])
    assert inspected is not None
    assert inspected["status"] == "success"
    assert inspected["versions"]["legal_context_version"] == "law06-v1"

    revised = logic.generate_bound_legal_ir_proof_obligations(
        document,
        **{
            **_premise_kwargs(text),
            "asserted_facts": [
                {
                    "fact_id": "fact-asserted",
                    "text": "The agency",
                    "revision": "fact-rev-2",
                    "span_unit": "character",
                    "char_start": 0,
                    "char_end": len("The agency"),
                }
            ],
        },
    )
    assert revised["execution_identity"] != original["execution_identity"]
    assert revised["native_obligation_ids"] == original["native_obligation_ids"]
    assert logic.inspect_bound_proof_obligation_receipt(original["receipt_id"])["status"] == "success"


def test_missing_and_unicode_spans_and_duplicate_labels() -> None:
    text = "The agency shall provide notice. café"
    missing = logic.generate_bound_legal_ir_proof_obligations(
        _modal_document(text, end=len(text) + 8),
        claim_id="claim",
        element_id="element",
        source_text=text,
    )
    assert missing["status"] == "source_unverified"
    assert missing["source_spans_verified"] is False
    check = missing["source_span_checks"][0]
    assert check["native_span_hash_is_fallback"] is True
    assert check["verified_source_sha256"] == ""
    assert check["native_hash_matches_verified_source"] is False
    assert check["native_source_span_sha256"]
    assert missing["entails_claim_element"] is False

    unicode_doc = _modal_document(text)
    verified = logic.generate_bound_legal_ir_proof_obligations(unicode_doc, source_text=text, claim_id="c", element_id="e")
    assert verified["status"] == "success"
    span = verified["source_span_checks"][0]
    assert span["character_length"] == len(text)
    assert span["byte_length"] == len(text.encode("utf-8"))
    assert span["character_length"] != span["byte_length"]
    assert span["verified"] is True

    cafe = "café"
    byte_start = text.encode("utf-8").find(cafe.encode("utf-8"))
    inventory = logic.build_legal_ir_premise_inventory(
        asserted_facts=[
            {
                "fact_id": "fact-cafe",
                "text": cafe,
                "revision": "r1",
                "span_unit": "utf8_byte",
                "byte_start": byte_start,
                "byte_end": byte_start + len(cafe.encode("utf-8")),
            }
        ],
        source_text=text,
    )
    assert inventory["asserted_facts"][0]["source_validated"] is True
    assert inventory["asserted_facts"][0]["provenance"]["span_unit"] == "utf8_byte"
    assert inventory["asserted_facts"][0]["epistemic_status"] == "allegation"

    duplicated = logic.generate_bound_legal_ir_proof_obligations(_modal_document(duplicate=True), claim_id="c", element_id="e")
    assert duplicated["duplicate_local_labels"]
    assert duplicated["duplicate_local_labels"][0]["formula_id"] == "f1"
    assert len(duplicated["duplicate_local_labels"][0]["binding_ids"]) == 2
    assert duplicated["duplicate_local_labels"][0]["binding_ids"][0] != duplicated["duplicate_local_labels"][0]["binding_ids"][1]


def test_truncation_empty_formulas_pipeline_result_and_missing_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _modal_document()
    bounded = logic.generate_bound_legal_ir_proof_obligations(document, max_obligations=3, claim_id="c", element_id="e")
    assert bounded["status"] == "truncated"
    assert bounded["truncated"] is True
    assert bounded["obligation_count"] == 3
    assert bounded["complete_coverage"] is False
    assert bounded["complete_coverage_certificate"] is None
    assert bounded["unbounded_obligation_count"] > 3
    assert bounded["entails_claim_element"] is False

    from ipfs_datasets_py.optimizers.logic_theorem_optimizer.modal_ir import ModalIRDocument

    empty = logic.generate_bound_legal_ir_proof_obligations(
        ModalIRDocument(document_id="empty", source="synthetic", normalized_text="No modal cues here.", formulas=[]),
        claim_id="c",
        element_id="e",
    )
    assert empty["status"] == "presence_diagnostic"
    assert empty["presence_diagnostic"] is True
    assert empty["obligations"][0]["kind"] == "modal_formula_presence"
    assert empty["entails_claim_element"] is False

    class CompilerPipelineResult:
        def __init__(self) -> None:
            self.pipeline_cid = "pipeline"
            self.result = object()

    rejected = logic.generate_bound_legal_ir_proof_obligations(CompilerPipelineResult(), claim_id="c", element_id="e")
    assert rejected["status"] == "unsupported"
    assert rejected["support"] == "unsupported"
    assert rejected["obligations"] == []
    assert rejected["entails_claim_element"] is False
    assert any(item["code"] == "pipeline_result_not_modal_ir" for item in rejected["operational_trace"])

    monkeypatch.setattr(logic, "_legal_ir_obligations_module", None)
    missing = logic.generate_bound_legal_ir_proof_obligations(document, claim_id="c", element_id="e")
    assert missing["status"] == "unavailable"
    assert missing["support"] == "unsupported"
    assert missing["backend"]["available"] is False
    assert missing["trust_level"] == "unavailable"
    assert missing["obligations"] == []
    assert missing["entails_claim_element"] is False


def test_canonical_receipt_bridge_binds_character_spans() -> None:
    compiled = _compile()
    assert compiled["status"] == "success"
    bridged = logic.modal_ir_from_canonical_formalization(compiled)
    assert bridged["bridge"] == "proof01_canonical_formalization_receipt"
    assert bridged["formulas"]
    assert bridged["formulas"][0]["provenance"]["span_unit"] == "character"
    artifact = logic.generate_bound_legal_ir_proof_obligations(
        canonical_receipt=compiled,
        claim_id="claim-canonical",
        element_id="element-rule",
        legal_context_version="law04-synthetic-1",
        selected_legal_rules=[
            {
                "rule_id": compiled["formula_ids"][0],
                "version": "law04-synthetic-1",
                "applicable": True,
                "text": compiled["source_text"],
                "span_unit": "character",
                "char_start": 0,
                "char_end": len(compiled["source_text"]),
            }
        ],
        structural_validation={"valid": True},
    )
    assert artifact["bridge"] == "proof01_canonical_formalization_receipt"
    assert artifact["status"] in {"success", "source_unverified"}
    assert artifact["source_spans_verified"] is True
    assert artifact["versions"]["source_map_identity"]
    assert artifact["versions"]["legal_context_version"] == "law04-synthetic-1"
    assert artifact["structural_validation"]["valid"] is True
    assert artifact["structural_validation_is_entailment"] is False
    assert artifact["entails_claim_element"] is False
    assert artifact["native_schema_versions"] == ["legal-ir-proof-obligation-v1"]


def test_claim_support_hook_keeps_source_proof_and_does_not_relabel_heuristics() -> None:
    from unittest.mock import Mock

    from mediator.claim_support_hooks import ClaimSupportHook

    hook = ClaimSupportHook(Mock(), db_path=":memory:")
    text = "The agency shall provide notice unless emergency conditions exist within 30 days."
    element = {
        "element_id": "element-1",
        "claim_id": "claim-1",
        "element_text": "Protected activity",
        "status": "supported",
        "support_by_kind": {},
        "missing_support_kinds": ["document"],
        "source_text": text,
        "legal_context_version": "law06-v1",
        "modal_ir": _modal_document(text),
        "assumptions": [
            {
                "assumption_id": "assume-1",
                "label": "notice-was-required",
                "text": "PRIVATE-ASSUMPTION-TEXT notice was required.",
                "revision": "a1",
            }
        ],
        "selected_legal_rules": [
            {
                "rule_id": "rule-1",
                "version": "law06-v1",
                "applicable": True,
                "text": "shall provide notice",
            }
        ],
        "support_traces": [
            {
                "fact_id": "fact-1",
                "support_ref": "ref-1",
                "support_kind": "evidence",
                "source_table": "evidence",
                "fact_text": "The complainant reported the issue.",
                "confidence": 0.4,
                "revision": "fact-rev-1",
                "content_hash": "abc123",
                "proof_path_id": "path-1",
                "graph_id": "graph-1",
                "source_passage": {"start_char": 0, "end_char": 10},
                "byte_start": 0,
                "byte_end": 10,
                "record_summary": {"citation": "Synthetic §1", "authority_version": "law06-v1"},
            }
        ],
    }
    predicates = hook._build_reasoning_predicates("retaliation", element, [])
    support = next(item for item in predicates if item["predicate_type"] == "support_trace")
    assert support["source_proof"]["proof_path_id"] == "path-1"
    assert support["source_proof"]["content_hash"] == "abc123"
    assert support["source_proof"]["graph_id"] == "graph-1"
    assert support["source_proof"]["character_span"]["span_unit"] == "character"
    assert support["source_proof"]["utf8_byte_span"]["span_unit"] == "utf8_byte"
    assert support["source_proof"]["dual_provenance"] is True
    assert support["source_proof"]["axiom"] is False
    assert support["source_proof"]["epistemic_status"] == "allegation"
    assert support["source_proof"]["authority_version"] == "law06-v1"

    diagnostics = hook._run_element_reasoning_diagnostics(
        "retaliation",
        element,
        [{"contradiction_id": "c-1", "texts": ["The company denies the report."], "revision": "d1"}],
    )
    artifact = diagnostics["legal_ir_proof_obligations"]
    assert artifact["entails_claim_element"] is False
    assert artifact["substantive_entailment"] is False
    assert artifact["coverage_status_promoted_to_proof"] is False
    assert diagnostics["substantive_entailment"] is False
    assert diagnostics["legacy_proof_heuristic"]["is_substantive_entailment"] is False
    assert diagnostics["legacy_proof_heuristic"]["labels_supported_coverage_provable"] is True
    inventory = artifact["premise_inventory"]
    assert inventory["asserted_facts"][0]["premise_id"] == "fact-1"
    assert inventory["asserted_facts"][0]["epistemic_status"] == "allegation"
    assert any(item["premise_id"] == "c-1" for item in inventory["disputed_facts"])
    assert inventory["selected_legal_rules"][0]["version"] == "law06-v1"
    assert inventory["assumptions"][0]["label"] == "notice-was-required"
    assert inventory["missing_facts"]
    assert inventory["axioms"] == []
    assert "PRIVATE-ASSUMPTION-TEXT" not in str(artifact["operational_trace"])
    assert artifact["native_obligation_ids"]
    assert diagnostics["logic_proof"].get("provable_elements") is not None
    # The legacy heuristic may still call supported coverage provable. The bound artifact does not.
    assert artifact["trust_level"] == "structural"
