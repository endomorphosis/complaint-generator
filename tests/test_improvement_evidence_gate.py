"""Current-source behavioral evidence is the only task-completion authority.

Unit fakes, optional provider smoke, empty collection, skips, stale hashes,
missing outputs, failed assertions and subprocess timeouts stay repairable
rejections. Dependent readiness is recomputed from the stored receipts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate.improvement_plan import (
    SEALED_ENVIRONMENT_POLICY,
    assess_behavioral_evidence,
    bind_sources,
    canonical_model_policy,
)
from integrations.ipfs_accelerate.improvement_runner import (
    gate_task_completion,
    recompute_dependent_readiness,
)


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

COMMAND = "python -m pytest -q --run-llm --run-network --run-heavy tests/test_improvement_evidence_gate.py"
NODE_A = "tests/test_improvement_evidence_gate.py::test_local_node_evidence_completes_and_readies_dependent"
NODE_B = "tests/test_improvement_evidence_gate.py::test_recompute_invalidates_dependents"


def _task(task_id: str = "CIMP-OPS-04", *, depends=None, command: str = COMMAND) -> dict:
    return {
        "id": task_id,
        "targets": [f"out/{task_id}.py"],
        "validation_commands": [command],
        "depends_on": list(depends or []),
    }


def _environment() -> dict:
    return {**SEALED_ENVIRONMENT_POLICY, "HOME": "/tmp/ipfs-accelerate-validation-home-evidence"}


def _write_output(root: Path, task_id: str, body: str = "def ready():\n    return True\n") -> str:
    path = root / "out" / f"{task_id}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    artifact = root / "artifacts" / f"{task_id}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"task_id": task_id, "body": body}), encoding="utf-8")
    return str(path.relative_to(root))


def _observation(root: Path, task_id: str = "CIMP-OPS-04", **overrides) -> dict:
    binding = bind_sources(root, [f"out/{task_id}.py"])
    artifact = root / "artifacts" / f"{task_id}.json"
    value = {
        "lane": "local_node_integration",
        "command": COMMAND,
        "exit_status": 0,
        "timed_out": False,
        "collected_count": 2,
        "cases": [
            {"nodeid": NODE_A, "outcome": "passed"},
            {"nodeid": NODE_B, "outcome": "passed"},
        ],
        "required_nodeids": [NODE_A, NODE_B],
        "environment": _environment(),
        "source_binding": binding,
        "artifacts": [{"relative_path": artifact.relative_to(root).as_posix()}],
    }
    value.update(overrides)
    return value


def _spec(*tasks: dict) -> dict:
    return {"tasks": list(tasks)}


def _gate(tmp_path: Path, task: dict, observation: dict, **kwargs) -> dict:
    return gate_task_completion(
        tmp_path, tmp_path / "state", task, observation,
        facts=kwargs.pop("facts", {"narrative": "synthetic"}),
        model_policy=kwargs.pop("model_policy", canonical_model_policy()),
        legal_data_version=kwargs.pop("legal_data_version", "legal-2026-10-21"),
        spec=kwargs.pop("spec", None), **kwargs,
    )


def test_local_node_evidence_completes_and_readies_dependent(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-01")
    _write_output(tmp_path, "CIMP-OPS-04")
    upstream = _task("CIMP-OPS-01")
    downstream = _task("CIMP-OPS-04", depends=["CIMP-OPS-01"])
    spec = _spec(upstream, downstream)
    first = _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01"), spec=spec)
    assert first["completion"] is True
    assert first["reason"] == "current_source_behavioral_evidence"
    assert first["repairable"] is False
    assert first["readiness"]["tasks"]["CIMP-OPS-01"]["complete"] is True
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["ready"] is True
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["complete"] is False
    assert first["readiness"]["tasks"]["CIMP-OPS-04"]["reason"] == "missing_behavioral_evidence"
    second = _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), spec=spec)
    assert second["completion"] is True
    assert second["exit_status"] == 0
    assert second["command"] == COMMAND
    assert second["environment_policy"]["required"]["PATH"] == SEALED_ENVIRONMENT_POLICY["PATH"]
    assert second["environment_policy"]["required"]["python"] == "/usr/bin/python3.12"
    assert second["source_binding"]["digest"]
    assert second["required_cases"][0]["nodeid"] == NODE_A
    assert second["artifacts"][0]["present"] is True
    assert second["artifacts"][0]["sha256"]
    assert second["native_validation"]["verdict_kind"] == "test"
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    lane = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/local_node_integration.json").read_text(encoding="utf-8"))
    assert stored == lane
    assert stored["facts_digest"] and stored["legal_data_version"] == "legal-2026-10-21"
    assert second["readiness"]["tasks"]["CIMP-OPS-04"]["ready"] is True
    assert second["readiness"]["tasks"]["CIMP-OPS-04"]["complete"] is True


@pytest.mark.parametrize("overrides,reason", [
    ({"collected_count": 0, "cases": [], "required_nodeids": []}, "zero_test_collection"),
    ({"cases": [
        {"nodeid": NODE_A, "outcome": "skipped"},
        {"nodeid": NODE_B, "outcome": "passed"},
    ]}, "skipped_required_case"),
    ({"cases": [
        {"nodeid": NODE_A, "outcome": "failed"},
        {"nodeid": NODE_B, "outcome": "passed"},
    ], "exit_status": 1}, "failed_assertion"),
    ({"timed_out": True, "exit_status": None}, "subprocess_timeout"),
    ({"source_binding": {"files": {"out/CIMP-OPS-04.py": {"sha256": "0" * 64}}}}, "stale_source_hash"),
    ({"artifacts": [{"relative_path": "artifacts/missing.json"}]}, "missing_output"),
])
def test_defective_local_evidence_cannot_complete(tmp_path: Path, overrides: dict, reason: str) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    receipt = _gate(tmp_path, _task(), _observation(tmp_path, **overrides))
    assert receipt["completion"] is False
    assert receipt["admitted"] is False
    assert receipt["repairable"] is True
    assert receipt["reason"] == reason
    assert "command" in receipt and "exit_status" in receipt
    assert receipt["required_cases"] is not None
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    assert stored["reason"] == reason and stored["completion"] is False


def test_missing_declared_output_rejects_before_completion(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "CIMP-OPS-04.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    observation = _observation(tmp_path)
    observation["source_binding"] = None
    receipt = _gate(tmp_path, _task(), observation)
    assert receipt["reason"] == "missing_output"
    assert receipt["completion"] is False
    assert receipt["repairable"] is True


def test_unit_fake_and_provider_smoke_are_distinct_and_cannot_complete(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    task = _task()
    fake = _gate(tmp_path, task, _observation(tmp_path, lane="unit_fake", environment={"PATH": "/tmp/fake"}))
    smoke = _gate(tmp_path, task, _observation(tmp_path, lane="optional_real_provider_smoke"))
    assert fake["reason"] == "unit_fake_is_not_current_source_completion"
    assert smoke["reason"] == "optional_real_provider_smoke_is_not_completion"
    assert fake["completion"] is smoke["completion"] is False
    assert fake["repairable"] is smoke["repairable"] is True
    assert (tmp_path / "state/evidence/CIMP-OPS-04/unit_fake.json").is_file()
    assert (tmp_path / "state/evidence/CIMP-OPS-04/optional_real_provider_smoke.json").is_file()
    assert not (tmp_path / "state/evidence/CIMP-OPS-04/completion.json").exists()


def test_failed_smoke_does_not_erase_admitted_local_evidence(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    task = _task()
    admitted = _gate(tmp_path, task, _observation(tmp_path))
    failed = _observation(tmp_path, lane="optional_real_provider_smoke", exit_status=1,
                          cases=[{"nodeid": NODE_A, "outcome": "failed"}, {"nodeid": NODE_B, "outcome": "passed"}])
    smoke = _gate(tmp_path, task, failed)
    stored = json.loads((tmp_path / "state/evidence/CIMP-OPS-04/completion.json").read_text(encoding="utf-8"))
    assert admitted["completion"] is True
    assert smoke["reason"] == "failed_assertion"
    assert smoke["lane"] == "optional_real_provider_smoke"
    assert stored["completion"] is True
    assert stored["lane"] == "local_node_integration"


def test_recompute_invalidates_dependents(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-01", "def upstream():\n    return 1\n")
    _write_output(tmp_path, "CIMP-OPS-04")
    upstream = _task("CIMP-OPS-01")
    downstream = _task("CIMP-OPS-04", depends=["CIMP-OPS-01"])
    spec = _spec(upstream, downstream)
    facts = {"narrative": "synthetic"}
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01"), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    _write_output(tmp_path, "CIMP-OPS-01", "def upstream():\n    return 2\n")
    stale = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-10-21",
    )
    assert stale["tasks"]["CIMP-OPS-01"]["complete"] is False
    assert stale["tasks"]["CIMP-OPS-01"]["reason"] == "stale_source_hash"
    assert stale["tasks"]["CIMP-OPS-01"]["repairable"] is True
    assert stale["tasks"]["CIMP-OPS-04"]["complete"] is False
    assert stale["tasks"]["CIMP-OPS-04"]["ready"] is False
    assert stale["tasks"]["CIMP-OPS-04"]["reason"] == "upstream_evidence_not_current"
    restored = bind_sources(tmp_path, ["out/CIMP-OPS-01.py"])
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    changed_policy = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy={**canonical_model_policy(), "allow_fallback": True},
        legal_data_version="legal-2026-10-21",
    )
    assert changed_policy["tasks"]["CIMP-OPS-01"]["reason"] == "model_policy_changed"
    assert changed_policy["tasks"]["CIMP-OPS-04"]["ready"] is False
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    changed_legal = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts=facts,
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-11-01",
    )
    assert changed_legal["tasks"]["CIMP-OPS-01"]["reason"] == "legal_data_version_changed"
    assert changed_legal["tasks"]["CIMP-OPS-04"]["blocked_by"] == ["CIMP-OPS-01"]
    _gate(tmp_path, upstream, _observation(tmp_path, "CIMP-OPS-01", source_binding=restored), facts=facts, spec=spec)
    _gate(tmp_path, downstream, _observation(tmp_path, "CIMP-OPS-04"), facts=facts, spec=spec)
    corrected = recompute_dependent_readiness(
        tmp_path, tmp_path / "state", spec, facts={"narrative": "corrected"},
        model_policy=canonical_model_policy(), legal_data_version="legal-2026-10-21",
    )
    assert corrected["tasks"]["CIMP-OPS-01"]["reason"] == "corrected_facts"
    assert corrected["tasks"]["CIMP-OPS-04"]["repairable"] is True
    persisted = json.loads((tmp_path / "state/evidence/CIMP-OPS-01/completion.json").read_text(encoding="utf-8"))
    assert persisted["reason"] == "corrected_facts" and persisted["completion"] is False


def test_assess_rejects_non_test_command_and_wrong_model_policy(tmp_path: Path) -> None:
    _write_output(tmp_path, "CIMP-OPS-04")
    binding = bind_sources(tmp_path, ["out/CIMP-OPS-04.py"])
    command = "python -m py_compile out/CIMP-OPS-04.py"
    task = _task(command=command)
    observation = _observation(tmp_path, command=command)
    receipt = assess_behavioral_evidence(task, observation, source_binding=binding)
    assert receipt["reason"] == "command_not_behavioral_test"
    assert receipt["completion"] is False
    rejected = assess_behavioral_evidence(
        _task(), _observation(tmp_path), source_binding=binding,
        model_policy={**canonical_model_policy(), "model": "other"},
    )
    assert rejected["reason"] == "model_policy_rejected"
    assert rejected["repairable"] is True
