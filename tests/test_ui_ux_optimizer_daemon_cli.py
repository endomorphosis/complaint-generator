from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.no_auto_network]


def _load_script_module():
    import complaint_generator.ui_optimizer_daemon as module

    return module


def test_build_parser_exposes_daemon_commands_and_flags():
    module = _load_script_module()
    parser = module.build_parser()
    help_text = parser.format_help()
    run_help = next(action for action in parser._actions if getattr(action, "dest", "") == "command").choices["run"].format_help()

    assert "start" in help_text
    assert "run" in help_text
    assert "status" in help_text
    assert "stop" in help_text
    assert "--iterations" in run_help
    assert "--use-llm-draft" in run_help
    assert "adversarial review artifacts" in run_help

    parsed = parser.parse_args(
        [
            "start",
            "--user-id",
            "sleep-user",
            "--goal",
            "repair broken buttons",
            "--goal",
            "improve the legal complaint output",
            "--use-llm-draft",
        ]
    )
    assert parsed.command == "start"
    assert parsed.goals == ["repair broken buttons", "improve the legal complaint output"]
    assert parsed.use_llm_draft is True


def test_run_daemon_refreshes_complaint_artifacts_and_writes_status(tmp_path, monkeypatch):
    module = _load_script_module()
    pid_file = tmp_path / "daemon.pid"
    status_file = tmp_path / "daemon-status.json"
    log_file = tmp_path / "daemon.log"

    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, root_dir):
            captured["root_dir"] = str(root_dir)

        def update_claim_type(self, user_id, claim_type):
            captured["claim_type"] = (user_id, claim_type)
            return {"claim_type": claim_type}

        def generate_complaint(self, user_id, **kwargs):
            captured["generate_complaint"] = {"user_id": user_id, **kwargs}
            return {
                "draft": {
                    "draft_strategy": "llm_router",
                    "draft_backend": {"provider": "codex_cli", "model": "gpt-5.3-codex"},
                }
            }

        def export_complaint_packet(self, user_id):
            captured["export_complaint_packet"] = user_id
            return {"packet": {}, "artifacts": {}}

        def export_complaint_markdown(self, user_id):
            captured["export_complaint_markdown"] = user_id
            return {"artifact": {"filename": "complaint.md", "size_bytes": 128}}

        def export_complaint_pdf(self, user_id):
            captured["export_complaint_pdf"] = user_id
            return {"artifact": {"filename": "complaint.pdf", "size_bytes": 256}}

        def analyze_complaint_output(self, user_id):
            captured["analyze_complaint_output"] = user_id
            return {
                "filing_shape_score": 88,
                "claim_type_alignment_score": 92,
                "release_gate": {"verdict": "warning"},
            }

        def review_generated_exports(self, user_id, **kwargs):
            captured["review_generated_exports"] = {"user_id": user_id, **kwargs}
            return {
                "artifact_count": 1,
                "aggregate": {
                    "average_filing_shape_score": 88,
                    "issue_findings": ["Venue allegations still look generic."],
                    "ui_suggestions": [{"title": "Strengthen venue guidance", "recommendation": "Warn before export when venue facts are missing."}],
                },
            }

        def _build_complaint_output_review_artifacts(self, user_id):
            return [
                {
                    "artifact_type": "complaint_export",
                    "name": "export-artifact",
                    "formal_section_gaps": ["jurisdiction and venue", "prayer for relief"],
                    "release_gate": {"verdict": "warning", "blocking_reason": "Formal sections remain incomplete."},
                    "claim_type_alignment": {"count_heading_matches_claim_type": False},
                    "ui_suggestions_excerpt": "Keep jurisdiction and venue guidance visible before export.",
                }
            ]

        def _build_cached_ui_readiness_artifacts(self, user_id):
            return [
                {
                    "artifact_type": "ui_readiness_review",
                    "name": "cached-ui",
                    "optimization_targets": [{"title": "Keep export controls visible", "reason": "The actor loses the next step after generation."}],
                    "screenshot_findings": [{"stage": "draft", "summary": "The export call-to-action falls below dense metadata."}],
                    "recommended_changes": ["Pin the export lane beside the complaint preview."],
                    "playwright_followups": ["Verify PDF export stays enabled after testimony edits."],
                }
            ]

        def _persist_ui_readiness(self, user_id, result):
            captured["persisted_ui_readiness"] = {"user_id": user_id, "workflow_type": result.get("workflow_type")}
            return {"status": "cached"}

        def get_client_release_gate(self, user_id):
            return {"verdict": "warning", "recommended_action": "Keep improving draft/export guidance."}

        def get_provider_diagnostics(self, user_id):
            return {
                "effective_provider_name": "codex_cli",
                "effective_model_name": "gpt-5.3-codex",
                "complaint_draft_default_order": ["codex_cli", "copilot_cli", "hf_inference_api"],
            }

    def fake_closed_loop(**kwargs):
        captured["closed_loop"] = kwargs
        return {
            "workflow_type": "ui_ux_closed_loop",
            "rounds_executed": 1,
            "stop_reason": "validation_review_stable",
            "cycles": [
                {
                    "round": 1,
                    "optimizer_result": {
                        "status": "applied",
                        "changed_files": ["templates/workspace.html", "playwright/tests/complaint-flow.spec.js"],
                        "metadata": {
                            "selected_patch_brief_titles": ["UX repair 1", "UX repair 2"],
                            "covered_patch_brief_titles": ["UX repair 1"],
                            "uncovered_selected_patch_brief_titles": ["UX repair 2"],
                            "selected_patch_brief_coverage_ratio": 0.5,
                        },
                    },
                }
            ],
        }

    monkeypatch.setattr(module, "ComplaintWorkspaceService", FakeService)
    monkeypatch.setattr(module, "optimize_ui", fake_closed_loop)
    monkeypatch.setattr(
        module,
        "run_end_to_end_complaint_browser_audit",
        lambda **kwargs: {"returncode": 0, "artifact_count": 5, "screenshot_dir": str(kwargs["screenshot_dir"])},
    )

    class _FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(module.threading, "Thread", _FakeThread)

    args = argparse.Namespace(
        command="run",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(tmp_path / "daemon"),
        pytest_target="playwright/tests/complaint-flow.spec.js",
        provider="codex_cli",
        model="gpt-5.3-codex",
        config_path="config.llm_router.json",
        backend_id=None,
        max_rounds=2,
        iterations=2,
        poll_seconds=0.0,
        retry_seconds=0.0,
        max_consecutive_errors=0,
        max_cycles=1,
        method="actor_critic",
        priority=90,
        notes="Keep improving the formal complaint output.",
        goals=["repair broken buttons", "tighten legal complaint posture"],
        use_llm_draft=True,
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )

    payload = module._run_daemon(args)

    assert payload["status"] == "success"
    assert payload["daemon_state"] == "completed"
    assert Path(payload["status_file"]).exists()
    status_payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert status_payload["status"] == "completed"
    assert status_payload["cycle_count"] == 1
    assert status_payload["last_result"]["summary"]["filing_shape_score"] == 88
    assert status_payload["recommendation_coverage"]["selected_patch_briefs_total"] == 2
    assert status_payload["recommendation_coverage"]["covered_patch_briefs_total"] == 1
    assert status_payload["recommendation_coverage"]["overall_selected_patch_brief_coverage_ratio"] == 0.5
    assert status_payload["last_result"]["recommendation_coverage"]["selected_patch_briefs_total"] == 2
    assert status_payload["last_result"]["recommendation_coverage"]["covered_patch_briefs_total"] == 1
    assert status_payload["last_result"]["recommendation_coverage"]["overall_selected_patch_brief_coverage_ratio"] == 0.5
    assert status_payload["last_result"]["goal_source"] == "adversarial_feedback"
    assert status_payload["last_result"]["summary"]["adversarial_goal_count"] >= 5
    assert captured["generate_complaint"]["use_llm"] is True
    assert captured["review_generated_exports"]["provider"] == "codex_cli"
    assert any("formal pleading sections" in item for item in captured["closed_loop"]["goals"])
    assert any("Fix the draft breakdown" in item for item in captured["closed_loop"]["goals"])
    assert any("Playwright obligation" in item for item in captured["closed_loop"]["goals"])
    assert not pid_file.exists()


def test_start_status_and_stop_daemon_commands(tmp_path, monkeypatch):
    module = _load_script_module()
    daemon_root = tmp_path / "daemon"
    pid_file = daemon_root / "ui_ux_optimizer_daemon.pid"
    status_file = daemon_root / "ui_ux_optimizer_daemon_status.json"
    log_file = daemon_root / "ui_ux_optimizer_daemon.log"
    daemon_root.mkdir(parents=True, exist_ok=True)

    class _FakePopen:
        def __init__(self, cmd, cwd, env, stdout, stderr, start_new_session):
            self.pid = 515151
            self.cmd = cmd
            self.cwd = cwd
            self.env = env
            self.stdout = stdout
            self.stderr = stderr
            self.start_new_session = start_new_session

    captured: dict[str, object] = {}

    def fake_popen(cmd, cwd, env, stdout, stderr, start_new_session):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        return _FakePopen(cmd, cwd, env, stdout, stderr, start_new_session)

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 515151)
    monkeypatch.setattr(module.os, "kill", lambda pid, sig: captured.setdefault("killed", (pid, sig)))

    args = argparse.Namespace(
        command="start",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(daemon_root),
        pytest_target="playwright/tests/complaint-flow.spec.js",
        provider="codex_cli",
        model="gpt-5.3-codex",
        config_path="config.llm_router.json",
        backend_id=None,
        max_rounds=3,
        iterations=2,
        poll_seconds=600.0,
        retry_seconds=90.0,
        max_consecutive_errors=2,
        max_cycles=0,
        method="actor_critic",
        priority=95,
        notes="Overnight optimizer pass",
        goals=["repair broken buttons"],
        use_llm_draft=True,
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )

    start_payload = module._start_daemon(args)
    assert start_payload["status"] == "started"
    assert "run" in captured["cmd"]
    assert "--use-llm-draft" in captured["cmd"]
    assert "--goal" in captured["cmd"]

    pid_file.write_text("515151\n", encoding="utf-8")
    status_file.write_text(
        json.dumps(
            {
                "status": "running",
                "cycle_count": 2,
                "last_result": {
                    "optimizer_result": {
                        "cycles": [
                            {
                                "optimizer_result": {
                                    "status": "applied",
                                    "changed_files": ["templates/workspace.html"],
                                    "metadata": {
                                        "selected_patch_brief_titles": ["UX repair 1", "UX repair 2", "UX repair 3"],
                                        "covered_patch_brief_titles": ["UX repair 1", "UX repair 2", "UX repair 3"],
                                        "uncovered_selected_patch_brief_titles": [],
                                        "selected_patch_brief_coverage_ratio": 1.0,
                                    },
                                }
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status_args = argparse.Namespace(
        command="status",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(daemon_root),
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )
    status_payload = module._status_payload(status_args)
    assert status_payload["running"] is True
    assert status_payload["status_payload"]["cycle_count"] == 2
    assert status_payload["recommendation_coverage"]["selected_patch_briefs_total"] == 3
    assert status_payload["recommendation_coverage"]["covered_patch_briefs_total"] == 3
    assert status_payload["recommendation_coverage"]["overall_selected_patch_brief_coverage_ratio"] == 1.0

    stop_args = argparse.Namespace(
        command="stop",
        user_id="sleep-user",
        workspace_root=str(tmp_path / "sessions"),
        artifact_root=str(daemon_root),
        pid_file=str(pid_file),
        status_file=str(status_file),
        log_file=str(log_file),
        json=True,
    )
    stop_payload = module._stop_daemon(stop_args)
    assert stop_payload["status"] == "stopping"
    assert captured["killed"][0] == 515151
