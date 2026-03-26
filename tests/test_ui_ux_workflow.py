import json
from pathlib import Path

import pytest

from complaint_generator import (
    build_ui_ux_review_prompt,
    review_screenshot_audit_with_llm_router,
    run_closed_loop_ui_ux_improvement,
    run_end_to_end_complaint_browser_audit,
    run_iterative_ui_ux_workflow,
    run_playwright_screenshot_audit,
    structure_ui_ux_review,
)
from complaint_generator import ui_ux_workflow as workflow_module


pytestmark = [pytest.mark.no_auto_network]


def _write_artifact(directory: Path, name: str, url: str = "http://example.test/workspace") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "url": url,
                "title": "Unified Complaint Workspace",
                "viewport": {"width": 1440, "height": 1200},
                "text_excerpt": "Unified Complaint Workspace\nEvidence Intake\nDraft and Edit",
                "screenshot_path": str(directory / f"{name}.png"),
            }
        )
    )
    (directory / f"{name}.png").write_bytes(b"fake-png")


def test_ui_ux_workflow_defaults_target_full_feature_audit_and_actor_critic_optimizer():
    assert workflow_module.DEFAULT_SCREENSHOT_TEST == "playwright/tests/complaint-flow.spec.js"
    assert workflow_module.DEFAULT_OPTIMIZER_METHOD == "actor_critic"
    assert workflow_module.DEFAULT_OPTIMIZER_PRIORITY == 90
    assert any("first-time complainants" in goal for goal in workflow_module.DEFAULT_UI_UX_REVIEW_GOALS)
    assert any("filing-ready legal complaint" in goal for goal in workflow_module.DEFAULT_UI_UX_REVIEW_GOALS)
    assert any("Evidence capture" in item for item in workflow_module.DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES)
    assert "package, CLI, MCP, and browser SDK" in workflow_module.DEFAULT_UI_UX_REVIEW_NOTES
    assert "release blocker" in workflow_module.DEFAULT_UI_UX_REVIEW_NOTES


def test_build_ui_ux_review_prompt_includes_artifacts_and_surface_contract(tmp_path):
    _write_artifact(tmp_path, "workspace")
    (tmp_path / "complaint-export.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "url": "http://example.test/workspace?target_tab=integrations",
                "title": "Unified Complaint Workspace",
                "viewport": {"width": 1440, "height": 1200},
                "text_excerpt": "Complaint packet exported",
                "artifact_type": "complaint_export",
                "claim_type": "retaliation",
                "draft_strategy": "llm_router",
                "filing_shape_score": 86,
                "claim_type_alignment_score": 35,
                "claim_type_alignment": {
                    "complaint_heading_matches": False,
                    "count_heading_matches": False,
                },
                "markdown_filename": "jordan-example-complaint.md",
                "pdf_filename": "jordan-example-complaint.pdf",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "pdf_header": "%PDF-1.4",
                "ui_suggestions_excerpt": "Add stronger export warnings when support gaps remain.",
            }
        )
    )

    prompt = build_ui_ux_review_prompt(
        iteration=2,
        artifacts=workflow_module.collect_screenshot_artifacts(tmp_path),
        previous_review="Previous iteration asked for clearer intake guidance.",
    )

    assert "Iteration: 2" in prompt
    assert "Screenshot path:" in prompt
    assert "workspace.html" not in prompt  # prompt includes file contents, not just filenames
    assert "complaint-mcp-server" in prompt or "complaint-generator-mcp" in prompt
    assert "JavaScript MCP SDK" in prompt or "ComplaintMcpClient" in prompt
    assert "Previous iteration asked for clearer intake guidance." in prompt
    assert "Treat this as an actor/critic workflow audit with adversarial pressure-testing" in prompt
    assert "actor/critic lens" in prompt
    assert "visible buttons, links, tabs, and handoff controls" in prompt
    assert "Required capability audit:" in prompt
    assert "Hidden Or Missing Feature Paths" in prompt
    assert "Stage Findings" in prompt
    assert "Actor Journey Findings" in prompt
    assert "Critic Test Obligations" in prompt
    assert "Actor Plan" in prompt
    assert "Critic Verdict" in prompt
    assert "control audit matrix" in prompt
    assert "Intake`, `Evidence`, `Review`, `Draft`, and `Integration Discovery`" in prompt
    assert "save a shared synopsis for the mediator path" in prompt
    assert "Complaint-output-informed UI suggestions:" in prompt
    assert "Claim type: retaliation" in prompt
    assert "Draft strategy: llm_router" in prompt
    assert "Filing shape score: 86" in prompt
    assert "formal pleading" in prompt
    assert "jurisdiction or venue section" in prompt
    assert "markdown, PDF, and docx downloads succeed" in prompt
    assert "claim-type alignment data" in prompt
    assert "Add stronger export warnings when support gaps remain." in prompt
    assert "complaint_generator.analyze_complaint_output" in prompt
    assert "complaint-workspace export-markdown" in prompt
    assert "complaint-workspace export-pdf" in prompt
    assert "complaint-workspace analyze-output" in prompt
    assert "complaint.analyze_complaint_output" in prompt
    assert "exportComplaintMarkdown()" in prompt
    assert "exportComplaintPdf()" in prompt
    assert "analyzeComplaintOutput()" in prompt
    assert "Use the screenshot evidence together with any complaint-output analysis excerpts" in prompt
    assert "claim type, draft strategy, and exported complaint filing quality remain aligned" in prompt


def test_build_ui_ux_review_prompt_includes_cached_ui_readiness_artifacts(tmp_path):
    _write_artifact(tmp_path, "workspace")

    prompt = build_ui_ux_review_prompt(
        iteration=3,
        artifacts=workflow_module.collect_review_artifacts(
            tmp_path,
            supplemental_artifacts=[
                {
                    "name": "workspace-cached-ui-readiness",
                    "url": "/workspace?target_tab=ux-review",
                    "title": "Cached UX Audit Review",
                    "artifact_type": "ui_readiness_review",
                    "verdict": "Needs repair",
                    "score": 72,
                    "critic_verdict": "warning",
                    "workflow_type": "iterative_actor_critic_review",
                    "screenshot_findings": [
                        {
                            "stage": "Draft",
                            "surface": "workspace-draft",
                            "summary": "Export controls are visually buried beneath dense metadata.",
                        }
                    ],
                    "optimization_targets": [
                        {
                            "title": "Pin export controls beside the complaint preview",
                            "reason": "The actor should not hunt for the next step after draft generation.",
                        }
                    ],
                    "playwright_followups": [
                        "Verify the export controls stay visible after testimony edits.",
                    ],
                    "recommended_changes": [
                        "Keep the export lane sticky within the draft panel.",
                    ],
                    "review_excerpt": "Cached review says the draft stage still hides exports.",
                }
            ],
        ),
    )

    assert "Cached review artifact type: ui_readiness_review" in prompt
    assert "Cached UI verdict: Needs repair" in prompt
    assert "Previously observed screenshot findings:" in prompt
    assert "workspace-draft" in prompt
    assert "Previously proposed optimization targets:" in prompt
    assert "Pin export controls beside the complaint preview" in prompt
    assert "Previously proposed Playwright follow-ups:" in prompt
    assert "Verify the export controls stay visible after testimony edits." in prompt
    assert "Previously recommended changes:" in prompt
    assert "Keep the export lane sticky within the draft panel." in prompt
    assert "Cached review excerpt:" in prompt
    assert "prior unresolved hypotheses" in prompt


def test_build_ui_ux_review_prompt_uses_default_goals_and_notes_when_not_supplied(tmp_path):
    _write_artifact(tmp_path, "workspace")

    prompt = build_ui_ux_review_prompt(
        iteration=1,
        artifacts=workflow_module.collect_screenshot_artifacts(tmp_path),
    )

    assert "Workflow goals:" in prompt
    assert "first-time complainants" in prompt
    assert "Review notes:" in prompt
    assert "complaint operator both need to succeed" in prompt
    assert "Package, CLI, MCP server, and JavaScript SDK entry points remain discoverable" in prompt


def test_run_playwright_screenshot_audit_uses_configured_artifact_directory(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"

    def fake_run(cmd, cwd, env, stdout, stderr, text, check):
        assert cmd == ["npm", "run", "test:e2e", "--", "--workers=1", "playwright/tests/complaint-flow.spec.js"]
        assert env["COMPLAINT_UI_SCREENSHOT_DIR"] == str(screenshot_dir)
        assert env["RUN_LLM_TESTS"] == "1"
        assert env["RUN_NETWORK_TESTS"] == "1"
        assert env["RUN_HEAVY_TESTS"] == "1"
        _write_artifact(screenshot_dir, "workspace")

        class Result:
            returncode = 0
            stdout = "1 passed"
            stderr = ""

        return Result()

    monkeypatch.setattr(workflow_module.subprocess, "run", fake_run)

    result = run_playwright_screenshot_audit(screenshot_dir=screenshot_dir, pytest_executable="pytest")

    assert result["returncode"] == 0
    assert result["artifact_count"] == 1
    assert result["artifacts"][0]["name"] == "workspace"


def test_iterative_workflow_raises_when_audit_returns_no_screenshots(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"

    monkeypatch.setattr(
        workflow_module,
        "run_playwright_screenshot_audit",
        lambda **kwargs: {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 skipped",
            "stderr": "",
            "artifact_count": 0,
            "artifacts": [],
            "screenshot_dir": str(screenshot_dir),
        },
    )

    with pytest.raises(RuntimeError, match="without screenshot artifacts"):
        run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=output_dir,
            iterations=1,
        )


def test_run_end_to_end_complaint_browser_audit_delegates_to_playwright_audit(monkeypatch, tmp_path):
    captured = {}

    def fake_audit(**kwargs):
        captured.update(kwargs)
        return {"returncode": 0, "artifact_count": 4, "screenshot_dir": str(kwargs["screenshot_dir"])}

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)

    result = run_end_to_end_complaint_browser_audit(
        screenshot_dir=tmp_path / "screens",
    )

    assert result["returncode"] == 0
    assert result["artifact_count"] == 4
    assert str(captured["screenshot_dir"]).endswith("screens")
    assert str(captured["pytest_target"]) == "playwright/tests/complaint-flow.spec.js"


def test_review_and_iterative_workflow_return_llm_router_output(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")
    expected_image_path = str((screenshot_dir / "workspace.png").resolve())

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Unified Complaint Workspace" in prompt
            assert image_paths == [expected_image_path]
            assert system_prompt
            return "# Top Risks\n- Intake flow needs calmer language."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)
    assert "Top Risks" in review["review"]
    assert review["issues"][0]["problem"] == "Intake flow needs calmer language."
    assert review["screenshot_findings"][0]["criticisms"]

    def fake_audit(**kwargs):
        _write_artifact(screenshot_dir, "workspace")
        return {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 passed",
            "stderr": "",
            "artifact_count": 1,
            "artifacts": workflow_module.collect_screenshot_artifacts(screenshot_dir),
            "screenshot_dir": str(screenshot_dir),
        }

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=2,
    )

    assert result["iterations"] == 2
    assert (output_dir / "iteration-01-review.md").exists()
    assert (output_dir / "iteration-02-review.json").exists()
    assert result["review"]["issues"][0]["problem"] == "Intake flow needs calmer language."
    assert result["runs"][0]["issues_count"] >= 1


def test_iterative_workflow_can_reuse_existing_screenshots_without_rerunning_playwright(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert image_paths
            return "# Top Risks\n- Reused screenshots still show one weak evidence cue."

    def fail_if_called(**kwargs):
        raise AssertionError("Playwright audit should not run when reusing existing screenshots.")

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)
    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fail_if_called)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=1,
        reuse_existing_screenshots=True,
    )

    assert result["iterations"] == 1
    assert result["reuse_existing_screenshots"] is True
    progress_payload = json.loads((output_dir / "workflow-progress.json").read_text())
    assert progress_payload["status"] == "completed"


def test_structure_ui_ux_review_builds_screenshot_driven_structured_feedback(tmp_path):
    _write_artifact(tmp_path, "workspace-intake", url="http://example.test/workspace?tab=intake")
    _write_artifact(tmp_path, "workspace-evidence", url="http://example.test/workspace?tab=evidence")
    artifacts = workflow_module.collect_screenshot_artifacts(tmp_path)

    review_text = """# Top Risks
- The intake call to action is easy to miss on the homepage.
- Evidence upload looks secondary even though it is required before filing.

# High-Impact UX Fixes
- Promote a single primary intake action above competing shortcuts.
- Move evidence upload into the main progression rail and label it as required.

# Stage Findings
## Intake
The actor can miss the first required step because the primary intake action is visually buried.
## Evidence
Evidence capture looks optional, which weakens the complaint record before generation.

# Actor Journey Findings
- The actor can start intake, but the first step is too easy to miss.

# Critic Test Obligations
- Click the primary intake CTA and confirm the intake panel becomes the dominant focus.

# Playwright Assertions To Add
- Assert the evidence upload control is visible and marked required before complaint generation.

# Actor Plan
- Clarify the first action and keep the actor on a linear path through evidence.

# Critic Verdict
Warning: the flow is usable, but the screenshots still show misleading hierarchy.
"""
    structured = structure_ui_ux_review(review_text=review_text, artifacts=artifacts, iteration=1)

    assert structured["issues"][0]["problem"] == "The intake call to action is easy to miss on the homepage."
    assert structured["recommended_changes"][0]["implementation_notes"].startswith("Promote a single primary intake action")
    assert structured["stage_findings"]["Intake"].startswith("The actor can miss")
    assert structured["critic_review"]["verdict"] == "warning"
    assert len(structured["screenshot_findings"]) == 2
    assert structured["screenshot_findings"][0]["criticisms"]
    assert structured["optimization_targets"][0]["target_surface"]


def test_structure_ui_ux_review_builds_carry_forward_assessment_from_cached_ui_review_artifact(tmp_path):
    artifacts = workflow_module.collect_screenshot_artifacts(tmp_path)
    _write_artifact(tmp_path, "workspace-draft", url="http://example.test/workspace?tab=draft")
    artifacts = workflow_module.collect_screenshot_artifacts(tmp_path)
    artifacts.append(
        {
            "name": "workspace-cached-ui-readiness",
            "artifact_type": "ui_readiness_review",
            "screenshot_findings": [
                {
                    "stage": "Draft",
                    "surface": "http://example.test/workspace?tab=draft",
                    "summary": "Export controls are visually buried beneath dense metadata.",
                },
                {
                    "stage": "Review",
                    "surface": "http://example.test/workspace?tab=review",
                    "summary": "Support gaps were too easy to miss.",
                },
            ],
            "optimization_targets": [
                {
                    "title": "UX repair 1",
                    "target_surface": "templates/workspace.html",
                    "reason": "Pin export controls beside the complaint preview.",
                }
            ],
        }
    )

    review_text = """# Top Risks
- The export controls are still too easy to miss on the draft screen.

# High-Impact UX Fixes
- Pin export controls beside the complaint preview and mediator handoff panel.

# Stage Findings
## Draft
The draft stage still buries the export action below metadata and secondary controls.

# Critic Verdict
Warning: the draft flow still needs a clearer next step.
"""
    structured = structure_ui_ux_review(review_text=review_text, artifacts=artifacts, iteration=2)

    carry_forward = structured["carry_forward_assessment"]
    assert carry_forward["prior_review_available"] is True
    assert carry_forward["unresolved_findings"][0]["stage"] == "Draft"
    assert carry_forward["resolved_findings"][0]["stage"] == "Review"
    assert carry_forward["continued_optimization_targets"][0]["title"] == "UX repair 1"
    assert "still appear unresolved" in carry_forward["summary"]


def test_review_workflow_routes_complaint_output_analysis_into_multimodal_prompt(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    _write_artifact(screenshot_dir, "workspace")
    expected_image_path = str((screenshot_dir / "workspace.png").resolve())
    (screenshot_dir / "workspace-export-artifacts.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "markdown_filename": "complaint.md",
                "pdf_filename": "complaint.pdf",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "pdf_header": "%PDF-1.4",
                "ui_suggestions_excerpt": "Promote the unsupported-elements warning before export.",
            }
        )
    )

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Promote the unsupported-elements warning before export." in prompt
            assert "Jordan Example brings this retaliation complaint against Acme Corporation." in prompt
            assert "Use the screenshot evidence together with any complaint-output analysis excerpts" in prompt
            assert image_paths == [expected_image_path]
            assert system_prompt
            return "# Top Risks\n- Export warnings are still too easy to miss."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)

    assert "Export warnings are still too easy to miss." in review["review"]


def test_iterative_workflow_routes_supplemental_complaint_output_artifacts_into_prompt(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")
    expected_image_path = str((screenshot_dir / "workspace.png").resolve())

    def fake_audit(**kwargs):
        _write_artifact(screenshot_dir, "workspace")
        return {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 passed",
            "stderr": "",
            "artifact_count": 1,
            "artifacts": workflow_module.collect_screenshot_artifacts(screenshot_dir),
            "screenshot_dir": str(screenshot_dir),
        }

    class FakeMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            assert "Tighten review-to-draft gatekeeping" in prompt
            assert "Add stronger blocker language" in prompt
            assert image_paths == [expected_image_path]
            assert system_prompt
            return "# Top Risks\n- Review picked up complaint-output suggestions."

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)
    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FakeMultimodalBackend)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=1,
        supplemental_artifacts=[
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "markdown_excerpt": "Jordan Example brings this retaliation complaint against Acme Corporation.",
                "ui_suggestions_excerpt": "- Tighten review-to-draft gatekeeping: Add stronger blocker language before export.",
            }
        ],
    )

    assert result["iterations"] == 1
    assert (output_dir / "iteration-01-review.md").exists()


def test_review_workflow_falls_back_to_text_router_when_multimodal_review_fails(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    _write_artifact(screenshot_dir, "workspace")

    class FailingMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise RuntimeError("vision unavailable")

    class FakeFallbackBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id

        def __call__(self, prompt):
            assert "Unified Complaint Workspace" in prompt
            return "# Top Risks\n- Fallback text review."

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(workflow_module, "LLMRouterBackend", FakeFallbackBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)

    assert "Fallback text review" in review["review"]
    assert review["backend"]["strategy"] == "llm_router"
    assert review["backend"]["fallback_from"] == "multimodal_router"


def test_review_workflow_returns_deterministic_fallback_when_all_router_paths_fail(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    _write_artifact(screenshot_dir, "workspace")
    (screenshot_dir / "workspace-export-artifacts.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "claim_type": "retaliation",
                "draft_strategy": "llm_router",
                "filing_shape_score": 100,
                "claim_type_alignment_score": 100,
                "ui_suggestions_excerpt": "Keep release-gate, filing-shape, and export guidance visible before download.",
            }
        )
    )

    class FailingMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise TimeoutError("vision timed out")

    class FailingFallbackBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt):
            raise TimeoutError("text fallback timed out")

    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(workflow_module, "LLMRouterBackend", FailingFallbackBackend)

    review = review_screenshot_audit_with_llm_router(screenshot_dir=screenshot_dir, iteration=1)

    assert "Router-backed screenshot review timed out" in review["review"]
    assert review["backend"]["strategy"] == "deterministic_fallback"
    assert "vision timed out" in review["backend"]["multimodal_error"]
    assert "text fallback timed out" in review["backend"]["fallback_error"]
    assert review["structured_review"]["critic_review"]["verdict"] == "warning"


def test_iterative_workflow_writes_completed_review_when_router_paths_timeout(monkeypatch, tmp_path):
    screenshot_dir = tmp_path / "screens"
    output_dir = tmp_path / "reviews"
    _write_artifact(screenshot_dir, "workspace")
    (screenshot_dir / "workspace-export-artifacts.json").write_text(
        json.dumps(
            {
                "name": "workspace-export-artifacts",
                "artifact_type": "complaint_export",
                "claim_type": "retaliation",
                "draft_strategy": "llm_router",
                "filing_shape_score": 92,
                "claim_type_alignment_score": 88,
            }
        )
    )

    def fake_audit(**kwargs):
        return {
            "command": ["pytest"],
            "returncode": 0,
            "stdout": "1 passed",
            "stderr": "",
            "artifact_count": 1,
            "artifacts": workflow_module.collect_screenshot_artifacts(screenshot_dir),
            "screenshot_dir": str(screenshot_dir),
        }

    class FailingMultimodalBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt, *, image_paths=None, system_prompt=None):
            raise TimeoutError("vision timed out")

    class FailingFallbackBackend:
        def __init__(self, id, provider=None, model=None):
            self.id = id
            self.provider = provider
            self.model = model

        def __call__(self, prompt):
            raise TimeoutError("text timed out")

    monkeypatch.setattr(workflow_module, "run_playwright_screenshot_audit", fake_audit)
    monkeypatch.setattr(workflow_module, "MultimodalRouterBackend", FailingMultimodalBackend)
    monkeypatch.setattr(workflow_module, "LLMRouterBackend", FailingFallbackBackend)

    result = run_iterative_ui_ux_workflow(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        iterations=1,
    )

    assert result["iterations"] == 1
    assert result["review"]["critic_review"]["verdict"] == "warning"
    assert result["runs"][0]["issues_count"] >= 1
    progress_payload = json.loads((output_dir / "workflow-progress.json").read_text())
    assert progress_payload["status"] == "completed"
    assert (output_dir / "iteration-01-review.md").exists()
    assert (output_dir / "iteration-01-review.json").exists()


def test_closed_loop_ui_ux_improvement_delegates_to_optimizer(monkeypatch, tmp_path):
    captured = {}

    def fake_feedback_loop(self, **kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr("adversarial_harness.optimizer.Optimizer.run_agentic_ui_ux_feedback_loop", fake_feedback_loop)

    result = run_closed_loop_ui_ux_improvement(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
        max_rounds=2,
        review_iterations=1,
        notes="Focus on calmer intake wording.",
        goals=["keep the full complaint flow visible", "make the intake calmer"],
        method="adversarial",
        priority=92,
        supplemental_artifacts=[{"artifact_type": "complaint_export", "ui_suggestions_excerpt": "Keep export blockers visible."}],
    )

    assert result["workflow_type"] == "ui_ux_closed_loop"
    assert captured["max_rounds"] == 2
    assert captured["notes"] == "Focus on calmer intake wording."
    assert captured["goals"] == ["keep the full complaint flow visible", "make the intake calmer"]
    assert captured["method"] == "adversarial"
    assert captured["priority"] == 92
    assert captured["metadata"]["supplemental_artifacts"][0]["artifact_type"] == "complaint_export"
    assert captured["reuse_existing_screenshots"] is False


def test_closed_loop_ui_ux_improvement_uses_default_brief_when_none_is_supplied(monkeypatch, tmp_path):
    captured = {}

    def fake_feedback_loop(self, **kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr("adversarial_harness.optimizer.Optimizer.run_agentic_ui_ux_feedback_loop", fake_feedback_loop)

    run_closed_loop_ui_ux_improvement(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
    )

    assert captured["method"] == workflow_module.DEFAULT_OPTIMIZER_METHOD
    assert captured["priority"] == workflow_module.DEFAULT_OPTIMIZER_PRIORITY
    assert captured["goals"] == workflow_module.DEFAULT_UI_UX_REVIEW_GOALS
    assert captured["notes"] == workflow_module.DEFAULT_UI_UX_REVIEW_NOTES
    assert captured["reuse_existing_screenshots"] is False


def test_closed_loop_ui_ux_improvement_can_delegate_reuse_existing_screenshots(monkeypatch, tmp_path):
    captured = {}

    def fake_feedback_loop(self, **kwargs):
        captured.update(kwargs)
        return {"workflow_type": "ui_ux_closed_loop", "rounds_executed": 1}

    monkeypatch.setattr("adversarial_harness.optimizer.Optimizer.run_agentic_ui_ux_feedback_loop", fake_feedback_loop)

    run_closed_loop_ui_ux_improvement(
        screenshot_dir=tmp_path / "screens",
        output_dir=tmp_path / "reviews",
        reuse_existing_screenshots=True,
    )

    assert captured["reuse_existing_screenshots"] is True
