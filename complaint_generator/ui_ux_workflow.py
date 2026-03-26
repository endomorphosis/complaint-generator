from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backends import LLMRouterBackend, MultimodalRouterBackend


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENSHOT_TEST = "playwright/tests/complaint-flow.spec.js"
DEFAULT_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_OPTIMIZER_PRIORITY = 90
DEFAULT_UI_UX_REVIEW_GOALS = [
    "Make the complaint generator easier for first-time complainants to complete without legal coaching.",
    "Keep intake, evidence, review, draft, package, CLI, MCP, and JavaScript SDK paths visibly connected as one workflow.",
    "Expose every major complaint-generator capability with clearer next-step guidance so users can actually use the full system.",
    "Prefer calmer, trauma-informed language and remove friction that makes evidence capture or draft completion feel risky or confusing.",
    "Make the end-to-end actor journey work cleanly from testimony and intake through evidence upload, claim review, complaint generation, and final draft revision.",
    "Make the final markdown, PDF, and docx outputs read like a filing-ready legal complaint with a coherent caption, jurisdiction section, counts, prayer for relief, signature block, and export/download affordances that match the selected claim type.",
]
DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES = [
    "Intake questions can be understood and completed without legal coaching.",
    "Evidence capture makes it clear what proof helps each claim element.",
    "Support review makes missing elements and next evidence steps obvious.",
    "Draft generation and editing feel like the natural continuation of intake and review.",
    "The workspace makes progress, readiness, and next-step guidance legible under stress.",
    "Package, CLI, MCP server, and JavaScript SDK entry points remain discoverable as first-class capabilities.",
    "The actor/critic optimizer path is clearly available, while adversarial pressure-testing remains discoverable as a secondary stress lane.",
]
DEFAULT_UI_UX_REVIEW_NOTES = (
    "Review the interface as if a stressed first-time complainant and a complaint operator both need to succeed without hand-holding. "
    "Actively look for places where the user could miss a required step, misunderstand what evidence helps prove, lose track of progress, "
    "or fail to discover package, CLI, MCP, and browser SDK capabilities that should remain part of one coherent complaint workflow. "
    "Treat any mismatch between the selected claim type, the visible complaint framing, and the exported pleading shape as a release blocker."
)


def _read_text(path: Path, limit: int = 12000) -> str:
    text = path.read_text()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def _write_progress_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(payload or {})
    normalized["updated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True))


def collect_screenshot_artifacts(screenshot_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(screenshot_dir)
    artifacts: list[dict[str, Any]] = []
    for metadata_path in sorted(root.glob("*.json")):
        payload = json.loads(metadata_path.read_text())
        artifacts.append(payload)
    return artifacts


def collect_review_artifacts(
    screenshot_dir: str | Path,
    supplemental_artifacts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    artifacts = collect_screenshot_artifacts(screenshot_dir)
    for artifact in supplemental_artifacts or []:
        if isinstance(artifact, dict):
            artifacts.append(dict(artifact))
    return artifacts


def _artifact_image_paths(artifacts: list[dict[str, Any]]) -> list[str]:
    image_paths: list[str] = []
    for artifact in artifacts:
        raw_path = str(artifact.get("screenshot_path", "") or "").strip()
        if raw_path:
            image_paths.append(raw_path)
    return image_paths


def _resolve_review_goals(goals: list[str] | None) -> list[str]:
    cleaned = [goal.strip() for goal in (goals or []) if str(goal).strip()]
    return cleaned or list(DEFAULT_UI_UX_REVIEW_GOALS)


def _resolve_review_notes(notes: str | None) -> str:
    cleaned = str(notes or "").strip()
    return cleaned or DEFAULT_UI_UX_REVIEW_NOTES


def _markdown_heading_sections(markdown_text: str) -> dict[str, str]:
    text = str(markdown_text or "")
    pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = str(match.group(2) or "").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()
    return sections


def _markdown_bullets(section_text: str) -> list[str]:
    bullets: list[str] = []
    for line in str(section_text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            bullets.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
    return [item for item in bullets if item]


def _first_nonempty_line(section_text: str) -> str:
    for line in str(section_text or "").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            return cleaned
    return ""


def _extract_named_markdown_section(markdown_text: str, heading: str) -> str:
    escaped = re.escape(str(heading or "").strip())
    pattern = re.compile(
        rf"(?ms)^\#{1,6}\s+{escaped}\s*$\n?(.*?)(?=^\#{1,6}\s+.+?$|\Z)"
    )
    match = pattern.search(str(markdown_text or ""))
    return str(match.group(1) or "").strip() if match else ""


def _stage_from_artifact(artifact: dict[str, Any]) -> str:
    haystack = " ".join(
        [
            str(artifact.get("name") or ""),
            str(artifact.get("title") or ""),
            str(artifact.get("url") or ""),
            str(artifact.get("text_excerpt") or ""),
        ]
    ).lower()
    if "intake" in haystack or "chat" in haystack:
        return "Intake"
    if "evidence" in haystack or "document" in haystack:
        return "Evidence"
    if "review" in haystack or "support" in haystack:
        return "Review"
    if "draft" in haystack or "builder" in haystack or "document" in haystack:
        return "Draft"
    if "integration" in haystack or "sdk" in haystack or "tool" in haystack:
        return "Integration Discovery"
    return "Workspace"


def _surface_from_artifact(artifact: dict[str, Any]) -> str:
    url = str(artifact.get("url") or "").strip()
    name = str(artifact.get("name") or "").strip()
    title = str(artifact.get("title") or "").strip()
    return url or name or title or "unknown-surface"


def _artifact_text_context(artifact: dict[str, Any]) -> str:
    return " ".join(
        [
            str(artifact.get("name") or ""),
            str(artifact.get("title") or ""),
            str(artifact.get("text_excerpt") or ""),
            str(artifact.get("url") or ""),
        ]
    ).lower()


def _match_artifacts_to_stage(
    artifacts: list[dict[str, Any]],
    stage_name: str,
) -> list[dict[str, Any]]:
    matches = [artifact for artifact in artifacts if _stage_from_artifact(artifact) == stage_name]
    return matches or list(artifacts[:1])


def _build_screenshot_findings(
    *,
    artifacts: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    stage_findings: dict[str, str],
    top_risks: list[str],
) -> list[dict[str, Any]]:
    screenshot_findings: list[dict[str, Any]] = []
    for artifact in artifacts:
        stage_name = _stage_from_artifact(artifact)
        artifact_context = _artifact_text_context(artifact)
        related_issues = [
            dict(item)
            for item in issues
            if str(item.get("surface") or "").strip() in {"", _surface_from_artifact(artifact)}
            or str(item.get("surface") or "").strip().lower() in artifact_context
            or stage_name.lower() in str(item.get("surface") or "").strip().lower()
        ]
        if not related_issues and top_risks:
            related_issues = [
                {
                    "severity": "warning",
                    "surface": _surface_from_artifact(artifact),
                    "problem": top_risks[0],
                    "user_impact": stage_findings.get(stage_name) or top_risks[0],
                    "recommended_fix": "Use this screenshot to verify the actor can see the next required complaint step without guessing.",
                }
            ]
        screenshot_findings.append(
            {
                "name": str(artifact.get("name") or "").strip() or "screenshot",
                "path": str(artifact.get("screenshot_path") or "").strip(),
                "url": str(artifact.get("url") or "").strip(),
                "stage": stage_name,
                "surface": _surface_from_artifact(artifact),
                "visible_text_excerpt": str(artifact.get("text_excerpt") or "").strip(),
                "stage_finding": str(stage_findings.get(stage_name) or "").strip(),
                "criticisms": related_issues[:3],
            }
        )
    return screenshot_findings


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _build_carry_forward_assessment(
    *,
    artifacts: list[dict[str, Any]],
    screenshot_findings: list[dict[str, Any]],
    optimization_targets: list[dict[str, Any]],
    stage_findings: dict[str, str],
) -> dict[str, Any]:
    prior_review_artifact = next(
        (
            dict(item)
            for item in artifacts
            if isinstance(item, dict) and str(item.get("artifact_type") or "").strip() == "ui_readiness_review"
        ),
        {},
    )
    if not prior_review_artifact:
        return {
            "prior_review_available": False,
            "unresolved_findings": [],
            "resolved_findings": [],
            "continued_optimization_targets": [],
            "retired_optimization_targets": [],
            "summary": "",
        }

    current_stage_keys = {_normalized_text(key) for key in stage_findings.keys()}
    current_surface_keys = {
        _normalized_text(item.get("surface") or item.get("name") or item.get("stage") or "")
        for item in screenshot_findings
    }
    current_target_keys = {
        _normalized_text(item.get("title") or item.get("target_surface") or item.get("reason") or "")
        for item in optimization_targets
    }

    unresolved_findings: list[dict[str, Any]] = []
    resolved_findings: list[dict[str, Any]] = []
    for item in list(prior_review_artifact.get("screenshot_findings") or []):
        if not isinstance(item, dict):
            continue
        stage_key = _normalized_text(item.get("stage") or "")
        surface_key = _normalized_text(item.get("surface") or item.get("name") or "")
        summary = str(item.get("summary") or item.get("stage_finding") or "").strip()
        record = {
            "stage": str(item.get("stage") or "").strip(),
            "surface": str(item.get("surface") or item.get("name") or "").strip(),
            "summary": summary,
        }
        if (stage_key and stage_key in current_stage_keys) or (surface_key and surface_key in current_surface_keys):
            unresolved_findings.append(record)
        else:
            resolved_findings.append(record)

    continued_targets: list[dict[str, Any]] = []
    retired_targets: list[dict[str, Any]] = []
    for item in list(prior_review_artifact.get("optimization_targets") or []):
        if not isinstance(item, dict):
            continue
        target_key = _normalized_text(item.get("title") or item.get("target") or item.get("target_surface") or "")
        record = {
            "title": str(item.get("title") or item.get("target") or item.get("target_surface") or "").strip(),
            "target_surface": str(item.get("target_surface") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
        }
        if target_key and target_key in current_target_keys:
            continued_targets.append(record)
        else:
            retired_targets.append(record)

    summary_parts: list[str] = []
    if unresolved_findings:
        summary_parts.append(f"{len(unresolved_findings)} prior screenshot finding(s) still appear unresolved.")
    if resolved_findings:
        summary_parts.append(f"{len(resolved_findings)} prior screenshot finding(s) look improved or no longer visible.")
    if continued_targets:
        summary_parts.append(f"{len(continued_targets)} optimization target(s) carried forward into this pass.")
    if retired_targets:
        summary_parts.append(f"{len(retired_targets)} optimization target(s) were not repeated in the new review.")

    return {
        "prior_review_available": True,
        "unresolved_findings": unresolved_findings,
        "resolved_findings": resolved_findings,
        "continued_optimization_targets": continued_targets,
        "retired_optimization_targets": retired_targets,
        "summary": " ".join(summary_parts).strip(),
    }


def structure_ui_ux_review(
    *,
    review_text: str,
    artifacts: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any]:
    sections = _markdown_heading_sections(review_text)
    top_risks = _markdown_bullets(sections.get("Top Risks", ""))
    fixes = _markdown_bullets(sections.get("High-Impact UX Fixes", ""))
    playwright_followups = _markdown_bullets(sections.get("Playwright Assertions To Add", "")) or _markdown_bullets(
        sections.get("Critic Test Obligations", "")
    )
    hidden_paths = _markdown_bullets(sections.get("Hidden Or Missing Feature Paths", ""))
    actor_plan_lines = _markdown_bullets(sections.get("Actor Plan", ""))
    implementation_order = _markdown_bullets(sections.get("Implementation Order", ""))
    complaint_journey_lines = _markdown_bullets(sections.get("Complaint Journey Coverage", ""))
    actor_journey_lines = _markdown_bullets(sections.get("Actor Journey Findings", ""))
    mcp_sdk_lines = _markdown_bullets(sections.get("MCP/SDK Workflow Improvements", ""))
    critic_test_lines = _markdown_bullets(sections.get("Critic Test Obligations", ""))
    language_lines = _markdown_bullets(sections.get("Complaint Intake Language Fixes", ""))
    critic_section = sections.get("Critic Verdict", "")
    critic_verdict_line = _first_nonempty_line(critic_section)
    critic_verdict = "warning"
    lowered_critic = critic_verdict_line.lower()
    if "pass" in lowered_critic or "safe" in lowered_critic:
        critic_verdict = "pass"
    elif "fail" in lowered_critic or "block" in lowered_critic:
        critic_verdict = "fail"

    stage_section = sections.get("Stage Findings", "")
    stage_subsections = _markdown_heading_sections(stage_section)
    stage_findings = {
        stage: _first_nonempty_line(stage_subsections.get(stage, ""))
        for stage in ("Intake", "Evidence", "Review", "Draft", "Integration Discovery")
        if _first_nonempty_line(stage_subsections.get(stage, ""))
    }
    for stage in ("Intake", "Evidence", "Review", "Draft", "Integration Discovery"):
        if stage not in stage_findings:
            direct_stage_body = str(sections.get(stage) or "").strip()
            if direct_stage_body:
                stage_findings[stage] = _first_nonempty_line(direct_stage_body)
    if not stage_findings:
        for stage in ("Intake", "Evidence", "Review", "Draft", "Integration Discovery"):
            stage_body = _extract_named_markdown_section(stage_section, stage)
            if stage_body:
                stage_findings[stage] = _first_nonempty_line(stage_body)

    issues: list[dict[str, Any]] = []
    stage_order = list(stage_findings.keys()) or ["Workspace"]
    for index, risk in enumerate(top_risks, start=1):
        stage_name = stage_order[min(index - 1, len(stage_order) - 1)]
        stage_artifacts = _match_artifacts_to_stage(artifacts, stage_name)
        surface = _surface_from_artifact(stage_artifacts[0]) if stage_artifacts else stage_name
        issues.append(
            {
                "severity": "high" if index <= 2 else "medium",
                "surface": surface,
                "problem": risk,
                "user_impact": stage_findings.get(stage_name) or risk,
                "recommended_fix": fixes[min(index - 1, len(fixes) - 1)] if fixes else "Apply the actor/critic repair described in the review.",
            }
        )

    recommended_changes: list[dict[str, Any]] = []
    for index, fix in enumerate(fixes, start=1):
        related_stage = stage_order[min(index - 1, len(stage_order) - 1)]
        stage_artifacts = _match_artifacts_to_stage(artifacts, related_stage)
        shared_code_path = "templates/workspace.html"
        artifact_context = _artifact_text_context(stage_artifacts[0]) if stage_artifacts else ""
        if "sdk" in fix.lower() or "tool" in fix.lower() or "integration" in fix.lower() or "sdk" in artifact_context:
            shared_code_path = "static/complaint_mcp_sdk.js"
        elif "playwright" in fix.lower():
            shared_code_path = "playwright/tests/complaint-flow.spec.js"
        recommended_changes.append(
            {
                "title": f"UX repair {index}",
                "implementation_notes": fix,
                "shared_code_path": shared_code_path,
                "sdk_considerations": "Keep the shared ComplaintMcpClient and MCP tool workflow visible while applying this repair.",
            }
        )

    broken_controls = [
        {
            "surface": item.get("surface"),
            "control": "Visible CTA or tab in screenshot flow",
            "failure_mode": item.get("problem"),
            "repair": item.get("recommended_fix"),
        }
        for item in issues[: min(3, len(issues))]
    ]

    screenshot_findings = _build_screenshot_findings(
        artifacts=artifacts,
        issues=issues,
        stage_findings=stage_findings,
        top_risks=top_risks,
    )

    optimization_targets = [
        {
            "title": item.get("title"),
            "target_surface": item.get("shared_code_path"),
            "reason": item.get("implementation_notes"),
        }
        for item in recommended_changes[:5]
    ]
    carry_forward_assessment = _build_carry_forward_assessment(
        artifacts=artifacts,
        screenshot_findings=screenshot_findings,
        optimization_targets=optimization_targets,
        stage_findings=stage_findings,
    )

    return {
        "summary": _first_nonempty_line(sections.get("Top Risks", "")) or _first_nonempty_line(review_text),
        "issues": issues,
        "recommended_changes": recommended_changes,
        "broken_controls": broken_controls,
        "workflow_gaps": hidden_paths,
        "playwright_followups": playwright_followups,
        "actor_path_breaks": actor_journey_lines,
        "critic_test_obligations": critic_test_lines or playwright_followups,
        "complaint_journey": {
            "tested_stages": list(stage_findings.keys()),
            "journey_gaps": complaint_journey_lines or hidden_paths,
            "sdk_tool_invocations": mcp_sdk_lines,
            "release_blockers": top_risks[:3],
        },
        "actor_plan": {
            "primary_objective": actor_plan_lines[0] if actor_plan_lines else (fixes[0] if fixes else ""),
            "repair_sequence": actor_plan_lines or implementation_order or fixes[:3],
            "playwright_objectives": playwright_followups[:5],
            "mcp_sdk_expectations": mcp_sdk_lines[:5],
        },
        "critic_review": {
            "verdict": critic_verdict,
            "blocking_findings": top_risks[:5],
            "acceptance_checks": critic_test_lines[:5] or playwright_followups[:5],
        },
        "actor_summary": _first_nonempty_line(sections.get("Actor Journey Findings", "")),
        "critic_summary": critic_verdict_line or _first_nonempty_line(critic_section),
        "stage_findings": stage_findings,
        "complaint_intake_language_fixes": language_lines,
        "screenshot_findings": screenshot_findings,
        "optimization_targets": optimization_targets,
        "carry_forward_assessment": carry_forward_assessment,
        "review_sections": sections,
        "iteration": iteration,
    }


def run_playwright_screenshot_audit(
    *,
    screenshot_dir: str | Path,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    pytest_executable: str | Path | None = None,
    workdir: str | Path | None = None,
) -> dict[str, Any]:
    target_dir = Path(screenshot_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in list(target_dir.glob("*.png")) + list(target_dir.glob("*.json")):
        stale.unlink()

    env = dict(os.environ)
    env["COMPLAINT_UI_SCREENSHOT_DIR"] = str(target_dir)
    env.setdefault("RUN_LLM_TESTS", "1")
    env.setdefault("RUN_NETWORK_TESTS", "1")
    env.setdefault("RUN_HEAVY_TESTS", "1")
    target_text = str(pytest_target or "").strip()
    if target_text.endswith(".js") or "playwright/tests/" in target_text:
        completed = subprocess.run(
            ["npm", "run", "test:e2e", "--", target_text],
            cwd=str(workdir or REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        command = ["npm", "run", "test:e2e", "--", target_text]
    else:
        pytest_cmd = str(pytest_executable or (REPO_ROOT / ".venv" / "bin" / "pytest"))
        completed = subprocess.run(
            [pytest_cmd, "-q", target_text],
            cwd=str(workdir or REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        command = [pytest_cmd, "-q", target_text]

    artifacts = collect_screenshot_artifacts(target_dir)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "screenshot_dir": str(target_dir),
    }


def run_end_to_end_complaint_browser_audit(
    *,
    screenshot_dir: str | Path,
    pytest_executable: str | Path | None = None,
    workdir: str | Path | None = None,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
) -> dict[str, Any]:
    return run_playwright_screenshot_audit(
        screenshot_dir=screenshot_dir,
        pytest_target=pytest_target,
        pytest_executable=pytest_executable,
        workdir=workdir,
    )


def build_ui_ux_review_prompt(
    *,
    iteration: int,
    artifacts: list[dict[str, Any]],
    previous_review: str | None = None,
    notes: str | None = None,
    goals: list[str] | None = None,
) -> str:
    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
    workspace_html = _read_text(REPO_ROOT / "templates" / "workspace.html", limit=14000)
    sdk_source = _read_text(REPO_ROOT / "static" / "complaint_mcp_sdk.js", limit=8000)
    artifact_blocks = []
    for artifact in artifacts:
        lines = [
            f"Surface: {artifact.get('name', 'unknown')}",
            f"URL: {artifact.get('url', '')}",
            f"Title: {artifact.get('title', '')}",
            f"Screenshot path: {artifact.get('screenshot_path', '')}",
            f"Viewport: {json.dumps(artifact.get('viewport', {}), sort_keys=True)}",
            "Visible text excerpt:",
            str(artifact.get("text_excerpt", "")).strip(),
        ]
        if artifact.get("artifact_type") == "complaint_export":
            lines.extend(
                [
                    f"Export artifact type: {artifact.get('artifact_type')}",
                    f"Claim type: {artifact.get('claim_type', '')}",
                    f"Draft strategy: {artifact.get('draft_strategy', '')}",
                    f"Filing shape score: {artifact.get('filing_shape_score', '')}",
                    f"Markdown filename: {artifact.get('markdown_filename', '')}",
                    f"PDF filename: {artifact.get('pdf_filename', '')}",
                    "Exported complaint markdown excerpt:",
                    str(artifact.get("markdown_excerpt", "")).strip(),
                    f"PDF header: {artifact.get('pdf_header', '')}",
                    "Complaint-output-informed UI suggestions:",
                    str(artifact.get("ui_suggestions_excerpt", "")).strip(),
                ]
            )
        if artifact.get("artifact_type") == "ui_readiness_review":
            lines.extend(
                [
                    f"Cached review artifact type: {artifact.get('artifact_type')}",
                    f"Cached UI verdict: {artifact.get('verdict', '')}",
                    f"Cached UI score: {artifact.get('score', '')}",
                    f"Cached critic verdict: {artifact.get('critic_verdict', '')}",
                    f"Cached workflow type: {artifact.get('workflow_type', '')}",
                    "Previously observed screenshot findings:",
                    json.dumps(artifact.get("screenshot_findings", []), indent=2, sort_keys=True),
                    "Previously proposed optimization targets:",
                    json.dumps(artifact.get("optimization_targets", []), indent=2, sort_keys=True),
                    "Previously proposed Playwright follow-ups:",
                    "\n".join(f"- {item}" for item in list(artifact.get("playwright_followups", []))[:6]),
                    "Previously recommended changes:",
                    "\n".join(f"- {item}" for item in list(artifact.get("recommended_changes", []))[:6]),
                    "Cached review excerpt:",
                    str(artifact.get("review_excerpt", "")).strip(),
                ]
            )
        artifact_blocks.append("\n".join(lines))

    prompt_sections = [
        "You are reviewing the complaint-generator MCP workspace and related complaint site surfaces.",
        "Focus on UI/UX problems that would make the site poorly suited for real user complaints.",
        "Prioritize issues around trauma-informed wording, complaint triage clarity, evidence capture usability, navigation coherence, draft confidence, and MCP SDK transparency.",
        "Also check that the complaint generator functionality remains legible as package exports, CLI tools, MCP server tools, and a JavaScript MCP SDK workflow.",
        "Treat this as an actor/critic workflow audit with adversarial pressure-testing: identify where a real user could fail to complete the full complaint journey, where the UI hides the next best step, or where major product capabilities disappear from view.",
        "Explicitly audit visible buttons, links, tabs, and handoff controls. Treat any dead, misleading, duplicated, or context-losing control as a release blocker until proven otherwise.",
        "Use an actor/critic lens: the actor should propose the smallest high-impact UX repair sequence, and the critic should decide whether the dashboard is actually safe to send legal clients through.",
        "Do not treat a workflow as successful unless the final complaint output still looks like a formal pleading and the export/download controls produce artifacts consistent with the selected claim type and draft strategy.",
        "If cached screenshot-driven findings or optimization targets are supplied, treat them as prior unresolved hypotheses that should be confirmed, refined, or explicitly retired with evidence from the current screenshots.",
        f"Iteration: {iteration}",
    ]
    prompt_sections.extend(
        [
            "Workflow goals:",
            "\n".join(f"- {goal}" for goal in resolved_goals),
            "Review notes:",
            resolved_notes,
            "Required capability audit:",
            "\n".join(f"- {capability}" for capability in DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES),
        ]
    )
    if previous_review:
        prompt_sections.extend(
            [
                "Previous review summary:",
                previous_review,
            ]
        )
    prompt_sections.extend(
        [
            "Surface artifacts:",
            "\n\n".join(artifact_blocks) or "No screenshot artifacts were captured.",
            "External interface contract:",
            (
                "Package exports: complaint_generator.ComplaintWorkspaceService, "
                "complaint_generator.start_session, "
                "complaint_generator.submit_intake_answers, "
                "complaint_generator.save_evidence, "
                "complaint_generator.import_gmail_evidence, "
                "complaint_generator.review_case, "
                "complaint_generator.build_mediator_prompt, "
                "complaint_generator.get_workflow_capabilities, "
                "complaint_generator.get_tooling_contract, "
                "complaint_generator.generate_complaint, "
                "complaint_generator.update_draft, "
                "complaint_generator.export_complaint_packet, "
                "complaint_generator.export_complaint_markdown, "
                "complaint_generator.export_complaint_pdf, "
                "complaint_generator.export_complaint_docx, "
                "complaint_generator.analyze_complaint_output, "
                "complaint_generator.get_formal_diagnostics, "
                "complaint_generator.get_filing_provenance, "
                "complaint_generator.get_provider_diagnostics, "
                "complaint_generator.review_generated_exports, "
                "complaint_generator.update_claim_type, "
                "complaint_generator.update_case_synopsis, "
                "complaint_generator.review_ui, "
                "complaint_generator.optimize_ui, "
                "complaint_generator.run_browser_audit, "
                "complaint_generator.handle_jsonrpc_message, "
                "complaint_generator.run_iterative_ui_ux_workflow, "
                "complaint_generator.run_closed_loop_ui_ux_improvement, "
                "complaint_generator.run_end_to_end_complaint_browser_audit, "
                "complaint_generator.create_ui_review_report\n"
                "CLI tools: complaint-generator, complaint-workspace, complaint-generator-workspace, complaint-mcp-server, complaint-workspace import-gmail-evidence, complaint-workspace tooling-contract, complaint-workspace set-claim-type, complaint-workspace update-synopsis, complaint-workspace export-packet, complaint-workspace export-markdown, complaint-workspace export-pdf, complaint-workspace export-docx, complaint-workspace analyze-output, complaint-workspace review-ui, complaint-workspace optimize-ui, complaint-workspace browser-audit\n"
                "MCP server tools: complaint.create_identity, complaint.list_intake_questions, complaint.list_claim_elements, complaint.start_session, complaint.submit_intake, complaint.save_evidence, complaint.import_gmail_evidence, complaint.review_case, complaint.build_mediator_prompt, complaint.get_workflow_capabilities, complaint.get_tooling_contract, complaint.generate_complaint, complaint.update_draft, complaint.export_complaint_packet, complaint.export_complaint_markdown, complaint.export_complaint_pdf, complaint.export_complaint_docx, complaint.analyze_complaint_output, complaint.review_generated_exports, complaint.update_claim_type, complaint.update_case_synopsis, complaint.reset_session, complaint.review_ui, complaint.optimize_ui, complaint.run_browser_audit\n"
                "Browser SDK: window.ComplaintMcpSdk.ComplaintMcpClient with bootstrapWorkspace(), getOrCreateDid(), callTool(), importGmailEvidence(), getToolingContract(), exportComplaintPacket(), exportComplaintMarkdown(), exportComplaintPdf(), exportComplaintDocx(), analyzeComplaintOutput(), reviewGeneratedExports(), updateClaimType(), updateCaseSynopsis(), reviewUiArtifacts(), optimizeUiArtifacts(), and runBrowserAudit()"
            ),
            "Current workspace HTML:",
            workspace_html,
            "Current JavaScript MCP SDK:",
            sdk_source,
            (
                "Return markdown with these sections: `Top Risks`, `High-Impact UX Fixes`, "
                "`Complaint Journey Coverage`, `Hidden Or Missing Feature Paths`, `Stage Findings`, "
                "`Actor Journey Findings`, `Critic Test Obligations`, `MCP/SDK Workflow Improvements`, `Actor Plan`, `Critic Verdict`, `Complaint Intake Language Fixes`, "
                "`Playwright Assertions To Add`, and `Implementation Order`."
            ),
            (
                "Under `Stage Findings`, use explicit subsections named `Intake`, `Evidence`, `Review`, `Draft`, and `Integration Discovery`, "
                "each with concrete UX failures or fixes for that stage."
            ),
            (
                "Under `Actor Journey Findings`, explicitly state whether a user can complete intake, save a shared synopsis for the mediator path, add testimony, upload or attach evidence, review claim support, generate a complaint, and revise the final draft from the shared MCP SDK-driven workspace."
            ),
            (
                "Under `Actor Journey Findings`, explicitly say whether the visible claim type, draft strategy, and exported complaint filing quality remain aligned, "
                "or whether the UI is allowing users to generate the wrong complaint shape without realizing it."
            ),
            (
                "Under `Actor Journey Findings`, explicitly flag any button, tab, link, or MCP invocation path that appears broken, misleading, duplicated, or disconnected from the actual complaint-generation workflow."
            ),
            (
                "Under `Critic Test Obligations`, list the exact Playwright end-to-end checks that should fail if buttons, navigation, shared state, SDK invocations, or stage transitions break."
            ),
            (
                "Under `Playwright Assertions To Add`, include a control audit matrix that names the exact button, link, or tab to click, the expected route or state transition, and the expected visible text confirming success."
            ),
            (
                "If exported complaint markdown or PDF artifacts are present, critique whether the final complaint output is coherent, filing-shaped, and consistent with what the UI promised the user during intake, review, and draft generation."
            ),
            (
                "Explicitly verify whether the generated complaint still presents a recognizable caption, civil action header, jurisdiction or venue section, factual allegations, count headings, prayer for relief, and signature block. "
                "If any of those elements are missing, mislabeled, or generic, treat that as both a complaint-output defect and a UI/UX failure."
            ),
            (
                "If complaint-output artifacts include claim-type alignment data, explicitly judge whether the UI let the selected claim type drift into the wrong complaint heading, wrong count heading, or a generic pleading shape."
            ),
            (
                "If complaint-output-informed UI suggestions are present, use them to propose concrete changes to buttons, validation, warnings, panel hierarchy, and handoff copy that would make the generated complaint stronger before export."
            ),
            (
                "Under `Playwright Assertions To Add`, include assertions that markdown, PDF, and docx downloads succeed, and that the markdown or PDF visibly contains the formal pleading sections the UI promised."
            ),
            (
                "Use the screenshot evidence together with any complaint-output analysis excerpts as a single actor/critic review context: the multimodal router should reason across both when images are available, and the llm_router fallback should still preserve those complaint-output suggestions in the review."
            ),
        ]
    )
    return "\n\n".join(prompt_sections)


def review_screenshot_audit_with_llm_router(
    *,
    screenshot_dir: str | Path,
    iteration: int = 1,
    provider: str | None = None,
    model: str | None = None,
    previous_review: str | None = None,
    notes: str | None = None,
    goals: list[str] | None = None,
    supplemental_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifacts = collect_review_artifacts(screenshot_dir, supplemental_artifacts=supplemental_artifacts)
    prompt = build_ui_ux_review_prompt(
        iteration=iteration,
        artifacts=artifacts,
        previous_review=previous_review,
        notes=notes,
        goals=goals,
    )
    image_paths = _artifact_image_paths(artifacts)
    backend = MultimodalRouterBackend(
        id=f"complaint-ui-ux-review-{iteration}",
        provider=provider,
        model=model,
    )
    try:
        review_text = backend(
            prompt,
            image_paths=image_paths,
            system_prompt=(
                "You are reviewing complaint intake and MCP dashboard screenshots. "
                "Use the images and prompt together to find concrete UI/UX issues."
            ),
        )
    except Exception:
        fallback_backend = LLMRouterBackend(
            id=f"complaint-ui-ux-review-{iteration}-fallback",
            provider=provider,
            model=model,
        )
        review_text = fallback_backend(prompt)
    structured_review = structure_ui_ux_review(
        review_text=review_text,
        artifacts=artifacts,
        iteration=iteration,
    )
    return {
        "iteration": iteration,
        "artifact_count": len(artifacts),
        "review": review_text,
        "artifacts": artifacts,
        "structured_review": structured_review,
        "issues": list(structured_review.get("issues") or []),
        "recommended_changes": list(structured_review.get("recommended_changes") or []),
        "broken_controls": list(structured_review.get("broken_controls") or []),
        "playwright_followups": list(structured_review.get("playwright_followups") or []),
        "stage_findings": dict(structured_review.get("stage_findings") or {}),
        "screenshot_findings": list(structured_review.get("screenshot_findings") or []),
        "optimization_targets": list(structured_review.get("optimization_targets") or []),
        "carry_forward_assessment": dict(structured_review.get("carry_forward_assessment") or {}),
    }


def run_iterative_ui_ux_workflow(
    *,
    screenshot_dir: str | Path,
    iterations: int = 1,
    provider: str | None = None,
    model: str | None = None,
    output_dir: str | Path | None = None,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    notes: str | None = None,
    goals: list[str] | None = None,
    initial_previous_review: str | None = None,
    supplemental_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
    target_output_dir = Path(output_dir or (Path(screenshot_dir) / "reviews"))
    target_output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = target_output_dir / "workflow-progress.json"
    _write_progress_artifact(
        progress_path,
        {
            "status": "initialized",
            "iterations_requested": max(1, iterations),
            "screenshot_dir": str(screenshot_dir),
            "pytest_target": str(pytest_target),
            "provider": str(provider or ""),
            "model": str(model or ""),
        },
    )

    previous_review: str | None = initial_previous_review
    run_reports: list[dict[str, Any]] = []
    latest_structured_review: dict[str, Any] = {}

    for iteration in range(1, max(1, iterations) + 1):
        _write_progress_artifact(
            progress_path,
            {
                "status": "running_playwright_audit",
                "iteration": iteration,
                "output_dir": str(target_output_dir),
            },
        )
        audit = run_playwright_screenshot_audit(
            screenshot_dir=screenshot_dir,
            pytest_target=pytest_target,
        )
        if audit["returncode"] != 0:
            _write_progress_artifact(
                progress_path,
                {
                    "status": "playwright_audit_failed",
                    "iteration": iteration,
                    "returncode": int(audit.get("returncode") or 1),
                },
            )
            raise RuntimeError(
                "Playwright screenshot audit failed.\n"
                f"stdout:\n{audit['stdout']}\n\nstderr:\n{audit['stderr']}"
            )
        if int(audit.get("artifact_count") or 0) <= 0:
            _write_progress_artifact(
                progress_path,
                {
                    "status": "playwright_audit_empty",
                    "iteration": iteration,
                    "returncode": int(audit.get("returncode") or 0),
                },
            )
            raise RuntimeError(
                "Playwright screenshot audit completed without screenshot artifacts.\n"
                f"stdout:\n{audit['stdout']}\n\nstderr:\n{audit['stderr']}"
            )

        _write_progress_artifact(
            progress_path,
            {
                "status": "running_router_review",
                "iteration": iteration,
                "artifact_count": int(audit.get("artifact_count") or 0),
            },
        )
        review = review_screenshot_audit_with_llm_router(
            screenshot_dir=screenshot_dir,
            iteration=iteration,
            provider=provider,
            model=model,
            previous_review=previous_review,
            notes=resolved_notes,
            goals=resolved_goals,
            supplemental_artifacts=supplemental_artifacts,
        )
        markdown_path = target_output_dir / f"iteration-{iteration:02d}-review.md"
        json_path = target_output_dir / f"iteration-{iteration:02d}-review.json"
        markdown_path.write_text(review["review"])
        json_path.write_text(json.dumps(review, indent=2, sort_keys=True))
        _write_progress_artifact(
            progress_path,
            {
                "status": "review_written",
                "iteration": iteration,
                "review_markdown_path": str(markdown_path),
                "review_json_path": str(json_path),
                "artifact_count": int(review.get("artifact_count") or 0),
            },
        )
        previous_review = review["review"]
        latest_structured_review = dict(review.get("structured_review") or {})
        run_reports.append(
            {
                "iteration": iteration,
                "audit": audit,
                "artifact_count": review["artifact_count"],
                "review_excerpt": str(review["review"] or "")[:600],
                "review_markdown_path": str(markdown_path),
                "review_json_path": str(json_path),
                "issues_count": len(list(review.get("issues") or [])),
                "broken_controls_count": len(list(review.get("broken_controls") or [])),
                "optimization_target_count": len(list(review.get("optimization_targets") or [])),
                "carry_forward_summary": str((review.get("carry_forward_assessment") or {}).get("summary") or "").strip(),
            }
        )

    _write_progress_artifact(
        progress_path,
        {
            "status": "completed",
            "iterations_completed": len(run_reports),
            "latest_review_json_path": str(target_output_dir / f"iteration-{len(run_reports):02d}-review.json") if run_reports else "",
        },
    )
    return {
        "iterations": len(run_reports),
        "screenshot_dir": str(screenshot_dir),
        "output_dir": str(target_output_dir),
        "latest_review": previous_review,
        "review": latest_structured_review,
        "issues": list(latest_structured_review.get("issues") or []),
        "recommended_changes": list(latest_structured_review.get("recommended_changes") or []),
        "broken_controls": list(latest_structured_review.get("broken_controls") or []),
        "playwright_followups": list(latest_structured_review.get("playwright_followups") or []),
        "stage_findings": dict(latest_structured_review.get("stage_findings") or {}),
        "screenshot_findings": list(latest_structured_review.get("screenshot_findings") or []),
        "optimization_targets": list(latest_structured_review.get("optimization_targets") or []),
        "carry_forward_assessment": dict(latest_structured_review.get("carry_forward_assessment") or {}),
        "latest_review_markdown_path": str(target_output_dir / f"iteration-{len(run_reports):02d}-review.md") if run_reports else None,
        "latest_review_json_path": str(target_output_dir / f"iteration-{len(run_reports):02d}-review.json") if run_reports else None,
        "runs": run_reports,
    }


def run_closed_loop_ui_ux_improvement(
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str = DEFAULT_SCREENSHOT_TEST,
    max_rounds: int = 2,
    review_iterations: int = 1,
    provider: str | None = None,
    model: str | None = None,
    method: str = DEFAULT_OPTIMIZER_METHOD,
    priority: int = DEFAULT_OPTIMIZER_PRIORITY,
    notes: str | None = None,
    goals: list[str] | None = None,
    constraints: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    supplemental_artifacts: list[dict[str, Any]] | None = None,
    llm_router: Any = None,
    patch_optimizer: Any = None,
    optimizer: Any = None,
    agent_id: str = "complaint-ui-ux-optimizer",
    components: dict[str, Any] | None = None,
    stop_when_review_stable: bool = True,
    break_on_no_changes: bool = True,
) -> dict[str, Any]:
    from adversarial_harness import Optimizer

    resolved_goals = _resolve_review_goals(goals)
    resolved_notes = _resolve_review_notes(notes)
    resolved_optimizer = optimizer or Optimizer()
    resolved_metadata = dict(metadata or {})
    if supplemental_artifacts:
        resolved_metadata["supplemental_artifacts"] = [dict(item) for item in supplemental_artifacts if isinstance(item, dict)]
    return resolved_optimizer.run_agentic_ui_ux_feedback_loop(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target=pytest_target,
        max_rounds=max_rounds,
        review_iterations=review_iterations,
        provider=provider,
        model=model,
        method=method,
        priority=priority,
        notes=resolved_notes,
        goals=resolved_goals,
        constraints=constraints,
        metadata=resolved_metadata or None,
        llm_router=llm_router,
        optimizer=patch_optimizer,
        agent_id=agent_id,
        components=components,
        stop_when_review_stable=stop_when_review_stable,
        break_on_no_changes=break_on_no_changes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complaint-generator screenshot audit and llm_router UX review workflow.",
    )
    parser.add_argument("--screenshot-dir", default=str(REPO_ROOT / "artifacts" / "ui-audit" / "screenshots"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "ui-audit" / "reviews"))
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--pytest-target", default=DEFAULT_SCREENSHOT_TEST)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--goal", dest="goals", action="append", default=None)
    parser.add_argument("--method", default=DEFAULT_OPTIMIZER_METHOD)
    parser.add_argument("--priority", type=int, default=DEFAULT_OPTIMIZER_PRIORITY)
    parser.add_argument("--max-rounds", type=int, default=0)
    args = parser.parse_args(argv)

    if args.max_rounds > 0:
        result = run_closed_loop_ui_ux_improvement(
            screenshot_dir=args.screenshot_dir,
            output_dir=args.output_dir,
            pytest_target=args.pytest_target,
            max_rounds=args.max_rounds,
            review_iterations=args.iterations,
            provider=args.provider,
            model=args.model,
            notes=args.notes,
            goals=args.goals,
            method=args.method,
            priority=args.priority,
        )
    else:
        result = run_iterative_ui_ux_workflow(
            screenshot_dir=args.screenshot_dir,
            output_dir=args.output_dir,
            iterations=args.iterations,
            provider=args.provider,
            model=args.model,
            pytest_target=args.pytest_target,
            notes=args.notes,
            goals=args.goals,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_SCREENSHOT_TEST",
    "DEFAULT_COMPLAINT_WORKFLOW_CAPABILITIES",
    "DEFAULT_OPTIMIZER_PRIORITY",
    "build_ui_ux_review_prompt",
    "collect_screenshot_artifacts",
    "DEFAULT_UI_UX_REVIEW_GOALS",
    "DEFAULT_UI_UX_REVIEW_NOTES",
    "review_screenshot_audit_with_llm_router",
    "run_end_to_end_complaint_browser_audit",
    "run_closed_loop_ui_ux_improvement",
    "run_iterative_ui_ux_workflow",
    "run_playwright_screenshot_audit",
    "structure_ui_ux_review",
    "main",
]
