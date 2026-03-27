from types import SimpleNamespace
from pathlib import Path

import pytest
import json
import subprocess

from adversarial_harness import Optimizer, UIOptimizationBundle, UIUXOptimizationBundle


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
    assert payload["task"]["metadata"]["report_summary"]["selected_patch_briefs"]
    assert payload["task"]["metadata"]["report_summary"]["recommendation_coverage"]["total_patch_briefs"] >= 1
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
    assert patch_briefs_payload["selected_patch_briefs"]
    assert patch_briefs_payload["selected_patch_brief"]["title"]
    assert patch_briefs_payload["recommendation_coverage"]["selected_patch_briefs_count"] >= 1
    assert patch_briefs_payload["selected_target_files"] == ["templates/workspace.html"]
    assert round_summary_payload["patch_briefs_path"] == patch_briefs_path
    assert round_summary_payload["selected_patch_briefs"]
    assert round_summary_payload["selected_patch_brief"]["title"]
    assert round_summary_payload["recommendation_coverage"]["selected_patch_briefs_count"] >= 1
    assert round_summary_payload["selected_target_files"] == ["templates/workspace.html"]
    assert result["cycles"][0]["selected_patch_briefs"]
    assert result["cycles"][0]["selected_patch_brief"]["title"]
    assert result["cycles"][0]["recommendation_coverage"]["selected_patch_briefs_count"] >= 1
    assert result["cycles"][0]["selected_target_files"] == ["templates/workspace.html"]
    assert result["complaint_output_feedback"]["export_artifact_count"] == 1
    assert result["complaint_output_release_gate"]["verdict"] == "pass"
    assert "actor_critic_summary" in result


def test_run_agentic_ui_ux_feedback_loop_carries_uncovered_patch_briefs_forward(monkeypatch, tmp_path):
    optimizer = Optimizer()
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    review_by_path = {}
    call_counter = {"count": 0}

    def fake_workflow(**kwargs):
        call_counter["count"] += 1
        review_json_path = tmp_path / f"carry-forward-review-{call_counter['count']}.json"
        review_by_path[str(review_json_path)] = {
            "review": f"# Top Risks\n- Review pass {call_counter['count']}.",
            "recommended_changes": [
                {
                    "title": "Keep filing readiness visible",
                    "implementation_notes": "Keep the release gate summary visible before export.",
                    "shared_code_path": "templates/workspace.html",
                }
            ],
            "complaint_output_feedback": {
                "export_artifact_count": 1,
                "claim_types": ["retaliation"],
                "draft_strategies": ["llm_router"],
                "filing_shape_scores": [83],
            },
        }
        return {
            "iterations": 1,
            "screenshot_dir": str(kwargs["screenshot_dir"]),
            "output_dir": str(kwargs["output_dir"]),
            "latest_review": f"# Top Risks\n- Review pass {call_counter['count']}.",
            "latest_review_json_path": str(review_json_path),
            "runs": [
                {
                    "iteration": 1,
                    "review_markdown_path": str(tmp_path / f"carry-forward-review-{call_counter['count']}.md"),
                    "review_json_path": str(review_json_path),
                }
            ],
        }

    monkeypatch.setattr("complaint_generator.ui_ux_workflow.run_iterative_ui_ux_workflow", fake_workflow)
    monkeypatch.setattr(optimizer, "_read_ui_ux_review_json", lambda path: review_by_path.get(str(path), {}))

    captured_task_metadata = []

    class FakeLoopOptimizer:
        def __init__(self, *, agent_id, llm_router):
            self._last_generation_diagnostics = [{"status": "ok"}]

        def optimize(self, task):
            captured_task_metadata.append(dict(task.metadata or {}))
            carry_forward = list((task.metadata or {}).get("carry_forward_patch_briefs") or [])
            if not carry_forward:
                return SimpleNamespace(
                    success=True,
                    status="fallback_recommendations_generated",
                    patch_path=str(tmp_path / "plan.patch"),
                    metadata={
                        "changed_files": [],
                        "covered_patch_brief_titles": [],
                        "uncovered_selected_patch_brief_titles": ["Keep filing readiness visible"],
                        "selected_patch_brief_coverage_ratio": 0.0,
                    },
                )
            return SimpleNamespace(
                success=True,
                status="applied",
                patch_path=str(tmp_path / "round.patch"),
                metadata={
                    "changed_files": ["templates/workspace.html"],
                    "covered_patch_brief_titles": ["Keep filing readiness visible"],
                    "uncovered_selected_patch_brief_titles": [],
                    "selected_patch_brief_coverage_ratio": 1.0,
                },
            )

    result = optimizer.run_agentic_ui_ux_feedback_loop(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target="playwright/tests/navigation.spec.js",
        max_rounds=1,
        review_iterations=1,
        llm_router=object(),
        optimizer=FakeLoopOptimizer(agent_id="ui-loop", llm_router=object()),
        components=None,
        goals=["Original goal"],
        notes="Base notes",
    )

    assert result["rounds_executed"] == 2
    assert result["planned_rounds"] == 2
    assert result["cycles"][0]["optimizer_result"]["metadata"]["selected_patch_brief_coverage_ratio"] == 0.0
    assert result["cycles"][1]["optimizer_result"]["metadata"]["selected_patch_brief_coverage_ratio"] == 1.0
    assert captured_task_metadata[1]["carry_forward_patch_briefs"][0]["title"] == "Keep filing readiness visible"
    coverage_gap_payload = json.loads((output_dir / "round-01" / "coverage-gap.json").read_text())
    assert coverage_gap_payload["requires_follow_up"] is True
    assert coverage_gap_payload["uncovered_selected_patch_brief_titles"] == ["Keep filing readiness visible"]


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
                        "target_files": ["templates/workspace.html"],
                    }
                ]
            },
        },
    )

    result = fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    assert result.status == "applied"
    assert result.metadata["optimizer_backend"] == "codex_cli_fallback_optimizer"
    assert result.metadata["changed_files"] == ["templates/workspace.html"]
    assert result.metadata["covered_patch_brief_titles"] == ["Clarify CTA"]
    assert result.metadata["uncovered_selected_patch_brief_titles"] == []
    assert result.metadata["selected_patch_brief_coverage_ratio"] == 1.0
    assert Path(result.patch_path).is_file()
    assert "Start intake" in target_file.read_text(encoding="utf-8")


def test_fallback_local_optimizer_codex_prompt_carries_selected_patch_brief_batch(monkeypatch, tmp_path):
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
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout, check):
        captured["command"] = list(command)
        captured["prompt"] = command[-1]
        return subprocess.CompletedProcess(command, 0, stdout="no-op", stderr="")

    monkeypatch.setattr("adversarial_harness.optimizer.subprocess.run", fake_run)

    task = SimpleNamespace(
        task_id="ui-task",
        target_files=[Path("templates/workspace.html")],
        constraints={"output_dir": str(output_dir)},
        metadata={
            "actor_critic_review": {"top_risks": ["Clarify the release-gate CTA."]},
            "report_summary": {
                "selected_patch_briefs": [
                    {
                        "title": "Clarify review CTA",
                        "surface": "draft",
                        "problem": "The release gate CTA is vague.",
                        "recommended_action": "Rename the primary action to Review Before Export.",
                        "validation_checks": ["Playwright sees the new CTA label."],
                    },
                    {
                        "title": "Keep support warning visible",
                        "surface": "draft",
                        "problem": "The support warning scrolls out of view.",
                        "recommended_action": "Pin the export warning beside the draft summary.",
                        "validation_checks": ["Warning stays visible before download."],
                    },
                ],
                "recommendation_coverage": {
                    "total_patch_briefs": 5,
                    "selected_patch_briefs_count": 2,
                    "uncovered_patch_briefs_count": 3,
                },
            },
        },
    )

    fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    assert "--ephemeral" in captured["command"]
    assert "Selected patch briefs:" in captured["prompt"]
    assert "Clarify review CTA" in captured["prompt"]
    assert "Keep support warning visible" in captured["prompt"]
    assert "Briefs selected for this pass: 2" in captured["prompt"]
    assert "Cover as many selected patch briefs as safely possible in this pass" in captured["prompt"]


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
        metadata={
            "report_summary": {
                "selected_patch_briefs": [
                    {
                        "title": "Clarify CTA",
                        "target_files": ["templates/workspace.html"],
                    },
                    {
                        "title": "Keep export warning visible",
                        "target_files": ["templates/workspace.html"],
                    },
                ]
            },
        },
    )

    result = fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    assert result.status == "fallback_recommendations_generated"
    assert result.metadata["changed_files"] == []
    assert result.metadata["target_files"] == ["templates/workspace.html"]
    assert result.metadata["covered_patch_brief_titles"] == []
    assert result.metadata["uncovered_selected_patch_brief_titles"] == [
        "Clarify CTA",
        "Keep export warning visible",
    ]
    assert result.metadata["selected_patch_brief_coverage_ratio"] == 0.0
    assert Path(result.patch_path).is_file()


def test_fallback_local_optimizer_applies_deterministic_workspace_release_gate_patch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    optimizer = Optimizer()
    components = optimizer._fallback_agentic_optimizer_components()
    fallback_cls = components["optimizer_classes"]["actor_critic"]
    output_dir = tmp_path / "reviews"
    output_dir.mkdir()
    target_file = tmp_path / "templates" / "workspace.html"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        """
<div class="tool-card canonical-release-gate" id="draft-canonical-release-gate">
    <h3>Canonical filing verdict</h3>
    <p class="muted">Pinned filing verdict for Review and Draft. One reason source drives both tabs.</p>
</div>
<div class="tool-card canonical-release-gate" id="unsupported-thin-blocker-panel">
    <p class="muted" id="unsupported-thin-blocker-summary">Generate, export, and download stay blocked until the confidence gate is grounded.</p>
    <div class="chip-row" id="unsupported-thin-blocker-chips">
        <span class="chip">grounded: 0</span>
        <span class="chip">thin: 0</span>
        <span class="chip">unsupported: 0</span>
    </div>
    <div class="list" id="unsupported-thin-blocker-reasons"></div>
</div>
<div class="chip-row" id="draft-release-gate-chip-row">
    <span class="chip warn" id="draft-release-gate-chip">verdict: BLOCKED</span>
</div>
<div class="status draft-preview-shell"><pre id="draft-release-gate-summary">Verdict: BLOCKED
Blocker reasons: waiting for readiness signals.</pre></div>
<button id="draft-review-before-export-button" type="button">Review</button>
<button id="draft-evidence-before-export-button" type="button">Evidence</button>
<script>
        document.getElementById('draft-review-before-export-button').addEventListener('click', () => jumpToStage('review', '#support-grid', 'Opened Review so support and release-gate blockers can be checked before export.'));
        document.getElementById('draft-evidence-before-export-button').addEventListener('click', () => jumpToStage('evidence', '#evidence-title', 'Opened Evidence so the record can be strengthened before export.'));
</script>
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("adversarial_harness.optimizer.shutil.which", lambda name: None)

    task = SimpleNamespace(
        task_id="ui-task",
        target_files=[Path("templates/workspace.html")],
        constraints={"output_dir": str(output_dir)},
        metadata={
            "report_summary": {
                "selected_patch_briefs": [
                    {
                        "title": "UX repair 1",
                        "recommended_action": "Make one canonical release-gate state across Review, Draft, and Export metadata.",
                        "target_files": ["templates/workspace.html"],
                    },
                    {
                        "title": "UX repair 2",
                        "recommended_action": "Add a hard Unsupported/Thin elements blocker above Generate, Export, and Download, with direct Go to Evidence and Go to Review actions.",
                        "target_files": ["templates/workspace.html"],
                    },
                    {
                        "title": "UX repair 3",
                        "recommended_action": "Convert readiness from counts to a weighted confidence card (Grounded, Thin, Unsupported).",
                        "target_files": ["templates/workspace.html"],
                    },
                ]
            },
        },
    )

    result = fallback_cls(agent_id="fallback-ui", llm_router=None).optimize(task)

    updated = target_file.read_text(encoding="utf-8")
    assert result.status == "applied"
    assert result.metadata["optimizer_backend"] == "deterministic_workspace_fallback_optimizer"
    assert result.metadata["changed_files"] == ["templates/workspace.html"]
    assert result.metadata["covered_patch_brief_titles"] == ["UX repair 1", "UX repair 2", "UX repair 3"]
    assert result.metadata["selected_patch_brief_coverage_ratio"] == 1.0
    assert "Canonical filing verdict bar" in updated
    assert "unsupported-thin-blocker-coverage-note" in updated
    assert "draft-confidence-card" in updated
    assert "unsupported-thin-go-evidence-button" in updated


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


def test_build_ui_patch_tasks_carries_selected_patch_brief_batch_and_merged_targets(monkeypatch):
    optimizer = Optimizer()
    ui_review_report = {
        "review": "# Top Risks\n- Strengthen the draft rail.",
        "recommended_changes": [{"title": "Keep release gate visible"}],
    }
    monkeypatch.setattr(
        optimizer,
        "build_ui_optimization_bundle",
        lambda **kwargs: UIOptimizationBundle(
            timestamp="2026-03-23T00:00:00+00:00",
            screenshot_dir="screens",
            screenshot_paths=["screens/workspace-draft.png"],
            artifact_count=1,
            summary="Keep the draft gate visible and route the shell CTA correctly.",
            issues=[],
            recommended_changes=[{"title": "Keep release gate visible"}],
            broken_controls=[],
            complaint_journey={},
            actor_plan={},
            critic_review={},
            playwright_followups=[],
            target_files=["templates/workspace.html", "static/complaint_app_shell.js"],
            complaint_output_feedback={},
            patch_briefs=[
                {
                    "title": "Keep release gate visible",
                    "surface": "draft",
                    "problem": "The gate disappears below the fold.",
                    "recommended_action": "Keep the gate summary above export actions.",
                    "target_files": ["templates/workspace.html"],
                    "severity": "critical",
                },
                {
                    "title": "Clarify shell CTA routing",
                    "surface": "shell",
                    "problem": "The shell CTA doesn't send the user to the draft gate.",
                    "recommended_action": "Route the CTA to the draft guardrail.",
                    "target_files": ["static/complaint_app_shell.js"],
                    "severity": "warning",
                },
            ],
        ),
    )

    tasks = optimizer.build_ui_patch_tasks(
        ui_review_report=ui_review_report,
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(TEST_DRIVEN="TEST_DRIVEN"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    assert len(tasks) == 1
    task = tasks[0]
    assert [str(path) for path in task.target_files] == [
        "templates/workspace.html",
        "static/complaint_app_shell.js",
    ]
    report_summary = task.metadata["report_summary"]
    assert len(report_summary["selected_patch_briefs"]) == 2
    assert report_summary["selected_patch_briefs"][0]["title"] == "Keep release gate visible"
    assert report_summary["recommendation_coverage"]["selected_patch_briefs_count"] == 2
    assert report_summary["active_target_files"] == [
        "templates/workspace.html",
        "static/complaint_app_shell.js",
    ]


def test_build_ui_ux_optimization_task_prioritizes_carry_forward_patch_briefs(monkeypatch, tmp_path):
    optimizer = Optimizer()
    review_json_path = tmp_path / "review.json"
    review_payload = {
        "review": "# Top Risks\n- Keep release-gate guidance visible.",
        "recommended_changes": [
            {
                "title": "Current review change",
                "implementation_notes": "Clarify the current CTA.",
                "shared_code_path": "static/complaint_app_shell.js",
            }
        ],
    }
    review_json_path.write_text(json.dumps(review_payload), encoding="utf-8")
    monkeypatch.setattr(optimizer, "_read_ui_ux_review_json", lambda path: review_payload)
    monkeypatch.setattr(
        optimizer,
        "build_ui_optimization_bundle",
        lambda **kwargs: UIOptimizationBundle(
            timestamp="2026-03-23T00:00:00+00:00",
            screenshot_dir="screens",
            screenshot_paths=["screens/workspace-draft.png"],
            artifact_count=1,
            summary="Keep filing readiness visible.",
            issues=[],
            recommended_changes=[{"title": "Current review change"}],
            broken_controls=[],
            complaint_journey={},
            actor_plan={},
            critic_review={},
            playwright_followups=[],
            target_files=["static/complaint_app_shell.js"],
            complaint_output_feedback={},
            patch_briefs=[
                {
                    "title": "Current review change",
                    "surface": "shell",
                    "problem": "The current CTA is unclear.",
                    "recommended_action": "Clarify the shell CTA.",
                    "target_files": ["static/complaint_app_shell.js"],
                    "severity": "warning",
                }
            ],
        ),
    )

    task = optimizer.build_ui_ux_optimization_task(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
        pytest_target="playwright/tests/navigation.spec.js",
        iterations=1,
        metadata={
            "carry_forward_patch_briefs": [
                {
                    "title": "Carry forward release gate",
                    "surface": "draft",
                    "problem": "The release gate warning disappeared in the last round.",
                    "recommended_action": "Restore the release gate warning above export.",
                    "target_files": ["templates/workspace.html"],
                }
            ]
        },
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(ACTOR_CRITIC="ACTOR_CRITIC"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
        review_runs=[
            {
                "review_markdown_path": str(tmp_path / "review.md"),
                "review_json_path": str(review_json_path),
            }
        ],
        target_files=["static/complaint_app_shell.js"],
    )

    report_summary = task.metadata["report_summary"]
    assert report_summary["carry_forward_patch_briefs"][0]["title"] == "Carry forward release gate"
    assert report_summary["selected_patch_briefs"][0]["title"] == "Carry forward release gate"
    assert [str(path) for path in task.target_files] == ["templates/workspace.html", "static/complaint_app_shell.js"]


def test_select_ui_patch_briefs_diversifies_across_target_files():
    optimizer = Optimizer()

    prioritized = [
        {
            "title": "Workspace warning 1",
            "surface": "/workspace",
            "recommended_action": "Keep the verdict visible.",
            "target_files": ["templates/workspace.html"],
            "severity": "critical",
        },
        {
            "title": "Workspace warning 2",
            "surface": "/workspace",
            "recommended_action": "Keep the blocker summary pinned.",
            "target_files": ["templates/workspace.html"],
            "severity": "warning",
        },
        {
            "title": "Shell CTA repair",
            "surface": "/",
            "recommended_action": "Route the shell CTA into the draft gate.",
            "target_files": ["static/complaint_app_shell.js"],
            "severity": "warning",
        },
        {
            "title": "Playwright coverage repair",
            "surface": "/workspace",
            "recommended_action": "Assert the selected repair coverage in the browser flow.",
            "target_files": ["playwright/tests/complaint-flow.spec.js"],
            "severity": "warning",
        },
    ]

    selected = optimizer._select_ui_patch_briefs(
        prioritized,
        max_items=optimizer._ui_patch_brief_batch_limit(prioritized),
    )

    assert [item["title"] for item in selected] == [
        "Workspace warning 1",
        "Shell CTA repair",
        "Playwright coverage repair",
        "Workspace warning 2",
    ]


def test_build_ui_patch_tasks_selects_diverse_patch_brief_batch(monkeypatch):
    optimizer = Optimizer()
    ui_review_report = {"summary": "Keep verdicts and CTA routing coherent."}

    monkeypatch.setattr(
        optimizer,
        "build_ui_optimization_bundle",
        lambda **kwargs: UIOptimizationBundle(
            timestamp="2026-03-23T00:00:00+00:00",
            screenshot_dir="screens",
            screenshot_paths=["screens/workspace-draft.png"],
            artifact_count=1,
            summary="Keep filing readiness visible.",
            issues=[],
            recommended_changes=[
                {"title": "Workspace warning 1"},
                {"title": "Workspace warning 2"},
                {"title": "Shell CTA repair"},
                {"title": "Playwright coverage repair"},
            ],
            broken_controls=[],
            complaint_journey={},
            actor_plan={},
            critic_review={},
            playwright_followups=[],
            target_files=[
                "templates/workspace.html",
                "static/complaint_app_shell.js",
                "playwright/tests/complaint-flow.spec.js",
            ],
            complaint_output_feedback={},
            patch_briefs=[
                {
                    "title": "Workspace warning 1",
                    "surface": "/workspace",
                    "problem": "The filing verdict is too easy to miss.",
                    "recommended_action": "Keep the verdict visible.",
                    "target_files": ["templates/workspace.html"],
                    "severity": "critical",
                },
                {
                    "title": "Workspace warning 2",
                    "surface": "/workspace",
                    "problem": "The blocker summary scrolls away.",
                    "recommended_action": "Keep the blocker summary pinned.",
                    "target_files": ["templates/workspace.html"],
                    "severity": "warning",
                },
                {
                    "title": "Shell CTA repair",
                    "surface": "/",
                    "problem": "The shell CTA misses the draft guardrail.",
                    "recommended_action": "Route the shell CTA into the draft gate.",
                    "target_files": ["static/complaint_app_shell.js"],
                    "severity": "warning",
                },
                {
                    "title": "Playwright coverage repair",
                    "surface": "/workspace",
                    "problem": "The browser contract does not assert repair coverage.",
                    "recommended_action": "Assert the selected repair coverage in the browser flow.",
                    "target_files": ["playwright/tests/complaint-flow.spec.js"],
                    "severity": "warning",
                },
            ],
        ),
    )

    tasks = optimizer.build_ui_patch_tasks(
        ui_review_report=ui_review_report,
        components={
            "OptimizationTask": lambda **kwargs: SimpleNamespace(**kwargs),
            "OptimizationMethod": SimpleNamespace(TEST_DRIVEN="TEST_DRIVEN"),
            "OptimizerLLMRouter": None,
            "optimizer_classes": {},
        },
    )

    task = tasks[0]
    report_summary = task.metadata["report_summary"]
    assert [item["title"] for item in report_summary["selected_patch_briefs"]] == [
        "Workspace warning 1",
        "Shell CTA repair",
        "Playwright coverage repair",
        "Workspace warning 2",
    ]
    assert [str(path) for path in task.target_files] == [
        "templates/workspace.html",
        "static/complaint_app_shell.js",
        "playwright/tests/complaint-flow.spec.js",
    ]
    assert report_summary["recommendation_coverage"]["selected_patch_briefs_count"] == 4


def test_ui_patch_brief_batch_limit_carries_full_review_set_up_to_cap():
    optimizer = Optimizer()
    prioritized = [{"title": f"Repair {index}", "target_files": [f"file-{index}.txt"]} for index in range(1, 16)]

    assert optimizer._ui_patch_brief_batch_limit(prioritized) == 12
