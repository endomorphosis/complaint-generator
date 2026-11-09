"""Fallback optimizer components delegated from Optimizer."""

from __future__ import annotations

from adversarial_harness.optimizer import (
    Path,
    SimpleNamespace,
    difflib,
    os,
    re,
    shutil,
    subprocess,
)


def _fallback_agentic_optimizer_components() -> Dict[str, Any]:
    class FallbackOptimizationTask:
        def __init__(
            self,
            task_id: str,
            description: str,
            target_files: List[Path],
            method: Any,
            priority: int,
            constraints: Dict[str, Any],
            metadata: Dict[str, Any],
        ) -> None:
            self.task_id = task_id
            self.description = description
            self.target_files = target_files
            self.method = method
            self.priority = priority
            self.constraints = constraints
            self.metadata = metadata

    class FallbackOptimizerResult:
        def __init__(self, *, success: bool, status: str, patch_path: str, metadata: Dict[str, Any]) -> None:
            self.success = success
            self.status = status
            self.patch_path = patch_path
            self.patch_cid = ""
            self.metadata = metadata

    class FallbackLocalOptimizer:
        def __init__(self, agent_id: str, llm_router: Any = None) -> None:
            self.agent_id = agent_id
            self.llm_router = llm_router
            self._last_generation_diagnostics: List[Dict[str, Any]] = []

        def optimize(self, task: Any) -> Any:
            constraints = dict(getattr(task, "constraints", {}) or {})
            metadata = dict(getattr(task, "metadata", {}) or {})
            output_dir = Path(str(constraints.get("review_output_dir") or constraints.get("output_dir") or "."))
            output_dir.mkdir(parents=True, exist_ok=True)
            patch_path = output_dir / "fallback-optimizer-plan.md"
            project_root = Path.cwd().resolve()

            actor_critic_review = dict(metadata.get("actor_critic_review") or {})
            complaint_output_feedback = dict(metadata.get("complaint_output_feedback") or {})
            release_gate = dict(metadata.get("complaint_output_release_gate") or {})
            target_files = [Path(path) for path in list(getattr(task, "target_files", []) or [])[:5]]
            changed_files = [str(path) for path in target_files]

            recommendations = [
                str(item).strip()
                for item in (
                    list(actor_critic_review.get("top_risks") or [])
                    + list(actor_critic_review.get("high_impact_fixes") or [])
                    + list(actor_critic_review.get("playwright_followups") or [])
                )
                if str(item).strip()
            ][:10]
            if not recommendations:
                recommendations = [
                    "Promote the highest-value primary action for the current complaint stage.",
                    "Keep complaint generation, export, and next-step guidance visible together.",
                    "Add or strengthen Playwright assertions for the unresolved screenshot findings.",
                ]

            report_summary = dict(metadata.get("report_summary") or {})
            prioritized_patch_briefs = list(report_summary.get("prioritized_patch_briefs") or [])
            selected_patch_briefs = [
                dict(item)
                for item in list(report_summary.get("selected_patch_briefs") or [])
                if isinstance(item, dict)
            ] or [dict(item) for item in prioritized_patch_briefs[:3] if isinstance(item, dict)]
            top_patch_brief = dict(selected_patch_briefs[0]) if selected_patch_briefs else {}
            recommendation_coverage = dict(report_summary.get("recommendation_coverage") or {})
            if not recommendation_coverage:
                recommendation_coverage = {
                    "total_patch_briefs": len(prioritized_patch_briefs),
                    "selected_patch_briefs_count": len(selected_patch_briefs),
                    "uncovered_patch_briefs_count": max(0, len(prioritized_patch_briefs) - len(selected_patch_briefs)),
                    "selected_patch_brief_titles": [
                        str((item or {}).get("title") or "").strip()
                        for item in selected_patch_briefs
                        if str((item or {}).get("title") or "").strip()
                    ],
                    "selected_target_files": [str(path) for path in changed_files],
                }
            for brief in selected_patch_briefs:
                title = str(brief.get("title") or "").strip()
                problem = str(brief.get("problem") or "").strip()
                recommended_action = str(brief.get("recommended_action") or "").strip()
                for candidate in (title, problem, recommended_action):
                    if candidate and candidate not in recommendations:
                        recommendations.append(candidate)
            recommendations = recommendations[:12]

            def _absolute_path(path: Path) -> Path:
                return path if path.is_absolute() else (project_root / path).resolve()

            tracked_files = {
                str(path): _absolute_path(path)
                for path in target_files
                if _absolute_path(path).is_file()
            }
            original_text_by_file = {
                rel_path: absolute_path.read_text(encoding="utf-8")
                for rel_path, absolute_path in tracked_files.items()
            }

            def _build_patch_text(updated_files: List[str]) -> str:
                chunks: List[str] = []
                for rel_path in updated_files:
                    absolute_path = tracked_files.get(rel_path)
                    if absolute_path is None:
                        continue
                    before_text = original_text_by_file.get(rel_path, "")
                    after_text = absolute_path.read_text(encoding="utf-8")
                    if before_text == after_text:
                        continue
                    chunks.append(
                        "".join(
                            difflib.unified_diff(
                                before_text.splitlines(keepends=True),
                                after_text.splitlines(keepends=True),
                                fromfile=f"a/{rel_path}",
                                tofile=f"b/{rel_path}",
                            )
                        )
                    )
                return "".join(chunks)

            def _summarize_selected_patch_brief_coverage(updated_files: List[str]) -> Dict[str, Any]:
                normalized_updated_files = {str(path).strip() for path in list(updated_files or []) if str(path).strip()}
                selected_titles = [
                    str((item or {}).get("title") or "").strip()
                    for item in selected_patch_briefs
                    if str((item or {}).get("title") or "").strip()
                ]
                covered_titles: List[str] = []
                uncovered_titles: List[str] = []
                for brief in selected_patch_briefs:
                    title = str((brief or {}).get("title") or "").strip()
                    if not title:
                        continue
                    brief_targets = {
                        str(path).strip()
                        for path in list((brief or {}).get("target_files") or [])
                        if str(path).strip()
                    }
                    if brief_targets:
                        matched = bool(brief_targets & normalized_updated_files)
                    else:
                        matched = bool(normalized_updated_files) and title == str((top_patch_brief or {}).get("title") or "").strip()
                    if matched:
                        covered_titles.append(title)
                    else:
                        uncovered_titles.append(title)
                total_selected = len(selected_titles)
                return {
                    "selected_patch_brief_titles": selected_titles,
                    "covered_patch_brief_titles": covered_titles,
                    "uncovered_selected_patch_brief_titles": uncovered_titles,
                    "selected_patch_brief_coverage_ratio": (
                        float(len(covered_titles)) / float(total_selected)
                        if total_selected
                        else 0.0
                    ),
                }

            def _restore_suspicious_file_outputs(command_status: str) -> List[Dict[str, Any]]:
                rollback_diagnostics: List[Dict[str, Any]] = []
                for rel_path, absolute_path in tracked_files.items():
                    before_text = original_text_by_file.get(rel_path, "")
                    after_text = absolute_path.read_text(encoding="utf-8")
                    if before_text == after_text:
                        continue
                    suspicious_empty = bool(before_text.strip()) and not bool(after_text.strip())
                    suspicious_truncation = (
                        len(before_text.strip()) >= 1000
                        and len(after_text.strip()) > 0
                        and len(after_text.strip()) < max(200, int(len(before_text.strip()) * 0.1))
                    )
                    if not suspicious_empty and not suspicious_truncation:
                        continue
                    absolute_path.write_text(before_text, encoding="utf-8")
                    rollback_diagnostics.append(
                        {
                            "backend": "codex_cli_fallback_optimizer",
                            "status": "rolled_back_suspicious_output",
                            "reason": (
                                "Codex fallback edit left a tracked file empty."
                                if suspicious_empty
                                else "Codex fallback edit truncated a tracked file implausibly."
                            ),
                            "command_status": command_status,
                            "file": rel_path,
                        }
                    )
                return rollback_diagnostics

            def _attempt_codex_autopatch() -> tuple[List[str], str | None, List[Dict[str, Any]]]:
                diagnostics: List[Dict[str, Any]] = []
                if not tracked_files:
                    diagnostics.append(
                        {
                            "backend": "codex_cli_fallback_optimizer",
                            "status": "skipped",
                            "reason": "No existing target files were available for bounded Codex edits.",
                        }
                    )
                    return [], None, diagnostics
                codex_bin = shutil.which("codex")
                if not codex_bin:
                    diagnostics.append(
                        {
                            "backend": "codex_cli_fallback_optimizer",
                            "status": "skipped",
                            "reason": "codex CLI is not installed.",
                        }
                    )
                    return [], None, diagnostics

                prompt_lines = [
                    "You are repairing the complaint-generator UI/UX workflow.",
                    "Make minimal, concrete edits in the listed target files only.",
                    "Do not modify files outside this set.",
                    "Prefer the smallest safe change that improves gating clarity, complaint formality, or end-to-end dashboard flow.",
                    "",
                    f"Task ID: {getattr(task, 'task_id', '')}",
                    "Target files:",
                    *[f"- {path}" for path in tracked_files.keys()],
                    "",
                    "Top recommendations:",
                    *[f"- {item}" for item in recommendations[:6]],
                ]
                if selected_patch_briefs:
                    prompt_lines.extend(
                        [
                            "",
                            "Selected patch briefs:",
                        ]
                    )
                    for index, brief in enumerate(selected_patch_briefs, start=1):
                        validation_checks = [
                            str(item).strip()
                            for item in list(brief.get("validation_checks") or [])
                            if str(item).strip()
                        ][:3]
                        prompt_lines.extend(
                            [
                                f"- Brief {index}: {str(brief.get('title') or '').strip()}",
                                f"  Surface: {str(brief.get('surface') or '').strip()}",
                                f"  Problem: {str(brief.get('problem') or '').strip()}",
                                f"  Recommended action: {str(brief.get('recommended_action') or '').strip()}",
                            ]
                        )
                        if validation_checks:
                            prompt_lines.append(f"  Validation: {' | '.join(validation_checks)}")
                elif top_patch_brief:
                    prompt_lines.extend(
                        [
                            "",
                            "Top patch brief:",
                            f"- Title: {str(top_patch_brief.get('title') or '').strip()}",
                            f"- Surface: {str(top_patch_brief.get('surface') or '').strip()}",
                            f"- Problem: {str(top_patch_brief.get('problem') or '').strip()}",
                            f"- Recommended action: {str(top_patch_brief.get('recommended_action') or '').strip()}",
                        ]
                    )
                if recommendation_coverage:
                    prompt_lines.extend(
                        [
                            "",
                            "Recommendation coverage target:",
                            f"- Total briefs identified: {int(recommendation_coverage.get('total_patch_briefs') or 0)}",
                            f"- Briefs selected for this pass: {int(recommendation_coverage.get('selected_patch_briefs_count') or 0)}",
                            f"- Briefs still uncovered after this pass: {int(recommendation_coverage.get('uncovered_patch_briefs_count') or 0)}",
                        ]
                    )
                prompt_lines.extend(
                    [
                        "",
                        "Important constraints:",
                        "- Preserve package, CLI, MCP, and browser SDK parity.",
                        "- Cover as many selected patch briefs as safely possible in this pass, starting from Brief 1.",
                        "- Keep release-gate and complaint-output warnings visible when drafting/export remains unsafe.",
                        "- If you touch tests, keep them focused on the workflow you changed.",
                        "- End by summarizing the concrete edits you made.",
                    ]
                )
                prompt = "\n".join(prompt_lines)
                last_message_path = output_dir / "fallback-codex-last-message.txt"
                command = [
                    codex_bin,
                    "exec",
                    "--ephemeral",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--skip-git-repo-check",
                    "-C",
                    str(project_root),
                    "-m",
                    "gpt-5.3-codex",
                    "-o",
                    str(last_message_path),
                    prompt,
                ]
                timeout_seconds = 90
                timeout_override = str(os.getenv("COMPLAINT_GENERATOR_UI_UX_FALLBACK_CODEX_TIMEOUT_SECONDS", "") or "").strip()
                if timeout_override:
                    try:
                        timeout_seconds = max(15, int(float(timeout_override)))
                    except Exception:
                        timeout_seconds = 90
                try:
                    completed = subprocess.run(
                        command,
                        cwd=str(project_root),
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    diagnostics.extend(_restore_suspicious_file_outputs("timed_out"))
                    diagnostics.append(
                        {
                            "backend": "codex_cli_fallback_optimizer",
                            "status": "timed_out",
                            "reason": f"codex exec timed out after {timeout_seconds}s",
                            "timeout_seconds": timeout_seconds,
                            "stdout_excerpt": str(exc.stdout or "").strip()[:500],
                            "stderr_excerpt": str(exc.stderr or "").strip()[:500],
                        }
                    )
                    return [], None, diagnostics
                except Exception as exc:
                    diagnostics.extend(_restore_suspicious_file_outputs("failed"))
                    diagnostics.append(
                        {
                            "backend": "codex_cli_fallback_optimizer",
                            "status": "failed",
                            "reason": str(exc),
                        }
                    )
                    return [], None, diagnostics

                diagnostics.append(
                    {
                        "backend": "codex_cli_fallback_optimizer",
                        "status": "ok" if completed.returncode == 0 else "nonzero_exit",
                        "returncode": int(completed.returncode),
                        "stdout_excerpt": str(completed.stdout or "").strip()[:500],
                        "stderr_excerpt": str(completed.stderr or "").strip()[:500],
                        "last_message_path": str(last_message_path),
                    }
                )
                diagnostics.extend(_restore_suspicious_file_outputs(
                    "ok" if completed.returncode == 0 else "nonzero_exit"
                ))

                updated_files = [
                    rel_path
                    for rel_path, absolute_path in tracked_files.items()
                    if absolute_path.read_text(encoding="utf-8") != original_text_by_file.get(rel_path, "")
                ]
                if not updated_files:
                    return [], None, diagnostics

                codex_patch_path = output_dir / "fallback-codex-autopatch.patch"
                patch_text = _build_patch_text(updated_files)
                codex_patch_path.write_text(patch_text, encoding="utf-8")
                return updated_files, str(codex_patch_path), diagnostics

            def _attempt_deterministic_surface_autopatch() -> tuple[List[str], str | None, List[Dict[str, Any]]]:
                diagnostics: List[Dict[str, Any]] = []
                def _selected_briefs_for(rel_path: str) -> List[Dict[str, Any]]:
                    return [
                        dict(brief)
                        for brief in selected_patch_briefs
                        if rel_path in [str(path).strip() for path in list((brief or {}).get("target_files") or []) if str(path).strip()]
                    ]

                updated_files: List[str] = []

                def _apply_workspace_patch() -> None:
                    workspace_rel_path = "templates/workspace.html"
                    workspace_path = tracked_files.get(workspace_rel_path)
                    if workspace_path is None:
                        return
                    selected_workspace_briefs = _selected_briefs_for(workspace_rel_path)
                    if not selected_workspace_briefs:
                        return

                    updated_text = workspace_path.read_text(encoding="utf-8")
                    original_text = updated_text
                    replacements = [
                    (
                        "<h3>Canonical filing verdict</h3>",
                        "<h3>Canonical filing verdict bar</h3>",
                    ),
                    (
                        "<p class=\"muted\">Pinned filing verdict for Review and Draft. One reason source drives both tabs.</p>",
                        "<p class=\"muted\">Pinned filing verdict for Review, Draft, and Export. One reason source keeps BLOCKED, NEEDS CORROBORATION, and READY aligned across the workflow.</p>",
                    ),
                    (
                        "<p class=\"muted\" id=\"unsupported-thin-blocker-summary\">Generate, export, and download stay blocked until the confidence gate is grounded.</p>",
                        "<p class=\"muted\" id=\"unsupported-thin-blocker-summary\">Generate, export, and download stay blocked until grounded evidence outweighs thin and unsupported elements.</p>",
                    ),
                    (
                        "<span class=\"chip\">grounded: 0</span>",
                        "<span class=\"chip\">grounded evidence: 0</span>",
                    ),
                    (
                        "<span class=\"chip\">thin: 0</span>",
                        "<span class=\"chip\">thin evidence: 0</span>",
                    ),
                    (
                        "<span class=\"chip\">unsupported: 0</span>",
                        "<span class=\"chip\">unsupported elements: 0</span>",
                    ),
                    (
                        "<strong>Current goal</strong>",
                        "<strong>Coverage</strong>",
                    ),
                    (
                        "<strong>Biggest blocker</strong>",
                        "<strong>Corroboration</strong>",
                    ),
                    (
                        "<strong>Safest next move</strong>",
                        "<strong>Filing Gate</strong>",
                    ),
                    (
                        "<strong>Grounded elements</strong>",
                        "<strong>Coverage</strong>",
                    ),
                    (
                        "<strong>Thin elements</strong>",
                        "<strong>Corroboration</strong>",
                    ),
                    (
                        "<strong>Unsupported elements</strong>",
                        "<strong>Filing Gate</strong>",
                    ),
                    (
                        "Fix Intake Names",
                        "Fix Intake",
                    ),
                    (
                        "Fix Caption",
                        "Fix Draft",
                    ),
                    ]
                    for before_text, after_text in replacements:
                        if before_text in updated_text and after_text not in updated_text:
                            updated_text = updated_text.replace(before_text, after_text, 1)

                    blocker_anchor = "<div class=\"list\" id=\"unsupported-thin-blocker-reasons\">"
                    blocker_note = (
                    "                                <div class=\"soft-note\" id=\"unsupported-thin-blocker-coverage-note\">"
                    "Confidence stays blocked until unsupported elements are routed back to Review or Evidence instead of being hidden behind export or download actions."
                    "</div>\n"
                    )
                    if "id=\"unsupported-thin-blocker-coverage-note\"" not in updated_text and blocker_anchor in updated_text:
                        updated_text = updated_text.replace(blocker_anchor, blocker_note + "                                " + blocker_anchor, 1)

                    repair_focus_anchor = "id=\"optimizer-repair-focus-note\">"
                    repair_focus_summary = " | ".join(
                        [
                            str((brief or {}).get("title") or "").strip()
                            + (
                                f": {str((brief or {}).get('recommended_action') or '').strip()}"
                                if str((brief or {}).get("recommended_action") or "").strip()
                                else ""
                            )
                            for brief in selected_workspace_briefs[:3]
                            if str((brief or {}).get("title") or "").strip()
                        ]
                    ).strip()
                    if repair_focus_summary:
                        updated_focus_note = (
                            "Adversarial optimizer repair focus: " + repair_focus_summary
                        )
                        if repair_focus_anchor in updated_text:
                            updated_text = re.sub(
                                r'(id="optimizer-repair-focus-note">)(.*?)(</div>)',
                                lambda match: match.group(1) + updated_focus_note + match.group(3),
                                updated_text,
                                count=1,
                                flags=re.DOTALL,
                            )
                        else:
                            repair_focus_insert_anchor = (
                                "                            <div class=\"tool-card canonical-release-gate\" id=\"unsupported-thin-blocker-panel\">"
                            )
                            repair_focus_block = (
                                "                            <div class=\"soft-note\" id=\"optimizer-repair-focus-note\">"
                                + updated_focus_note
                                + "</div>\n"
                            )
                            if repair_focus_insert_anchor in updated_text:
                                updated_text = updated_text.replace(
                                    repair_focus_insert_anchor,
                                    repair_focus_block + repair_focus_insert_anchor,
                                    1,
                                )

                    confidence_anchor = "<div class=\"status draft-preview-shell\"><pre id=\"draft-release-gate-summary\">Verdict: BLOCKED"
                    confidence_block = (
                    "                                <div class=\"confidence-strip\" id=\"draft-confidence-card\">\n"
                    "                                    <div class=\"confidence-card\">\n"
                    "                                        <strong>Grounded</strong>\n"
                    "                                        <span id=\"draft-confidence-grounded\">0 elements are backed by mixed or documentary proof.</span>\n"
                    "                                    </div>\n"
                    "                                    <div class=\"confidence-card\">\n"
                    "                                        <strong>Thin</strong>\n"
                    "                                        <span id=\"draft-confidence-thin\">0 elements still need corroboration before export confidence should rise.</span>\n"
                    "                                    </div>\n"
                    "                                    <div class=\"confidence-card\">\n"
                    "                                        <strong>Unsupported</strong>\n"
                    "                                        <span id=\"draft-confidence-unsupported\">0 elements still need direct targeted proof before filing confidence should rise.</span>\n"
                    "                                    </div>\n"
                    "                                </div>\n"
                    )
                    if "id=\"draft-confidence-card\"" not in updated_text and confidence_anchor in updated_text:
                        updated_text = updated_text.replace(confidence_anchor, confidence_block + confidence_anchor, 1)

                    event_anchor = (
                    "        document.getElementById('draft-review-before-export-button').addEventListener('click', () => jumpToStage('review', '#support-grid', 'Opened Review so support and release-gate blockers can be checked before export.'));\n"
                    "        document.getElementById('draft-evidence-before-export-button').addEventListener('click', () => jumpToStage('evidence', '#evidence-title', 'Opened Evidence so the record can be strengthened before export.'));\n"
                    )
                    event_block = (
                    event_anchor
                    + "        document.getElementById('unsupported-thin-go-evidence-button').addEventListener('click', () => jumpToStage('evidence', '#evidence-title', 'Opened Evidence from the unsupported-elements blocker so the record can be strengthened before export or download.'));\n"
                    + "        document.getElementById('unsupported-thin-go-review-button').addEventListener('click', () => jumpToStage('review', '#support-grid', 'Opened Review from the unsupported-elements blocker so the filing verdict can be checked before export or download.'));\n"
                    + "        document.getElementById('draft-fix-intake-names-button').addEventListener('click', () => jumpToStage('intake', '#intake-party_name', 'Opened Intake so placeholder party names can be fixed before export.'));\n"
                    + "        document.getElementById('draft-fix-caption-button').addEventListener('click', () => jumpToStage('draft', '#draft-title', 'Focused the draft caption so the filing title can be fixed before export.'));\n"
                    )
                    if "unsupported-thin-go-evidence-button" not in updated_text and event_anchor in updated_text:
                        updated_text = updated_text.replace(event_anchor, event_block, 1)

                    if updated_text != original_text:
                        workspace_path.write_text(updated_text, encoding="utf-8")
                        updated_files.append(workspace_rel_path)

                def _apply_app_shell_patch() -> None:
                    shell_rel_path = "static/complaint_app_shell.js"
                    shell_path = tracked_files.get(shell_rel_path)
                    if shell_path is None:
                        return
                    if not _selected_briefs_for(shell_rel_path):
                        return
                    updated_text = shell_path.read_text(encoding="utf-8")
                    original_text = updated_text
                    if "Use the shared release gate in Workspace before trusting packet exports or downloads." not in updated_text:
                        anchor = (
                            "'<div class=\"cg-app-shell__phase-note\">Keep draft generation, packet export, and release-gate next-step guidance visible together before downloading complaint files.</div>',\n"
                        )
                        addition = (
                            anchor
                            + "            '<div class=\"cg-app-shell__phase-note\">Use the shared release gate in Workspace before trusting packet exports or downloads.</div>',\n"
                        )
                        if anchor in updated_text:
                            updated_text = updated_text.replace(anchor, addition, 1)
                    if "Open Workspace Draft Gate" not in updated_text:
                        updated_text = updated_text.replace(
                            "buildGatedLink('cg-app-shell__draft-step', '2. Export + review packet', buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }), draftFlowEnabled, draftFlowReason),",
                            "buildGatedLink('cg-app-shell__draft-step', '2. Open Workspace Draft Gate', buildShellSurfaceUrl('/workspace', context, { target_tab: 'draft' }), draftFlowEnabled, draftFlowReason),",
                            1,
                        )
                    if updated_text != original_text:
                        shell_path.write_text(updated_text, encoding="utf-8")
                        updated_files.append(shell_rel_path)

                def _apply_sdk_patch() -> None:
                    sdk_rel_path = "static/complaint_mcp_sdk.js"
                    sdk_path = tracked_files.get(sdk_rel_path)
                    if sdk_path is None:
                        return
                    if not _selected_briefs_for(sdk_rel_path):
                        return
                    updated_text = sdk_path.read_text(encoding="utf-8")
                    original_text = updated_text
                    ledger_anchor = (
                        "    getToolCallLedger() {\n"
                        "        if (typeof localStorage === 'undefined') {\n"
                        "            return [];\n"
                        "        }\n"
                        "        try {\n"
                        "            const raw = localStorage.getItem(this.toolCallLedgerStorageKey);\n"
                        "            const parsed = raw ? JSON.parse(raw) : [];\n"
                        "            return Array.isArray(parsed) ? parsed : [];\n"
                        "        } catch (error) {\n"
                        "            return [];\n"
                        "        }\n"
                        "    }\n"
                    )
                    ledger_block = (
                        ledger_anchor
                        + "\n"
                        + "    getToolImpactSummary() {\n"
                        + "        const ledger = this.getToolCallLedger();\n"
                        + "        const latest = ledger[0] || null;\n"
                        + "        const successCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'success').length;\n"
                        + "        const errorCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'error').length;\n"
                        + "        return {\n"
                        + "            total_calls: ledger.length,\n"
                        + "            success_count: successCount,\n"
                        + "            error_count: errorCount,\n"
                        + "            latest_tool_name: latest ? String(latest.tool_name || '').trim() : '',\n"
                        + "            latest_status: latest ? String(latest.status || '').trim() : '',\n"
                        + "            latest_finished_at: latest ? String(latest.finished_at || '').trim() : '',\n"
                        + "        };\n"
                        + "    }\n"
                        + "\n"
                        + "    async getWorkflowOperationSnapshot(userId) {\n"
                        + "        const [releaseGate, workflowCapabilities, toolingContract] = await Promise.all([\n"
                        + "            this.getCanonicalReleaseGate(userId),\n"
                        + "            this.getWorkflowCapabilities(userId),\n"
                        + "            this.getToolingContract(userId),\n"
                        + "        ]);\n"
                        + "        return {\n"
                        + "            tool_impact_summary: this.getToolImpactSummary(),\n"
                        + "            canonical_release_gate: releaseGate,\n"
                        + "            workflow_capabilities: workflowCapabilities,\n"
                        + "            tooling_contract: toolingContract,\n"
                        + "        };\n"
                        + "    }\n"
                    )
                    if "getToolImpactSummary()" not in updated_text and ledger_anchor in updated_text:
                        updated_text = updated_text.replace(ledger_anchor, ledger_block, 1)
                    if updated_text != original_text:
                        sdk_path.write_text(updated_text, encoding="utf-8")
                        updated_files.append(sdk_rel_path)

                def _apply_playwright_spec_patch() -> None:
                    spec_rel_path = "playwright/tests/complaint-flow.spec.js"
                    spec_path = tracked_files.get(spec_rel_path)
                    if spec_path is None:
                        return
                    if not _selected_briefs_for(spec_rel_path):
                        return
                    updated_text = spec_path.read_text(encoding="utf-8")
                    original_text = updated_text
                    anchor = "    await expect(page.locator('#ux-review-stage-findings')).toContainText(/Complaint-output suggestion carried into optimization/i);\n"
                    assertion_block = (
                        anchor
                        + "    await expect(page.locator('#ux-review-scorecard')).toContainText(/3\\/3 selected repairs/i);\n"
                        + "    await expect(page.locator('#ux-review-scorecard')).toContainText(/coverage 100%/i);\n"
                        + "    await expect(page.locator('#ux-review-runs')).toContainText(/UX repair 1/i);\n"
                    )
                    if anchor in updated_text and "3\\/3 selected repairs" not in updated_text:
                        updated_text = updated_text.replace(anchor, assertion_block, 1)
                    if updated_text != original_text:
                        spec_path.write_text(updated_text, encoding="utf-8")
                        updated_files.append(spec_rel_path)

                _apply_workspace_patch()
                _apply_app_shell_patch()
                _apply_sdk_patch()
                _apply_playwright_spec_patch()

                if not updated_files:
                    diagnostics.append(
                        {
                            "backend": "deterministic_surface_fallback_optimizer",
                            "status": "no_changes",
                            "reason": "The bounded deterministic surface repairs were already present or no selected target files matched known deterministic patchers.",
                        }
                    )
                    return [], None, diagnostics

                patch_path = output_dir / "fallback-deterministic-surfaces.patch"
                patch_path.write_text(_build_patch_text(updated_files), encoding="utf-8")
                diagnostics.append(
                    {
                        "backend": "deterministic_surface_fallback_optimizer",
                        "status": "applied",
                        "changed_files": list(updated_files),
                        "patch_path": str(patch_path),
                    }
                )
                return list(updated_files), str(patch_path), diagnostics

            updated_files, codex_patch_path, codex_diagnostics = _attempt_codex_autopatch()
            if updated_files:
                patch_brief_coverage = _summarize_selected_patch_brief_coverage(updated_files)
                self._last_generation_diagnostics = codex_diagnostics
                return FallbackOptimizerResult(
                    success=True,
                    status="applied",
                    patch_path=str(codex_patch_path or ""),
                    metadata={
                        "changed_files": updated_files,
                        "recommendations": recommendations,
                        "optimizer_backend": "codex_cli_fallback_optimizer",
                        "selected_patch_briefs": selected_patch_briefs,
                        "recommendation_coverage": recommendation_coverage,
                        **patch_brief_coverage,
                    },
                )

            deterministic_files, deterministic_patch_path, deterministic_diagnostics = _attempt_deterministic_surface_autopatch()
            if deterministic_files:
                patch_brief_coverage = _summarize_selected_patch_brief_coverage(deterministic_files)
                self._last_generation_diagnostics = codex_diagnostics + deterministic_diagnostics
                return FallbackOptimizerResult(
                    success=True,
                    status="applied",
                    patch_path=str(deterministic_patch_path or ""),
                    metadata={
                        "changed_files": deterministic_files,
                        "recommendations": recommendations,
                        "optimizer_backend": "deterministic_surface_fallback_optimizer",
                        "selected_patch_briefs": selected_patch_briefs,
                        "recommendation_coverage": recommendation_coverage,
                        **patch_brief_coverage,
                    },
                )

            lines = [
                "# Fallback UI/UX Optimizer Plan",
                "",
                f"Task ID: {getattr(task, 'task_id', '')}",
                f"Agent ID: {self.agent_id}",
                f"Status: fallback_recommendations_generated",
                "",
                "## Target Files",
                *[f"- {item}" for item in changed_files],
                "",
                "## Actor/Critic Summary",
                f"- Actor summary: {str(actor_critic_review.get('actor_summary') or 'No actor summary captured.').strip()}",
                f"- Critic summary: {str(actor_critic_review.get('critic_summary') or 'No critic summary captured.').strip()}",
                "",
                "## Recommended Changes",
                *[f"- {item}" for item in recommendations],
            ]
            release_verdict = str(release_gate.get("verdict") or "").strip()
            if release_verdict:
                lines.extend(
                    [
                        "",
                        "## Complaint Output Release Gate",
                        f"- Verdict: {release_verdict}",
                        f"- Reason: {str(release_gate.get('reason') or 'No reason captured.').strip()}",
                    ]
                )
            filing_shape_score = complaint_output_feedback.get("filing_shape_score")
            if filing_shape_score is not None:
                lines.extend(
                    [
                        "",
                        "## Complaint Output Signals",
                        f"- Filing shape score: {filing_shape_score}",
                        f"- Claim type alignment score: {complaint_output_feedback.get('claim_type_alignment_score')}",
                    ]
                )

            patch_path.write_text("\n".join(lines).strip() + "\n")
            self._last_generation_diagnostics = codex_diagnostics + deterministic_diagnostics + [
                {
                    "backend": "local_fallback_optimizer",
                    "reason": "ipfs_datasets_py agentic optimizer classes were unavailable, so a deterministic optimizer plan was generated.",
                    "patch_path": str(patch_path),
                }
            ]
            return FallbackOptimizerResult(
                success=True,
                status="fallback_recommendations_generated",
                patch_path=str(patch_path),
                metadata={
                    "changed_files": [],
                    "target_files": changed_files,
                    "recommendations": recommendations,
                    "optimizer_backend": "local_fallback_optimizer",
                    "selected_patch_briefs": selected_patch_briefs,
                    "recommendation_coverage": recommendation_coverage,
                    **_summarize_selected_patch_brief_coverage([]),
                },
            )

    fallback_method = SimpleNamespace(
        ACTOR_CRITIC="ACTOR_CRITIC",
        ADVERSARIAL="ADVERSARIAL",
        TEST_DRIVEN="TEST_DRIVEN",
        CHAOS="CHAOS",
    )
    return {
        "OptimizationTask": FallbackOptimizationTask,
        "OptimizationMethod": fallback_method,
        "OptimizerLLMRouter": None,
        "optimizer_classes": {
            "actor_critic": FallbackLocalOptimizer,
            "adversarial": FallbackLocalOptimizer,
            "test_driven": FallbackLocalOptimizer,
            "chaos": FallbackLocalOptimizer,
        },
    }
