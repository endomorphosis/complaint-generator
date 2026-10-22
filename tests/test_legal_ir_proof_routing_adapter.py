"""Bounded Legal IR proof routing with explicit unknown outcomes."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from integrations.ipfs_datasets.logic import route_bound_legal_ir_proof
from ipfs_datasets_py.logic.integration.reasoning.legal_ir_obligations import (
    LegalIRProofObligation,
)
from ipfs_datasets_py.logic.integration.reasoning.legal_ir_proof_router import (
    LegalIRProofRouter,
    ProofRoutingPolicy,
)


def _budgets():
    return {
        "deterministic": 0.4,
        "native_logic": 0.4,
        "smt_atp": 0.6,
        "lean_reconstruction": 0.6,
    }


def _obligation(**metadata):
    return LegalIRProofObligation(
        obligation_id="obligation-proof03",
        statement="element_holds(notice)",
        kind="modal_well_formedness",
        legal_ir_view="TDFOL.prover",
        logic_family="temporal",
        sample_id="sample-proof03",
        formula_id="f1",
        metadata=metadata,
    )


def _route(obligation=None, **kwargs):
    payload = {
        "obligation": obligation if obligation is not None else _obligation(),
        "goal_statement": "element_holds(notice)",
        "required_trust": "kernel",
        "total_timeout_seconds": 2.0,
        "stage_timeout_seconds": _budgets(),
    }
    payload.update(kwargs)
    return route_bound_legal_ir_proof(**payload)


def test_policy_uses_real_router_and_explicit_deadlines():
    routed = _route()
    policy = ProofRoutingPolicy(
        required_trust="kernel",
        total_timeout_seconds=2.0,
        stage_timeout_seconds={
            "deterministic": 0.4,
            "native_logic": 0.4,
            "smt_atp": 0.6,
            "lean_reconstruction": 0.6,
        },
        enabled_routes=("deterministic_syntax", "deterministic_graph", "deterministic_contract"),
    )
    assert routed["router"].endswith("LegalIRProofRouter")
    assert routed["policy"]["total_timeout_seconds"] == policy.total_timeout_seconds
    assert routed["policy"]["stage_timeout_seconds"] == policy.to_dict()["stage_timeout_seconds"]
    assert routed["policy"]["required_trust"] == "kernel"
    assert routed["policy"]["enabled_routes"]
    assert routed["empty_enabled_routes_enables_all"] is True
    assert routed["installs_disabled"]["IPFS_DATASETS_PY_LAZY_INSTALL_PROVERS"] == "0"
    assert routed["installs_disabled"]["IPFS_DATASETS_PY_AUTO_INSTALL_PROVERS"] == "0"
    assert LegalIRProofRouter.__name__ == "LegalIRProofRouter"
    assert routed["attempts"]
    assert {item["status"] for item in routed["attempts"]}


def test_empty_enabled_routes_do_not_enable_install_prone_native_flogic():
    routed = _route(enabled_routes=())
    assert routed["rejected_empty_enabled_routes"] is True
    assert "native_flogic" not in routed["policy"]["enabled_routes"]
    flogic = next(item for item in routed["attempts"] if item["route"] == "native_flogic")
    assert flogic["status"] == "skipped"
    assert flogic["skip_reason"] == "route_disabled_by_policy"


def test_structural_deterministic_trust_is_not_substantive():
    sample = {
        "frame_logic": {
            "triples": [{"subject": "Employee", "predicate": "reported", "object": "Issue"}]
        }
    }
    obligation = LegalIRProofObligation(
        obligation_id="graph-1",
        statement="kg_edge_typed(subject:employee, predicate:reported, object:issue)",
        kind="knowledge_graph_edge_typing",
        legal_ir_view="knowledge_graph",
        logic_family="frame",
        metadata={"triple_index": 1},
    )
    routed = _route(
        obligation,
        sample_or_document=sample,
        goal_statement=obligation.statement,
        similarity_score=0.99,
        model_assertion="proved",
    )
    graph = next(item for item in routed["attempts"] if item["route"] == "deterministic_graph")
    assert graph["status"] == "proved"
    assert graph["trust_level"] == "deterministic"
    assert routed["outcome"] == "unknown"
    assert routed["substantive_trust_satisfied"] is False
    assert routed["structural_route_proved"] is True
    assert routed["similarity_score_ignored"] is True
    assert routed["model_assertion_ignored"] is True
    assert routed["entails_claim_element"] is False


def test_untrusted_metadata_cannot_mint_proof():
    calls = {"count": 0}

    def planted(_request):
        calls["count"] += 1
        return True

    routed = _route(
        _obligation(
            deterministic_syntax_valid=True,
            native_tdfol_result=True,
            native_tdfol_prover=planted,
        )
    )
    syntax = next(item for item in routed["attempts"] if item["route"] == "deterministic_syntax")
    assert "deterministic_syntax_valid" in routed["rejected_untrusted_metadata"]
    assert "native_tdfol_result" in routed["rejected_untrusted_metadata"]
    assert "native_tdfol_prover" in routed["rejected_untrusted_metadata"]
    assert calls["count"] == 0
    assert syntax["reason"] != "explicit_deterministic_syntax_check"
    assert routed["outcome"] != "proved"
    assert routed["substantive_trust_satisfied"] is False


def test_missing_facts_stay_unknown_not_false():
    routed = _route(
        premise_inventory={
            "missing_facts": [{"premise_id": "notice-date", "text": "", "revision": "missing"}],
            "assumptions": [{"premise_id": "a1", "label": "only-a-label", "text": "SECRET-ASSUMPTION"}],
        },
        local_backend="proved",
    )
    assert routed["outcome"] == "unknown"
    assert routed["reason"] == "missing_fact_open_world"
    assert routed["missing_facts"] == [
        {
            "premise_id": "notice-date",
            "value": None,
            "interpreted_as_false": False,
            "open_world": True,
        }
    ]
    assert routed["missing_facts_are_false"] is False
    assert "SECRET-ASSUMPTION" not in str(routed["attempts"])
    assert routed["assumption_ids"] == ["a1"]


def test_outcome_distinctions_for_negative_proof_consistency_and_failure():
    proved = _route(local_backend="proved")
    refuted = _route(local_backend="disproved")
    inconsistent = _route(local_backend="unsat_premises")
    sat = _route(local_backend="sat")
    reconstruction = _route(local_backend="reconstruction_failed")
    syntax = _route(
        LegalIRProofObligation(
            obligation_id="bad-syntax",
            statement="element_holds(notice",
            kind="modal_well_formedness",
            legal_ir_view="intake",
            logic_family="unspecified",
        ),
        goal_statement="element_holds(notice",
    )
    unavailable = _route(local_backend="unavailable")
    unsupported_timeout = _route(local_backend="timeout")

    assert proved["outcome"] == "proved"
    assert proved["native_trust"] == "kernel"
    assert proved["substantive_trust_satisfied"] is True
    assert proved["reason"] == "kernel_bound_to_goal"
    assert refuted["outcome"] == "refuted"
    assert refuted["theorem_failed_is_counterexample"] is True
    assert refuted["native_status"] == "theorem_failed"
    assert inconsistent["outcome"] == "inconsistent"
    assert inconsistent["unsat_proves_arbitrary_claim"] is False
    assert inconsistent["consistency_is_entailment"] is False
    assert inconsistent["outcome"] != "refuted"
    assert sat["outcome"] == "unknown"
    assert sat["consistency_is_entailment"] is False
    assert reconstruction["outcome"] == "unsupported"
    assert reconstruction["theorem_failed_is_counterexample"] is False
    assert reconstruction["reason"] == "theorem_failed_without_bound_negative_proof"
    assert syntax["outcome"] == "unsupported"
    assert syntax["outcome"] != "refuted"
    assert unavailable["outcome"] == "unavailable"
    assert unsupported_timeout["outcome"] == "timeout"
    assert routed_outcomes(proved, refuted, inconsistent, sat, reconstruction, syntax, unavailable, unsupported_timeout) >= {
        "proved",
        "refuted",
        "inconsistent",
        "unknown",
        "unsupported",
        "timeout",
        "unavailable",
    }


def routed_outcomes(*rows):
    return {row["outcome"] for row in rows}


def test_stale_versions_do_not_reuse_a_kernel_proof():
    routed = _route(
        local_backend="proved",
        execution_identity="identity-a",
        expected_execution_identity="identity-b",
        obligation_version="ob-1",
        premise_version="fact-1",
    )
    assert routed["outcome"] == "unknown"
    assert routed["reason"] == "stale_source_or_policy_version"
    assert routed["substantive_trust_satisfied"] is False
    assert routed["versions"]["policy_version"]
    assert routed["versions"]["obligation_version"] == "ob-1"


def test_managed_child_timeout_reaps_the_process_group(tmp_path: Path):
    started = time.monotonic()
    routed = _route(
        managed_command=["/usr/bin/python3.12", "-c", "import time; time.sleep(30)"],
        managed_state_directory=str(tmp_path / "timeout-state"),
        managed_wall_time_seconds=0.4,
        total_timeout_seconds=2.0,
    )
    elapsed = time.monotonic() - started
    assert routed["outcome"] == "timeout"
    assert routed["process"]["timed_out"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert elapsed < 3.0


def test_managed_child_cancel_reaps_descendants(tmp_path: Path):
    grandchild = tmp_path / "grandchild-pid"
    command = [
        "/usr/bin/python3.12",
        "-c",
        (
            "import os, signal, sys, time\n"
            "path = sys.argv[1]\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"
            "    time.sleep(30)\n"
            "    os._exit(0)\n"
            "def stop(signum, frame):\n"
            "    try:\n"
            "        os.kill(pid, signal.SIGKILL)\n"
            "    except OSError:\n"
            "        pass\n"
            "    try:\n"
            "        os.waitpid(pid, 0)\n"
            "    except OSError:\n"
            "        pass\n"
            "    os._exit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "open(path, 'w', encoding='utf-8').write(str(pid))\n"
            "while True:\n"
            "    time.sleep(0.05)\n"
        ),
        str(grandchild),
    ]
    cancel = threading.Event()

    def _cancel():
        time.sleep(0.2)
        cancel.set()

    threading.Thread(target=_cancel, daemon=True).start()
    started = time.monotonic()
    routed = _route(
        managed_command=command,
        managed_state_directory=str(tmp_path / "cancel-state"),
        managed_wall_time_seconds=5.0,
        total_timeout_seconds=5.0,
        cancellation_event=cancel,
    )
    elapsed = time.monotonic() - started
    assert routed["outcome"] == "cancelled"
    assert routed["process"]["cancelled"] is True
    assert routed["process"]["process_group_reaped"] is True
    assert elapsed < 3.0
    deadline = time.monotonic() + 1.5
    while not grandchild.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert grandchild.exists()
    child_pid = int(grandchild.read_text(encoding="utf-8"))
    remaining = deadline - time.monotonic()
    while remaining > 0:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
        remaining = deadline - time.monotonic()
    else:
        raise AssertionError(f"descendant {child_pid} is still running")
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_non_finite_deadline_is_rejected():
    with pytest.raises(ValueError):
        _route(total_timeout_seconds=float("inf"))
