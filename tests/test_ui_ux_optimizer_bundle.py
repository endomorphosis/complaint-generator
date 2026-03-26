from types import SimpleNamespace
from pathlib import Path

import pytest
import json
import subprocess

from adversarial_harness import Optimizer, UIUXOptimizationBundle


pytestmark = [pytest.mark.no_auto_network]


def test_build_ui_ux_optimization_bundle_wraps_iterative_review_workflow(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    def fake_iterative(**kwargs):
        assert str(kwargs["screenshot_dir"]) == str(screenshot_dir)
        assert str(kwargs["output_dir"]) == str(output_dir)
        return {
            "iterations": 2,
            "screenshot_dir": str(screenshot_dir),
            "output_dir": str(output_dir),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(output_dir / "iteration-01-review.md"),
                    "review_json_path": str(output_dir / "iteration-01-review.json"),
                },
                {
                    "iteration": 2,
                    "review_markdown_path": str(output_dir / "iteration-02-review.md"),
                    "review_json_path": str(output_dir / "iteration-02-review.json"),
                },
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_iterative)
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: {
            "review": "# Top Risks\n- Improve evidence affordances.",
            "issues": [
                {
                    "problem": "Release gate messaging contradicts export posture.",
                    "recommended_fix": "Add a canonical filing readiness banner.",
                    "severity": "high",
                    "surface": "/workspace",
                }
            ],
            "recommended_changes": [
                {
                    "title": "Canonical filing banner",
                    "implementation_notes": "Add a single filing readiness banner that owns the verdict and blockers.",
                    "shared_code_path": "templates/workspace.html",
                }
            ],
            "complaint_output_feedback": {
                "export_artifact_count": 2,
                "claim_types": ["retaliation"],
                "draft_strategies": ["llm_router"],
                "filing_shape_scores": [82],
                "ui_suggestions": ["Warn before export when support gaps remain."],
            },
        },
    )

    bundle = optimizer.build_ui_ux_optimization_bundle(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    assert isinstance(bundle, UIUXOptimizationBundle)
    payload = bundle.to_dict()
    assert payload["iterations"] == 2
    assert payload["review_runs"]
    assert payload["complaint_output_feedback"]["export_artifact_count"] == 2
    assert payload["complaint_output_feedback"]["release_gate"]["verdict"] == "pass"
    assert payload["patch_briefs"]
    assert payload["patch_briefs"][0]["title"]
    assert payload["task"]["target_files"]
    assert "templates/workspace.html" in payload["target_files"]
    assert payload["task"]["metadata"]["report_summary"]["prioritized_patch_briefs"]
    assert payload["task"]["metadata"]["report_summary"]["active_target_files"] == ["templates/workspace.html"]


def test_run_agentic_ui_ux_autopatch_executes_optimizer_against_ui_task(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    monkeypatch.setattr(
        optimizer,
        "build_ui_ux_optimization_bundle",
        lambda **kwargs: UIUXOptimizationBundle(
            timestamp="2026-03-23T00:00:00+00:00",
            screenshot_dir=str(screenshot_dir),
            output_dir=str(output_dir),
            iterations=1,
            pytest_target="playwright/tests/navigation.spec.js",
            target_files=["templates/workspace.html"],
            review_runs=[
                {
                    "iteration": 1,
                    "review_markdown_path": str(output_dir / "iteration-01-review.md"),
                    "review_json_path": str(output_dir / "iteration-01-review.json"),
                }
            ],
            latest_review_markdown_path=str(output_dir / "iteration-01-review.md"),
            latest_review_json_path=str(output_dir / "iteration-01-review.json"),
            complaint_output_feedback={
                "export_artifact_count": 1,
                "claim_types": ["retaliation"],
                "draft_strategies": ["template"],
                "filing_shape_scores": [61],
                "ui_suggestions": ["Keep export warnings visible."],
                "release_gate": {"verdict": "blocked"},
            },
            patch_briefs=[],
            task={},
        ),
    )
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: {"review": "# High-Impact UX Fixes\n- Keep the MCP SDK path shared."},
    )

    captured = {}

    class FakeUIOptimizer:
        def __init__(self, *, agent_id, llm_router):
            captured["agent_id"] = agent_id
            captured["llm_router"] = llm_router
            self._last_generation_diagnostics = [{"file": "templates/workspace.html", "status": "ok"}]

        def optimize(self, task):
            captured["task"] = task
            return SimpleNamespace(status="applied", metadata={"changed_files": ["templates/workspace.html"]})

    result = optimizer.run_agentic_ui_ux_autopatch(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        llm_router=object(),
        components=None,
        optimizer=FakeUIOptimizer(agent_id="ui-ux-agent", llm_router=object()),
    )

    assert result["bundle"]["target_files"] == ["templates/workspace.html"]
    assert result["bundle"]["complaint_output_feedback"]["export_artifact_count"] == 1
    assert result["bundle"]["complaint_output_feedback"]["release_gate"]["verdict"] == "blocked"
    assert result["task"]["target_files"] == ["templates/workspace.html"]
    assert captured["task"].metadata["workflow_type"] == "ui_ux_autopatch"
    assert captured["task"].metadata["complaint_output_release_gate"]["verdict"] == "blocked"
    assert captured["task"].metadata["actor_critic_review"]["critic_test_obligations"] == []


def test_run_agentic_ui_ux_feedback_loop_revalidates_and_stops_when_reviews_stabilize(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    call_counter = {"count": 0}
    review_by_path = {}

    def fake_workflow(**kwargs):
        call_counter["count"] += 1
        round_index = call_counter["count"]
        review_json_path = tmp_path / f"review-{round_index}.json"
        if round_index == 2:
            review_text = "# Top Risks\n- Calmer intake language still needed."
        elif round_index == 4:
            review_text = "# Top Risks\n- Calmer intake language still needed."
        else:
            review_text = f"# Top Risks\n- Review pass {round_index}."
        review_by_path[str(review_json_path)] = {
            "review": review_text,
            "recommended_changes": [
                {
                    "title": "Keep filing readiness visible",
                    "implementation_notes": "Make the release gate and next safest action impossible to miss in the draft rail.",
                    "shared_code_path": "templates/workspace.html",
                }
            ],
            "complaint_output_feedback": {
                "export_artifact_count": 1,
                "claim_types": ["housing_discrimination"],
                "draft_strategies": ["llm_router"],
                "filing_shape_scores": [84],
                "ui_suggestions": [f"Suggestion from pass {round_index}"],
            },
        }
        return {
            "iterations": 1,
            "screenshot_dir": str(kwargs["screenshot_dir"]),
            "output_dir": str(kwargs["output_dir"]),
            "latest_review": review_text,
            "latest_review_json_path": str(review_json_path),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(tmp_path / f"review-{round_index}.md"),
                    "review_json_path": str(review_json_path),
                }
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_workflow)
    monkeypatch.setattr(
        optimizer,
        "_read_ui_ux_review_json",
        lambda path: review_by_path.get(str(path), {}),
    )

    class FakeLoopOptimizer:
        def __init__(self, *, agent_id, llm_router):
            self._last_generation_diagnostics = [{"status": "ok"}]

        def optimize(self, task):
            return SimpleNamespace(
                success=True,
                status="applied",
                patch_path=str(tmp_path / "round.patch"),
                metadata={"changed_files": [str(task.target_files[0])]},
            )

    result = optimizer.run_agentic_ui_ux_feedback_loop(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        max_rounds=3,
        review_iterations=1,
        llm_router=object(),
        optimizer=FakeLoopOptimizer(agent_id="ui-loop", llm_router=object()),
        components=None,
    )

    assert result["workflow_type"] == "ui_ux_closed_loop"
    assert result["rounds_executed"] == 2
    assert result["stop_reason"] == "validation_review_stable"
    assert result["complaint_output_release_gate"]["verdict"] == "pass"
    assert result["cycles"][0]["optimizer_result"]["changed_files"]
    assert result["cycles"][0]["complaint_output_pre_review"]["export_artifact_count"] == 1
    assert result["cycles"][0]["complaint_output_pre_review"]["release_gate"]["verdict"] == "pass"
    patch_briefs_path = result["cycles"][0]["patch_briefs_path"]
    round_summary_path = result["cycles"][0]["round_summary_path"]
    patch_briefs_payload = json.loads((tmp_path / "reviews" / "round-01" / "patch-briefs.json").read_text())
    round_summary_payload = json.loads((tmp_path / "reviews" / "round-01" / "round-summary.json").read_text())
    assert patch_briefs_path.endswith("patch-briefs.json")
    assert round_summary_path.endswith("round-summary.json")
    assert "patch_briefs" in patch_briefs_payload
    assert patch_briefs_payload["selected_patch_brief"]["title"]
    assert patch_briefs_payload["selected_target_files"] == ["templates/workspace.html"]
    assert round_summary_payload["patch_briefs_path"] == patch_briefs_path
    assert round_summary_payload["selected_patch_brief"]["title"]
    assert round_summary_payload["selected_target_files"] == ["templates/workspace.html"]
    assert result["cycles"][0]["selected_patch_brief"]["title"]
    assert result["cycles"][0]["selected_target_files"] == ["templates/workspace.html"]
    assert result["complaint_output_feedback"]["export_artifact_count"] == 1
    assert result["complaint_output_release_gate"]["verdict"] == "pass"
    assert "actor_critic_summary" in result


def test_fallback_local_optimizer_can_apply_bounded_codex_edits(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    optimizer = Optimizer()
    components = optimizer._fallback_agentic_optimizer_components()
    fallback_cls = components["optimizer_classes"]["actor_critic"]
    output_dir = tmp_path / "reviews"
    output_dir.mkdir()
    target_file = tmp_path / "templates" / "workspace.html"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("<button>Start</button>\n", encoding="utf-8")

    monkeypatch.setattr("adversarial_harness.optimizer.shutil.which", lambda name: "/usr/bin/codex")

    def fake_run(command, cwd, capture_output, text, timeout, check):
        assert "codex" in command[0]
        assert str(target_file.relative_to(tmp_path)) in " ".join(command)
        target_file.write_text("<button>Start intake</button>\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="patched", stderr="")

    monkeypatch.setattr("adversarial_harness.optimizer.subprocess.run", fake_run)

    task = SimpleNamespace(
        task_id="ui-task",
        target_files=[Path("templates/workspace.html")],
        constraints={"output_dir": str(output_dir)},
        metadata={
            "actor_critic_review": {
                "top_risks": ["Clarify the intake CTA so first-time users know what the button does."],
            },
            "report_summary": {
                "prioritized_patch_briefs": [
                    {
                        "title": "Clarify CTA",
                        "surface": "intake",
                        "problem": "The start button is vague.",
                        "recommended_action": "Rename it to Start intake.",
                    }
                ]
            },
        },
    )

    result = fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    assert result.status == "applied"
    assert result.metadata["optimizer_backend"] == "codex_cli_fallback_optimizer"
    assert result.metadata["changed_files"] == ["templates/workspace.html"]
    assert Path(result.patch_path).is_file()
    assert "Start intake" in target_file.read_text(encoding="utf-8")


def test_fallback_local_optimizer_plan_only_does_not_claim_changed_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    optimizer = Optimizer()
    components = optimizer._fallback_agentic_optimizer_components()
    fallback_cls = components["optimizer_classes"]["actor_critic"]
    output_dir = tmp_path / "reviews"
    output_dir.mkdir()
    target_file = tmp_path / "templates" / "workspace.html"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("<button>Start</button>\n", encoding="utf-8")

    monkeypatch.setattr("adversarial_harness.optimizer.shutil.which", lambda name: None)

    task = SimpleNamespace(
        task_id="ui-task",
        target_files=[Path("templates/workspace.html")],
        constraints={"output_dir": str(output_dir)},
        metadata={},
    )

    result = fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    assert result.status == "fallback_recommendations_generated"
    assert result.metadata["changed_files"] == []
    assert result.metadata["target_files"] == ["templates/workspace.html"]
    assert Path(result.patch_path).is_file()


def test_fallback_local_optimizer_rolls_back_suspicious_empty_file_outputs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    optimizer = Optimizer()
    components = optimizer._fallback_agentic_optimizer_components()
    fallback_cls = components["optimizer_classes"]["actor_critic"]
    output_dir = tmp_path / "reviews"
    output_dir.mkdir()
    target_file = tmp_path / "templates" / "workspace.html"
    target_file.parent.mkdir(parents=True)
    original_text = "<main>" + ("x" * 2000) + "</main>\n"
    target_file.write_text(original_text, encoding="utf-8")

    monkeypatch.setattr("adversarial_harness.optimizer.shutil.which", lambda name: "/usr/bin/codex")

    def fake_run(command, cwd, capture_output, text, timeout, check):
        target_file.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="patched", stderr="")

    monkeypatch.setattr("adversarial_harness.optimizer.subprocess.run", fake_run)

    task = SimpleNamespace(
        task_id="ui-task",
        target_files=[Path("templates/workspace.html")],
        constraints={"output_dir": str(output_dir)},
        metadata={
            "actor_critic_review": {"top_risks": ["Keep the draft rail visible."]},
            "report_summary": {
                "prioritized_patch_briefs": [
                    {
                        "title": "Keep draft rail visible",
                        "surface": "draft",
                        "problem": "The primary action disappears.",
                        "recommended_action": "Keep the draft rail visible.",
                    }
                ]
            },
        },
    )

    worker = fallback_cls(agent_id="fallback-ui", llm_router=None)
    result = worker.optimize(task)

    assert result.status == "fallback_recommendations_generated"
    assert result.metadata["changed_files"] == []
    assert target_file.read_text(encoding="utf-8") == original_text
    assert any(
        item.get("status") == "rolled_back_suspicious_output"
        for item in list(getattr(worker, "_last_generation_diagnostics", []) or [])
        if isinstance(item, dict)
    )
