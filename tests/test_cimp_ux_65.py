"""New UX campaign ingestion and startup stay short of owned execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from integrations.ipfs_accelerate import improvement_plan as compiler
from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
SPEC = "docs/task_boards/complaint_gui_ux_overhaul_spec.json"
HISTORICAL = (
    "docs/task_boards/complaint_intake_task_board.md",
    "docs/task_boards/complaint_mediator_grounding_task_board.md",
    "docs/task_boards/complaint_gui_collaboration_task_board.md",
)
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(autouse=True)
def _ready_doctor_without_provider(monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(runner, "_branch", lambda path: "codex/gui-ux-overhaul-20261026")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *args: {"ready": True, "reason": "ready"})
    monkeypatch.setattr(runner, "_auth_material_present", lambda env: True)
    monkeypatch.setattr(runner.shutil, "which", lambda *args, **kwargs: "/usr/bin/false")


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    root = tmp_path_factory.mktemp("ux-campaign-repo")
    historical = {}
    for relative in HISTORICAL:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        historical[relative] = raw
    spec_path = root / SPEC
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_bytes((ROOT / SPEC).read_bytes())
    runner._native_modules(ROOT)
    generated = compiler.generate(spec_path, root)
    spec = compiler.load_spec(spec_path)
    binding = compiler.campaign_observation_binding(spec)
    state = tmp_path_factory.mktemp("ux-campaign-state")
    worktree = tmp_path_factory.mktemp("ux-campaign-worktree")
    os.chmod(worktree, 0o700)
    runner._validate_worktree_root(root, state, worktree, claim=True)
    budget = {"spent": 7, "holds": ["historical-intake"], "refunded": False}
    (state / "budget.json").write_text(json.dumps(budget), encoding="utf-8")
    (state / "receipts.jsonl").write_text('{"task_id":"CIMP-INTAKE-01","status":"completed"}\n', encoding="utf-8")
    (state / "accounting.json").write_text('{"paid_calls":4}\n', encoding="utf-8")
    return {
        "root": root, "spec_path": spec_path, "spec": spec, "generated": generated,
        "binding": binding, "state": state, "worktree": worktree, "historical": historical,
        "budget": (state / "budget.json").read_bytes(),
        "receipts": (state / "receipts.jsonl").read_bytes(),
        "accounting": (state / "accounting.json").read_bytes(),
        "board": Path(generated["board_path"]).read_bytes(),
    }


def _preserved(campaign) -> None:
    state = campaign["state"]
    assert (state / "budget.json").read_bytes() == campaign["budget"]
    assert (state / "receipts.jsonl").read_bytes() == campaign["receipts"]
    assert (state / "accounting.json").read_bytes() == campaign["accounting"]
    assert Path(campaign["generated"]["board_path"]).read_bytes() == campaign["board"]
    for relative, raw in campaign["historical"].items():
        assert (campaign["root"] / relative).read_bytes() == raw
        assert (ROOT / relative).read_bytes() == raw


def _observe(campaign, **kwargs):
    observed = runner.qualify_new_campaign_startup(
        campaign["root"], campaign["spec_path"], kwargs.get("state", campaign["state"]),
        worktree_root=kwargs.get("worktree", campaign["worktree"]))
    _preserved(campaign)
    return observed


def _phase(campaign, *, attempt=1, phase="validating", started=None, task_id="CIMP-UX-01", cid=None):
    tasks = runner._native_modules(ROOT)[1].parse_task_file(
        Path(campaign["generated"]["board_path"]), task_header_prefix=runner.TASK_PREFIX)
    identity = next(task for task in tasks if task.task_id == task_id)
    when = started if started is not None else datetime.now(timezone.utc)
    payload = {
        "implementation_in_progress": True,
        "active_task_id": task_id,
        "active_task_cid": identity.canonical_task_cid if cid is None else cid,
        "active_attempt": attempt,
        "active_phase": phase,
        "active_phase_started_at": when.isoformat(),
    }
    path = campaign["state"] / f"{runner.STATE_PREFIX}_task_state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return identity


class _Owned:
    def __init__(self, campaign):
        token = "synthetic-ux-owner"
        code = (
            "import subprocess,sys,time\n"
            "state=sys.argv[sys.argv.index('--state-dir')+1]\n"
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(180)',"
            "'implementation_daemon','--state-dir',state])\n"
            "time.sleep(180)\n"
        )
        argv = [sys.executable, "-c", code, "_run", "--owner-token", token,
                "--state-dir", str(campaign["state"]), "--worktree-root", str(campaign["worktree"])]
        self.proc = subprocess.Popen(argv, start_new_session=True)
        self.argv = argv
        self.token = token
        self.campaign = campaign
        deadline = time.time() + 5
        child = None
        while time.time() < deadline and child is None:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                identity = runner.process_identity(int(entry.name))
                if not identity or identity.get("ppid") != self.proc.pid:
                    continue
                if "implementation_daemon" in identity.get("argv", []):
                    child = identity
                    break
            time.sleep(0.05)
        if child is None:
            self.close()
            raise AssertionError("daemon_not_born")
        self.child = child
        launcher = runner.process_identity(self.proc.pid)
        binding = campaign["binding"]
        record = {
            "schema_version": "complaint-improvement-launcher@1",
            "identity": launcher, "argv": argv, "owner_token": token,
            "started_at": time.time(), "status": "starting",
            "repo_root": str(campaign["root"]), "spec_path": str(campaign["spec_path"]),
            "state_dir": str(campaign["state"]), "merge_target": "codex/gui-ux-overhaul-20261026",
            "board_path": campaign["generated"]["board_path"],
            "plan_id": binding["plan_id"], "source_generation": binding["source_generation"],
            "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False,
            "worktree_root": str(campaign["worktree"]),
            "worktree_root_binding": runner._validate_worktree_root(
                campaign["root"], campaign["state"], campaign["worktree"]),
        }
        runner._atomic_json(campaign["state"] / "launcher.json", record)
        runner._atomic_json(campaign["state"] / f"{runner.STATE_PREFIX}_supervisor_status.json", {
            "status": "running", "supervisor_pid": self.proc.pid, "daemon_pid": child["pid"],
            "daemon_pid_alive": True, "daemon_start_ticks": child["start_ticks"],
            "daemon_boot_id": child["boot_id"],
        })

    def close(self):
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, 15)
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, 9)
                self.proc.wait(timeout=2)


def test_publisher_bindings_are_independent_and_ingestion_does_not_execute(published):
    spec = published["spec"]
    manifest = json.loads((ROOT / "docs/ux/complaint_ux_overhaul/baseline/screenshot_manifest.json").read_text())
    assert spec["baseline_commit"] == manifest["application_base_commit"]
    assert published["generated"]["receipt"]["execution_started"] is False
    assert published["generated"]["receipt"]["tasks_completed_by_ingestion"] == 0
    observed = _observe(published)
    binding = published["binding"]
    assert observed["identities_independent"] is True
    assert observed["publisher_bound"] is True
    assert observed["publisher"]["plan_id"] == binding["plan_id"]
    assert observed["publisher"]["source_generation"] == binding["source_generation"]
    assert set(observed["task_cids"]) == {f"CIMP-UX-{number:02d}" for number in range(1, 69)}
    assert len(set(observed["task_cids"].values())) == 68
    sample = observed["task_bindings"]["CIMP-UX-65"]
    declared = next(task for task in spec["tasks"] if task["id"] == "CIMP-UX-65")
    assert sample["depends_on"] == declared["depends_on"]
    assert sample["validation"] == declared["validation_commands"]
    assert sample["status"] == "todo"
    assert observed["execution_admitted"] is False
    assert observed["ingestion_is_execution"] is False
    assert observed["tasks_completed_by_ingestion"] == 0
    assert observed["doctor_ready"] is True
    assert observed["doctor_ready_is_execution"] is False
    assert observed["launcher_birth"] is False and observed["daemon_birth"] is False
    assert observed["paid_calls"] == 0 and observed["completion_authority"] is False
    scopes = observed["identity_scopes"]
    assert len(set(scopes.values())) == 6
    assert Path(scopes["state"]) != Path(scopes["worktree"])
    assert not Path(scopes["state"]).is_relative_to(published["root"])
    assert binding["board_namespace"] == "complaint-gui-ux-overhaul"
    assert binding["distinct_from_historical_intake"] is True


def test_live_pid_and_completed_markdown_are_not_execution(published):
    board = Path(published["generated"]["board_path"])
    held = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        identity = runner.process_identity(held.pid)
        runner._atomic_json(published["state"] / "launcher.json", {
            "schema_version": "complaint-improvement-launcher@1",
            "identity": identity, "argv": identity["argv"], "owner_token": "not-a-campaign-owner",
            "repo_root": str(published["root"]), "spec_path": str(published["spec_path"]),
            "state_dir": str(published["state"]), "plan_id": published["binding"]["plan_id"],
            "source_generation": published["binding"]["source_generation"],
            "provider": "grok_cli", "model": "grok-4.7",
        })
        text = board.read_text(encoding="utf-8")
        board.write_text(text.replace("- Status: todo", "- Status: completed", 1), encoding="utf-8")
        published["board"] = board.read_bytes()
        observed = _observe(published)
        assert observed["pid_alive"] is True
        assert observed["pid_alive_is_execution"] is False
        assert observed["launcher_birth"] is False
        assert observed["markdown_completed_task_ids"]
        assert observed["markdown_status_grants_execution"] is False
        assert observed["tasks_completed_by_ingestion"] == 0
        assert observed["execution_admitted"] is False
        assert observed["doctor_ready_is_execution"] is False
    finally:
        held.kill()
        held.wait(timeout=2)
        restored = board.read_text(encoding="utf-8").replace("- Status: completed", "- Status: todo", 1)
        board.write_text(restored, encoding="utf-8")
        published["board"] = board.read_bytes()


def test_owned_births_without_bounded_work_do_not_execute(published):
    owned = _Owned(published)
    try:
        observed = _observe(published)
        assert observed["launcher_birth"] is True
        assert observed["daemon_birth"] is True
        assert observed["bounded_work"]["active"] is False
        assert observed["execution_admitted"] is False
        assert observed["doctor_ready"] is True
        assert observed["doctor_ready_is_execution"] is False
        assert observed["paid_calls"] == 0
    finally:
        owned.close()


def test_bounded_validation_is_admitted_without_changing_old_campaigns(published):
    _phase(published)
    owned = _Owned(published)
    try:
        observed = _observe(published)
        assert observed["execution_admitted"] is True
        assert observed["launcher_birth"] is True and observed["daemon_birth"] is True
        assert observed["bounded_work"]["phase"] == "validating"
        assert observed["bounded_work"]["attempt"] == 1
        assert observed["bounded_work"]["timeout_seconds"] == 900
        assert observed["bounded_work"]["validation_commands"]
        assert observed["source_generation_bound"] is True and observed["plan_bound"] is True
        assert observed["publisher_bound"] is True
        assert "CIMP-UX-65" not in observed["markdown_completed_task_ids"]
        assert observed["task_bindings"]["CIMP-UX-01"]["status"] == "todo"
        assert observed["completion_authority"] is False
        assert observed["historical_and_budget_unchanged"] is True
    finally:
        owned.close()


def test_expired_attempt_and_foreign_generation_are_refused(published):
    _phase(published, attempt=4, phase="implementing",
           started=datetime.now(timezone.utc) - timedelta(seconds=1000))
    owned = _Owned(published)
    try:
        refused = _observe(published)
        assert refused["launcher_birth"] is True and refused["daemon_birth"] is True
        assert refused["bounded_work"]["active"] is False
        assert refused["execution_admitted"] is False
        record = json.loads((published["state"] / "launcher.json").read_text(encoding="utf-8"))
        record["source_generation"] = "other-generation"
        runner._atomic_json(published["state"] / "launcher.json", record)
        _phase(published, attempt=1, phase="implementing")
        mismatched = _observe(published)
        assert mismatched["source_generation_bound"] is False
        assert mismatched["launcher_birth"] is False
        assert mismatched["execution_admitted"] is False
        assert mismatched["publisher"]["source_generation"] == published["binding"]["source_generation"]
    finally:
        owned.close()


def test_collapsed_scopes_and_unpublished_plan_are_not_a_new_campaign(published):
    inside = published["root"] / "nested-state"
    inside.mkdir()
    nested_worktree = published["root"] / "nested-worktree"
    nested_worktree.mkdir()
    os.chmod(nested_worktree, 0o700)
    collapsed = runner.qualify_new_campaign_startup(
        published["root"], published["spec_path"], inside, worktree_root=nested_worktree)
    assert collapsed["identities_independent"] is False
    assert collapsed["execution_admitted"] is False
    plan = published["root"] / published["binding"]["plan_relative"]
    original = plan.read_bytes()
    plan.write_text("{", encoding="utf-8")
    try:
        broken = _observe(published)
        assert broken["publisher_bound"] is False
        assert broken["execution_admitted"] is False
        assert broken["tasks_completed_by_ingestion"] == 0
    finally:
        plan.write_bytes(original)
    _preserved(published)
