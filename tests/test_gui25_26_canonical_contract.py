"""Real local-source/Mediator contract regressions; no live provider qualification.

The source rows are authored MGND fixtures passed through the actual Data-backed
acquisition adapter. The constructor, phase owner, storage owner and admission
method are production objects. These contract tests do not stand in for issued
browser/key/session or encrypted Workspace integration tests.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from applications.legal_research_api import (
    LegalResearchError,
    _index_acquired_passages,
    review_versioned_authority,
)
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.logic import prepare_acquired_authority_record
from tests.mgnd_fixtures import meaningful_cases
from tests.test_cimp_mgnd_17 import _acquire, _case_file, _mediator

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _real_source(tmp_path):
    authored = next(case for case in meaningful_cases() if case.label == "baseline")
    acquisition = _acquire(authored)
    assert acquisition["status"] == "candidates"
    candidate = acquisition["candidates"][0]
    assert candidate["applicability"] == "unknown"
    assert candidate["proof"] is False
    assert candidate["applicable"] is False
    assert candidate["retrieval"]["effective_date"]
    mediator = _mediator(tmp_path)
    case_file = _case_file(authored)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
    authority = SimpleNamespace(actor_principal_id="synthetic-mgnd-17", case_id=authored.case_id)
    return mediator, case_file, authority, acquisition, candidate


def test_real_mediator_source_admission_is_nested_and_is_not_a_proof(tmp_path):
    mediator, case_file, authority, acquisition, candidate = _real_source(tmp_path)
    outcome = mediator.admit_acquired_authorities(
        acquisition, [{"type": "termination", "name": "Termination"}], case_file,
        user_id=authority.actor_principal_id,
    )
    assert "status" not in outcome
    assert outcome["acquisition"]["status"] == "candidates"
    assert outcome["admission"]["status"] == "admitted"
    assert outcome["admission"]["stored_record_ids"]
    assert outcome["admission"]["proof"] is False
    assert candidate["applicability"] == "unknown"


def test_gui_index_retains_real_canonical_source_before_review(tmp_path):
    mediator, case_file, authority, acquisition, candidate = _real_source(tmp_path)
    _index_acquired_passages(case_file, acquisition)
    stored = next(iter(case_file["legal_source_passage_index"].values()))
    assert stored.get("source_text") == candidate["source_text"]
    assert stored.get("retrieval") == candidate["retrieval"]
    assert stored.get("law_query_date") == candidate["law_query_date"]
    assert stored["applicability"] == "unknown"
    prepared = prepare_acquired_authority_record(stored, jurisdiction="OR", as_of_date="2024-03-15")
    assert prepared["status"] == "admitted", prepared.get("reason")
    assert prepared["record"]["content"] == candidate["source_text"]


def _unknown_review(candidate, *, operation_id="synthetic-source-review"):
    return {
        "decision": "admit", "source_passage": candidate["source_text"],
        "content_hash": candidate["retrieval"]["content_hash"],
        "version": candidate["version"], "authority_identity": candidate["locator"],
        "jurisdiction": "", "effective_date": candidate["retrieval"]["effective_date"],
        "applicability": "unknown", "exceptions": None, "treatment_state": "unknown",
        "operation_id": operation_id,
    }


def test_real_unknown_applicability_is_recorded_unresolved_without_invented_law(tmp_path):
    mediator, case_file, authority, acquisition, candidate = _real_source(tmp_path)
    _index_acquired_passages(case_file, acquisition)
    record = review_versioned_authority(
        mediator, object(), authority, _unknown_review(candidate), membership="owner",
        canonical_owner_principal_id="synthetic-canonical-owner",
    )
    assert record["status"] == "unresolved"
    assert record["admitted_law"] is False and record["proof"] is False
    assert record["applicability"] == "unknown"
    assert record["treatment_state"] == "unknown"
    assert record["exceptions"] is None
    assert record["reason"] in {"applicability_unresolved", "source_metadata_unresolved"}
    assert case_file["legal_authority_admissions"][-1] == record


def test_review_operation_id_cannot_replay_different_context_fields(tmp_path):
    mediator, case_file, authority, acquisition, candidate = _real_source(tmp_path)
    _index_acquired_passages(case_file, acquisition)
    body = _unknown_review(candidate)
    review_versioned_authority(mediator, object(), authority, body, membership="owner")
    changed = deepcopy(body)
    changed["jurisdiction"] = "different-explicit-scope"
    with pytest.raises(LegalResearchError, match="legal_research_revision_conflict"):
        review_versioned_authority(mediator, object(), authority, changed, membership="owner")
