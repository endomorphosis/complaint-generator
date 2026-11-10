"""UI feedback loop helpers delegated from Optimizer.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from adversarial_harness.optimizer import (
    UIOptimizationBundle,
    UIUXOptimizationBundle,
)

def build_ui_ux_optimization_task(
    self,
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str,
    iterations: int,
    method: str = "actor_critic",
    priority: int = 80,
    constraints: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    components: Optional[Dict[str, Any]] = None,
    review_runs: Optional[List[Dict[str, Any]]] = None,
    target_files: Optional[List[str | Path]] = None,
) -> Any:
    components = components or self._resolve_agentic_optimizer_components()
    task_cls = components["OptimizationTask"]
    method_enum = components["OptimizationMethod"]

    normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")
    if normalized_method not in {"actor_critic", "adversarial", "test_driven", "chaos"}:
        raise ValueError(f"Unsupported agentic optimization method: {method}")

    screenshot_root = Path(screenshot_dir)
    output_root = Path(output_dir)
    resolved_target_files = [
        Path(path) for path in (target_files or self._default_ui_ux_target_files())
    ]
    latest_run = dict((review_runs or [])[-1] or {}) if review_runs else {}
    latest_markdown_path = str(latest_run.get("review_markdown_path") or "")
    latest_json_path = str(latest_run.get("review_json_path") or "")
    latest_review_payload = self._read_ui_ux_review_json(Path(latest_json_path)) if latest_json_path else {}
    ui_review_bundle = self.build_ui_optimization_bundle(ui_review_report=latest_review_payload)
    patch_briefs = list(ui_review_bundle.patch_briefs or [])
    prioritized_patch_briefs = self._prioritize_ui_patch_briefs(patch_briefs)
    carry_forward_patch_briefs = [
        dict(item)
        for item in list((metadata or {}).get("carry_forward_patch_briefs") or [])
        if isinstance(item, dict)
    ]
    if carry_forward_patch_briefs:
        prioritized_with_carry_forward: List[Dict[str, Any]] = []
        seen_patch_brief_keys: set[tuple[str, str, str]] = set()

        def _patch_brief_key(brief: Dict[str, Any]) -> tuple[str, str, str]:
            return (
                str((brief or {}).get("title") or "").strip().lower(),
                str((brief or {}).get("surface") or "").strip().lower(),
                str((brief or {}).get("recommended_action") or "").strip().lower(),
            )

        for brief in carry_forward_patch_briefs + prioritized_patch_briefs:
            key = _patch_brief_key(brief)
            if key in seen_patch_brief_keys:
                continue
            seen_patch_brief_keys.add(key)
            prioritized_with_carry_forward.append(dict(brief))
        prioritized_patch_briefs = prioritized_with_carry_forward
    selected_patch_briefs = self._select_ui_patch_briefs(
        prioritized_patch_briefs,
        max_items=self._ui_patch_brief_batch_limit(prioritized_patch_briefs),
    )
    top_patch_brief = dict(selected_patch_briefs[0]) if selected_patch_briefs else {}
    selected_target_paths: List[Path] = []
    for brief in selected_patch_briefs:
        for raw_path in list(brief.get("target_files") or []):
            text = str(raw_path).strip()
            if not text:
                continue
            candidate = Path(text)
            if candidate not in selected_target_paths:
                selected_target_paths.append(candidate)
    if selected_target_paths:
        resolved_target_files = selected_target_paths
    recommendation_coverage = {
        "total_patch_briefs": len(patch_briefs),
        "selected_patch_briefs_count": len(selected_patch_briefs),
        "uncovered_patch_briefs_count": max(0, len(patch_briefs) - len(selected_patch_briefs)),
        "selected_patch_brief_titles": [
            str((item or {}).get("title") or "").strip()
            for item in selected_patch_briefs
            if str((item or {}).get("title") or "").strip()
        ],
        "selected_target_files": [str(path) for path in selected_target_paths] if selected_target_paths else [],
    }
    latest_review_excerpt = str(
        latest_review_payload.get("review")
        or latest_review_payload.get("summary")
        or "No llm_router review summary was captured."
    ).strip()
    latest_review_excerpt = latest_review_excerpt[:1200]

    description = (
        "Use the "
        f"{normalized_method} optimizer to improve the complaint-generator MCP dashboard and shared complaint workflow UI/UX. "
        f"The optimization source is a screenshot-driven Playwright audit stored under {screenshot_root}. "
        "Preserve the shared JavaScript MCP SDK path, DID-backed session continuity, and the alignment between package exports, CLI tools, MCP tools, and browser flows. "
        f"Latest UI review excerpt: {latest_review_excerpt}. "
        "Apply changes only within the resolved shared dashboard targets."
    )

    return task_cls(
        task_id=f"complaint_ui_ux_autopatch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
        description=description,
        target_files=resolved_target_files,
        method=getattr(method_enum, normalized_method.upper()),
        priority=int(priority),
        constraints={
            "preserve_sdk_contract": True,
            "preserve_did_persistence": True,
            "require_playwright_validation": True,
            "screenshot_dir": str(screenshot_root),
            "review_output_dir": str(output_root),
            "pytest_target": str(pytest_target),
            **dict(constraints or {}),
        },
        metadata={
            "source": "adversarial_harness.ui_ux",
            "workflow_type": "ui_ux_autopatch",
            "screenshot_dir": str(screenshot_root),
            "output_dir": str(output_root),
            "iterations": int(iterations),
            "pytest_target": str(pytest_target),
            "latest_review_markdown_path": latest_markdown_path,
            "latest_review_json_path": latest_json_path,
            "target_contracts": [
                "complaint_generator package exports",
                "complaint-workspace CLI",
                "complaint-mcp-server tools",
                "window.ComplaintMcpSdk browser SDK",
            ],
            "actor_critic_review": self._extract_actor_critic_review_summary(latest_review_payload, latest_review_excerpt),
            "complaint_output_feedback": self._extract_complaint_output_feedback(latest_review_payload),
            "complaint_output_release_gate": self._build_complaint_output_release_gate(
                self._extract_complaint_output_feedback(latest_review_payload)
            ),
            "report_summary": {
                "summary": str(ui_review_bundle.summary or latest_review_excerpt).strip(),
                "recommendations": [
                    str((item or {}).get("implementation_notes") or "").strip()
                    for item in list(ui_review_bundle.recommended_changes or [])
                    if isinstance(item, dict) and str((item or {}).get("implementation_notes") or "").strip()
                ][:6],
                "issues": [
                    str((item or {}).get("problem") or "").strip()
                    for item in list(ui_review_bundle.issues or [])
                    if isinstance(item, dict) and str((item or {}).get("problem") or "").strip()
                ][:6],
                "patch_briefs": patch_briefs,
                "prioritized_patch_briefs": prioritized_patch_briefs,
                "carry_forward_patch_briefs": carry_forward_patch_briefs,
                "selected_patch_briefs": selected_patch_briefs,
                "top_patch_brief": top_patch_brief,
                "recommendation_coverage": recommendation_coverage,
                "active_target_files": [str(path) for path in list(resolved_target_files or [])],
            },
            **dict(metadata or {}),
        },
    )

def build_ui_ux_optimization_bundle(
    self,
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str,
    iterations: int = 1,
    method: str = "actor_critic",
    priority: int = 80,
    constraints: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    components: Optional[Dict[str, Any]] = None,
    workflow_result: Optional[Dict[str, Any]] = None,
) -> UIUXOptimizationBundle:
    if workflow_result is None:
        from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

        supplemental_artifacts = list((metadata or {}).get("supplemental_artifacts") or [])
        workflow_result = run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=output_dir,
            iterations=iterations,
            pytest_target=pytest_target,
            supplemental_artifacts=supplemental_artifacts,
        )

    review_runs = list(workflow_result.get("runs") or [])
    latest_review_json_path = str((review_runs[-1] or {}).get("review_json_path") or "") if review_runs else ""
    latest_review_payload = self._read_ui_ux_review_json(Path(latest_review_json_path)) if latest_review_json_path else {}
    ui_review_bundle = self.build_ui_optimization_bundle(ui_review_report=latest_review_payload)
    task = self.build_ui_ux_optimization_task(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target=pytest_target,
        iterations=iterations,
        method=method,
        priority=priority,
        constraints=constraints,
        metadata=metadata,
        components=components,
        review_runs=review_runs,
        target_files=self._default_ui_ux_target_files(),
    )

    complaint_output_feedback = self._extract_complaint_output_feedback(latest_review_payload)
    return UIUXOptimizationBundle(
        timestamp=datetime.now(UTC).isoformat(),
        screenshot_dir=str(screenshot_dir),
        output_dir=str(output_dir),
        iterations=int(workflow_result.get("iterations") or iterations),
        pytest_target=str(pytest_target),
        target_files=[str(path) for path in list(getattr(task, "target_files", []) or [])],
        review_runs=review_runs,
        complaint_output_feedback={
            **complaint_output_feedback,
            "release_gate": self._build_complaint_output_release_gate(complaint_output_feedback),
        },
        patch_briefs=list(ui_review_bundle.patch_briefs or []),
        latest_review_markdown_path=str((review_runs[-1] or {}).get("review_markdown_path") or "") or None,
        latest_review_json_path=latest_review_json_path or None,
        task={
            "task_id": str(getattr(task, "task_id", "")),
            "description": str(getattr(task, "description", "")),
            "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
            "method": str(getattr(task, "method", "")),
            "priority": int(getattr(task, "priority", priority) or priority),
            "constraints": dict(getattr(task, "constraints", {}) or {}),
            "metadata": dict(getattr(task, "metadata", {}) or {}),
        },
    )

def run_agentic_ui_ux_autopatch(
    self,
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str,
    iterations: int = 1,
    method: str = "actor_critic",
    priority: int = 80,
    constraints: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    llm_router: Any = None,
    optimizer: Any = None,
    agent_id: str = "complaint-ui-ux-optimizer",
    components: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    components = components or self._resolve_agentic_optimizer_components()
    bundle = self.build_ui_ux_optimization_bundle(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target=pytest_target,
        iterations=iterations,
        method=method,
        priority=priority,
        constraints=constraints,
        metadata=metadata,
        components=components,
    )
    review_runs = list(bundle.review_runs or [])
    task = self.build_ui_ux_optimization_task(
        screenshot_dir=screenshot_dir,
        output_dir=output_dir,
        pytest_target=pytest_target,
        iterations=iterations,
        method=method,
        priority=priority,
        constraints=constraints,
        metadata=metadata,
        components=components,
        review_runs=review_runs,
        target_files=list(bundle.target_files or []),
    )

    router_cls = components["OptimizerLLMRouter"]
    optimizer_classes = components["optimizer_classes"]
    normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")
    resolved_router = llm_router
    if resolved_router is None and router_cls is not None:
        resolved_router = router_cls(enable_tracking=False, enable_caching=True)

    resolved_optimizer = optimizer
    if resolved_optimizer is None:
        if normalized_method not in optimizer_classes:
            raise ValueError(f"Unsupported agentic optimization method: {method}")
        resolved_optimizer = optimizer_classes[normalized_method](
            agent_id=agent_id,
            llm_router=resolved_router,
        )

    self._last_agentic_optimizer = resolved_optimizer
    self._last_agentic_generation_diagnostics = []
    result = resolved_optimizer.optimize(task)
    diagnostics = getattr(resolved_optimizer, "_last_generation_diagnostics", None)
    if isinstance(diagnostics, list):
        self._last_agentic_generation_diagnostics = list(diagnostics)
    return {
        "bundle": bundle.to_dict(),
        "task": {
            "task_id": str(getattr(task, "task_id", "")),
            "description": str(getattr(task, "description", "")),
            "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
            "constraints": dict(getattr(task, "constraints", {}) or {}),
            "metadata": dict(getattr(task, "metadata", {}) or {}),
        },
        "optimizer_result": result,
        "generation_diagnostics": list(self._last_agentic_generation_diagnostics or []),
    }

def run_agentic_ui_ux_feedback_loop(
    self,
    *,
    screenshot_dir: str | Path,
    output_dir: str | Path,
    pytest_target: str,
    max_rounds: int = 2,
    review_iterations: int = 1,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    method: str = "actor_critic",
    priority: int = 80,
    notes: Optional[str] = None,
    goals: Optional[List[str]] = None,
    constraints: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    llm_router: Any = None,
    optimizer: Any = None,
    agent_id: str = "complaint-ui-ux-optimizer",
    components: Optional[Dict[str, Any]] = None,
    stop_when_review_stable: bool = True,
    break_on_no_changes: bool = True,
    reuse_existing_screenshots: bool = False,
) -> Dict[str, Any]:
    from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

    def _latest_review_text(workflow_result: Dict[str, Any]) -> str:
        latest_review = str(workflow_result.get("latest_review") or "").strip()
        if latest_review:
            return latest_review
        latest_json_path = str(workflow_result.get("latest_review_json_path") or "").strip()
        if latest_json_path:
            payload = self._read_ui_ux_review_json(Path(latest_json_path))
            return str(payload.get("review") or payload.get("summary") or "").strip()
        return ""

    def _unique_nonempty(values: List[Any]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return ordered

    def _serialize_optimizer_result(result: Any) -> Dict[str, Any]:
        metadata_payload = dict(getattr(result, "metadata", {}) or {})
        return {
            "success": bool(getattr(result, "success", False)),
            "status": str(getattr(result, "status", "")),
            "patch_path": str(getattr(result, "patch_path", "")),
            "patch_cid": str(getattr(result, "patch_cid", "")),
            "metadata": metadata_payload,
            "changed_files": list(metadata_payload.get("changed_files") or []),
        }

    components = components or self._resolve_agentic_optimizer_components()
    router_cls = components["OptimizerLLMRouter"]
    optimizer_classes = components["optimizer_classes"]
    normalized_method = str(method or "actor_critic").strip().lower().replace("-", "_")

    resolved_router = llm_router
    if resolved_router is None and router_cls is not None:
        resolved_router = router_cls(enable_tracking=False, enable_caching=True)

    resolved_optimizer = optimizer
    if resolved_optimizer is None:
        if normalized_method not in optimizer_classes:
            raise ValueError(f"Unsupported agentic optimization method: {method}")
        resolved_optimizer = optimizer_classes[normalized_method](
            agent_id=agent_id,
            llm_router=resolved_router,
        )

    root_output_dir = Path(output_dir)
    root_output_dir.mkdir(parents=True, exist_ok=True)
    cycles: List[Dict[str, Any]] = []
    previous_validation_review = ""
    stop_reason = "max_rounds_reached"
    base_metadata = dict(metadata or {})
    supplemental_artifacts = list(base_metadata.get("supplemental_artifacts") or [])
    base_goals = [str(item).strip() for item in list(goals or []) if str(item).strip()]
    carry_forward_patch_briefs: List[Dict[str, Any]] = []
    carry_forward_goals: List[str] = []
    coverage_retry_budget = 1
    planned_rounds = max(1, int(max_rounds))
    round_index = 1

    while round_index <= planned_rounds:
        round_dir = root_output_dir / f"round-{round_index:02d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        round_metadata = dict(base_metadata)
        if supplemental_artifacts:
            round_metadata["supplemental_artifacts"] = list(supplemental_artifacts)
        if carry_forward_patch_briefs:
            round_metadata["carry_forward_patch_briefs"] = [dict(item) for item in carry_forward_patch_briefs]
        round_goals = _unique_nonempty(base_goals + carry_forward_goals)
        round_notes = str(notes or "").strip()
        if carry_forward_goals:
            carry_forward_note = (
                "Carry forward uncovered selected recommendations from the prior round:\n- "
                + "\n- ".join(carry_forward_goals[:6])
            )
            round_notes = f"{round_notes}\n\n{carry_forward_note}".strip() if round_notes else carry_forward_note

        pre_workflow = run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=round_dir / "pre-review",
            iterations=max(1, int(review_iterations)),
            provider=provider,
            model=model,
            pytest_target=pytest_target,
            notes=round_notes or None,
            goals=round_goals,
            initial_previous_review=previous_validation_review or None,
            supplemental_artifacts=supplemental_artifacts,
            reuse_existing_screenshots=reuse_existing_screenshots,
        )
        pre_review_payload = (
            self._read_ui_ux_review_json(Path(str(pre_workflow.get("latest_review_json_path") or "")))
            if str(pre_workflow.get("latest_review_json_path") or "").strip()
            else {}
        )
        pre_review_summary = self._extract_actor_critic_review_summary(
            pre_review_payload,
            _latest_review_text(pre_workflow),
        )
        bundle = self.build_ui_ux_optimization_bundle(
            screenshot_dir=screenshot_dir,
            output_dir=round_dir / "pre-review",
            pytest_target=pytest_target,
            iterations=max(1, int(review_iterations)),
            method=method,
            priority=priority,
            constraints=constraints,
            metadata=round_metadata,
            components=components,
            workflow_result=pre_workflow,
        )
        task = self.build_ui_ux_optimization_task(
            screenshot_dir=screenshot_dir,
            output_dir=round_dir / "pre-review",
            pytest_target=pytest_target,
            iterations=max(1, int(review_iterations)),
            method=method,
            priority=priority,
            constraints=constraints,
            metadata=round_metadata,
            components=components,
            review_runs=list(bundle.review_runs or []),
            target_files=list(bundle.target_files or []),
        )

        self._last_agentic_optimizer = resolved_optimizer
        self._last_agentic_generation_diagnostics = []
        optimize_result = resolved_optimizer.optimize(task)
        diagnostics = getattr(resolved_optimizer, "_last_generation_diagnostics", None)
        if isinstance(diagnostics, list):
            self._last_agentic_generation_diagnostics = list(diagnostics)

        validation_workflow = run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=round_dir / "validation-review",
            iterations=max(1, int(review_iterations)),
            provider=provider,
            model=model,
            pytest_target=pytest_target,
            notes=round_notes or None,
            goals=round_goals,
            initial_previous_review=_latest_review_text(pre_workflow) or previous_validation_review or None,
            supplemental_artifacts=supplemental_artifacts,
            reuse_existing_screenshots=reuse_existing_screenshots,
        )
        validation_review = _latest_review_text(validation_workflow)
        validation_review_payload = (
            self._read_ui_ux_review_json(Path(str(validation_workflow.get("latest_review_json_path") or "")))
            if str(validation_workflow.get("latest_review_json_path") or "").strip()
            else {}
        )
        validation_review_summary = self._extract_actor_critic_review_summary(
            validation_review_payload,
            validation_review,
        )
        serialized_result = _serialize_optimizer_result(optimize_result)
        report_summary = dict((getattr(task, "metadata", {}) or {}).get("report_summary") or {})
        selected_patch_briefs = [
            dict(item)
            for item in list(report_summary.get("selected_patch_briefs") or [])
            if isinstance(item, dict)
        ]
        selected_patch_brief = dict(report_summary.get("top_patch_brief") or {})
        recommendation_coverage = dict(report_summary.get("recommendation_coverage") or {})
        selected_target_files = [
            str(path).strip()
            for path in list(report_summary.get("active_target_files") or getattr(task, "target_files", []) or [])
            if str(path).strip()
        ]
        optimizer_metadata = dict(serialized_result.get("metadata") or {})
        covered_patch_brief_titles = [
            str(item).strip()
            for item in list(optimizer_metadata.get("covered_patch_brief_titles") or [])
            if str(item).strip()
        ]
        uncovered_selected_patch_brief_titles = [
            str(item).strip()
            for item in list(optimizer_metadata.get("uncovered_selected_patch_brief_titles") or [])
            if str(item).strip()
        ]
        selected_patch_brief_coverage_ratio = float(
            optimizer_metadata.get("selected_patch_brief_coverage_ratio") or 0.0
        )
        requires_coverage_follow_up = bool(
            selected_patch_briefs
            and not covered_patch_brief_titles
            and not list(serialized_result.get("changed_files") or [])
            and selected_patch_brief_coverage_ratio <= 0.0
        )
        patch_briefs_payload = {
            "round": round_index,
            "generated_at": datetime.now(UTC).isoformat(),
            "patch_briefs": list(getattr(bundle, "patch_briefs", []) or []),
            "target_files": list(bundle.target_files or []),
            "selected_patch_briefs": selected_patch_briefs,
            "selected_patch_brief": selected_patch_brief,
            "recommendation_coverage": recommendation_coverage,
            "selected_target_files": selected_target_files,
            "task_id": str(getattr(task, "task_id", "")),
            "pytest_target": str(pytest_target),
        }
        patch_briefs_path = self._write_json_artifact(
            round_dir / "patch-briefs.json",
            patch_briefs_payload,
        )
        coverage_gap_payload = {
            "round": round_index,
            "generated_at": datetime.now(UTC).isoformat(),
            "selected_patch_brief_titles": [
                str((item or {}).get("title") or "").strip()
                for item in selected_patch_briefs
                if str((item or {}).get("title") or "").strip()
            ],
            "covered_patch_brief_titles": covered_patch_brief_titles,
            "uncovered_selected_patch_brief_titles": uncovered_selected_patch_brief_titles,
            "selected_patch_brief_coverage_ratio": selected_patch_brief_coverage_ratio,
            "changed_files": list(serialized_result.get("changed_files") or []),
            "requires_follow_up": requires_coverage_follow_up,
        }
        coverage_gap_path = self._write_json_artifact(
            round_dir / "coverage-gap.json",
            coverage_gap_payload,
        )
        complaint_output_validation_review = {
            **self._extract_complaint_output_feedback(validation_review_payload),
            "release_gate": self._build_complaint_output_release_gate(
                self._extract_complaint_output_feedback(validation_review_payload)
            ),
        }
        round_summary_path = self._write_json_artifact(
            round_dir / "round-summary.json",
            {
                "round": round_index,
                "generated_at": datetime.now(UTC).isoformat(),
                "task_id": str(getattr(task, "task_id", "")),
                "patch_briefs_path": patch_briefs_path,
                "coverage_gap_path": coverage_gap_path,
                "selected_patch_briefs": selected_patch_briefs,
                "selected_patch_brief": selected_patch_brief,
                "recommendation_coverage": recommendation_coverage,
                "selected_target_files": selected_target_files,
                "pre_review_json_path": str(pre_workflow.get("latest_review_json_path") or ""),
                "validation_review_json_path": str(validation_workflow.get("latest_review_json_path") or ""),
                "complaint_output_validation_review": complaint_output_validation_review,
                "optimizer_result": serialized_result,
            },
        )
        cycles.append(
            {
                "round": round_index,
                "bundle": bundle.to_dict(),
                "patch_briefs_path": patch_briefs_path,
                "coverage_gap_path": coverage_gap_path,
                "round_summary_path": round_summary_path,
                "selected_patch_briefs": selected_patch_briefs,
                "selected_patch_brief": selected_patch_brief,
                "recommendation_coverage": recommendation_coverage,
                "selected_target_files": selected_target_files,
                "task": {
                    "task_id": str(getattr(task, "task_id", "")),
                    "description": str(getattr(task, "description", "")),
                    "target_files": [str(path) for path in list(getattr(task, "target_files", []) or [])],
                    "constraints": dict(getattr(task, "constraints", {}) or {}),
                    "metadata": dict(getattr(task, "metadata", {}) or {}),
                },
                "optimizer_result": serialized_result,
                "generation_diagnostics": list(self._last_agentic_generation_diagnostics or []),
                "actor_critic_pre_review": pre_review_summary,
                "actor_critic_validation_review": validation_review_summary,
                "complaint_output_pre_review": {
                    **self._extract_complaint_output_feedback(pre_review_payload),
                    "release_gate": self._build_complaint_output_release_gate(
                        self._extract_complaint_output_feedback(pre_review_payload)
                    ),
                },
                "complaint_output_validation_review": complaint_output_validation_review,
                "pre_review": pre_workflow,
                "validation_review": validation_workflow,
            }
        )

        if requires_coverage_follow_up:
            carry_forward_patch_briefs = [
                dict(brief)
                for brief in selected_patch_briefs
                if str((brief or {}).get("title") or "").strip() in set(uncovered_selected_patch_brief_titles)
                or not uncovered_selected_patch_brief_titles
            ]
            carry_forward_goals = _unique_nonempty(
                [
                    (
                        "Implement the previously selected optimizer repair: "
                        + str((brief or {}).get("title") or "").strip()
                        + (
                            f". {str((brief or {}).get('recommended_action') or '').strip()}"
                            if str((brief or {}).get("recommended_action") or "").strip()
                            else ""
                        )
                    ).strip()
                    for brief in carry_forward_patch_briefs
                    if str((brief or {}).get("title") or "").strip()
                ]
            )
            supplemental_artifacts = _unique_nonempty(
                list(supplemental_artifacts)
                + [patch_briefs_path, coverage_gap_path, round_summary_path]
            )
            if coverage_retry_budget > 0 and round_index >= planned_rounds:
                planned_rounds += 1
                coverage_retry_budget -= 1
                stop_reason = "extending_for_uncovered_selected_patch_briefs"
        else:
            carry_forward_patch_briefs = []
            carry_forward_goals = []

        if break_on_no_changes and not serialized_result["changed_files"] and not serialized_result["patch_path"]:
            stop_reason = "no_changes_reported"
            break
        if stop_when_review_stable and previous_validation_review and validation_review == previous_validation_review:
            if requires_coverage_follow_up and coverage_retry_budget > 0:
                planned_rounds = max(planned_rounds, round_index + 1)
                coverage_retry_budget -= 1
                stop_reason = "extending_for_uncovered_selected_patch_briefs"
                previous_validation_review = validation_review
                round_index += 1
                continue
            stop_reason = "validation_review_stable"
            break
        previous_validation_review = validation_review
        round_index += 1

    return {
        "workflow_type": "ui_ux_closed_loop",
        "max_rounds": max(1, int(max_rounds)),
        "planned_rounds": planned_rounds,
        "rounds_executed": len(cycles),
        "stop_reason": stop_reason,
        "cycles": cycles,
        "actor_critic_summary": cycles[-1]["actor_critic_validation_review"] if cycles else {},
        "complaint_output_feedback": cycles[-1]["complaint_output_validation_review"] if cycles else {},
        "complaint_output_release_gate": (
            cycles[-1]["complaint_output_validation_review"].get("release_gate") if cycles else {}
        ),
        "latest_validation_review": previous_validation_review or (
            cycles[-1]["validation_review"].get("latest_review") if cycles else ""
        ),
    }

def build_ui_optimization_bundle(
    self,
    *,
    ui_review_report: Dict[str, Any],
) -> UIOptimizationBundle:
    report = dict(ui_review_report or {})
    review_payload = report.get("review")
    review = dict(review_payload) if isinstance(review_payload, dict) else {}
    review_markdown = str(review_payload or "") if not isinstance(review_payload, dict) else ""
    complaint_output_feedback = dict(report.get("complaint_output_feedback") or review.get("complaint_output_feedback") or {})
    formal_diagnostics = dict(complaint_output_feedback.get("formal_diagnostics") or {})
    target_files = [str(path) for path in self._ui_target_files_from_review(report)]
    recommended_changes = [
        dict(item)
        for item in list((review.get("recommended_changes") if review else report.get("recommended_changes")) or [])
        if isinstance(item, dict)
    ]
    for suggestion in [str(item).strip() for item in list(complaint_output_feedback.get("ui_suggestions") or []) if str(item).strip()]:
        recommended_changes.append(
            {
                "title": "Complaint output feedback",
                "implementation_notes": suggestion,
                "shared_code_path": "templates/workspace.html",
                "sdk_considerations": "Preserve the shared ComplaintMcpClient export, analysis, and optimizer path while improving filing guidance.",
            }
        )
    draft_normalizations = [
        str(item).strip()
        for item in list(complaint_output_feedback.get("draft_normalizations") or [])
        if str(item).strip()
    ]
    draft_strategy = str(complaint_output_feedback.get("draft_strategy") or "").strip().lower()
    draft_fallback_reason = str(complaint_output_feedback.get("draft_fallback_reason") or "").strip()
    if draft_strategy and draft_strategy != "llm_router":
        recommended_changes.append(
            {
                "title": "Template fallback warning",
                "implementation_notes": (
                    "The exported complaint is still relying on the template drafting path instead of a successful llm_router draft. "
                    "Treat this as a product-quality signal: make fallback status, release-gate posture, and drafting-path guidance more explicit in the UI and optimizer review."
                ),
                "shared_code_path": "templates/workspace.html",
                "sdk_considerations": "Preserve MCP SDK draft generation while surfacing when the system fell back from the intended llm_router path.",
            }
        )
    if draft_fallback_reason:
        recommended_changes.append(
            {
                "title": "Draft fallback reason warning",
                "implementation_notes": (
                    "The complaint generator recorded a concrete fallback reason before export. "
                    f"Fallback reason: {draft_fallback_reason}"
                ),
                "shared_code_path": "applications/complaint_workspace.py",
                "sdk_considerations": "Keep the MCP SDK draft flow intact while surfacing actionable fallback guidance in the dashboard and review outputs.",
            }
        )
    if draft_normalizations:
        recommended_changes.append(
            {
                "title": "LLM draft cleanup warning",
                "implementation_notes": (
                    "The generated complaint required post-generation cleanup before it resembled a filing. "
                    f"Normalization steps observed: {', '.join(draft_normalizations[:5])}."
                ),
                "shared_code_path": "applications/complaint_workspace.py",
                "sdk_considerations": "Preserve MCP SDK draft generation while exposing when LLM outputs required cleanup before export.",
            }
        )
    top_formal_findings = [
        str(item).strip()
        for item in list(formal_diagnostics.get("top_formal_findings") or [])
        if str(item).strip()
    ]
    if top_formal_findings:
        recommended_changes.append(
            {
                "title": "Formal complaint diagnostics warning",
                "implementation_notes": (
                    "The complaint-output analyzer still sees filing-quality defects. "
                    f"Top findings: {' | '.join(top_formal_findings[:3])}."
                ),
                "shared_code_path": "templates/workspace.html",
                "sdk_considerations": "Keep MCP SDK export and analysis controls visible while highlighting the top complaint defects before download.",
            }
        )
    alignment_score_raw = complaint_output_feedback.get("claim_type_alignment_score")
    alignment_score = None
    if alignment_score_raw is not None and str(alignment_score_raw).strip():
        try:
            alignment_score = int(alignment_score_raw)
        except Exception:
            alignment_score = None
    if alignment_score is not None and 0 <= alignment_score < 80:
        recommended_changes.append(
            {
                "title": "Claim type alignment warning",
                "implementation_notes": (
                    "Keep the selected claim type, complaint heading, and count heading visible through draft and export so the complaint does not drift into the wrong legal theory."
                ),
                "shared_code_path": "templates/workspace.html",
                "sdk_considerations": "Preserve MCP SDK draft generation while exposing claim-type alignment warnings before export.",
            }
        )
    patch_briefs = self._build_ui_patch_briefs(
        review=review,
        recommended_changes=recommended_changes,
        complaint_output_feedback=complaint_output_feedback,
        target_files=target_files,
    )
    return UIOptimizationBundle(
        timestamp=datetime.now(UTC).isoformat(),
        screenshot_dir=str(report.get("screenshot_dir") or ""),
        screenshot_paths=[
            str((item or {}).get("path") or "").strip()
            for item in list(report.get("screenshots") or [])
            if isinstance(item, dict) and str((item or {}).get("path") or "").strip()
        ],
        artifact_count=int(len(list(report.get("screenshots") or []))),
        summary=str(review.get("summary") or report.get("summary") or review_markdown).strip(),
        issues=[
            dict(item)
            for item in list((review.get("issues") if review else report.get("issues")) or [])
            if isinstance(item, dict)
        ],
        recommended_changes=recommended_changes,
        broken_controls=[
            dict(item)
            for item in list((review.get("broken_controls") if review else report.get("broken_controls")) or [])
            if isinstance(item, dict)
        ],
        complaint_journey=dict(review.get("complaint_journey") or {}),
        actor_plan=dict(review.get("actor_plan") or {}),
        critic_review=dict(review.get("critic_review") or {}),
        playwright_followups=[
            str(item)
            for item in list((review.get("playwright_followups") if review else report.get("playwright_followups")) or [])
            if str(item)
        ],
        complaint_output_feedback=complaint_output_feedback,
        target_files=target_files,
        patch_briefs=patch_briefs,
    )

def _build_ui_patch_briefs(
    *,
    review: Dict[str, Any],
    recommended_changes: List[Dict[str, Any]],
    complaint_output_feedback: Dict[str, Any],
    target_files: List[str],
) -> List[Dict[str, Any]]:
    briefs: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_brief(
        *,
        brief_id: str,
        title: str,
        surface: str,
        problem: str,
        recommended_action: str,
        validation_checks: List[str],
        files: List[str],
        severity: str = "warning",
        related_controls: List[str] | None = None,
    ) -> None:
        normalized = brief_id.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        briefs.append(
            {
                "id": brief_id,
                "title": title,
                "surface": surface,
                "severity": severity,
                "problem": problem,
                "recommended_action": recommended_action,
                "validation_checks": [str(item).strip() for item in validation_checks if str(item).strip()],
                "target_files": [str(item).strip() for item in files if str(item).strip()],
                "related_controls": [str(item).strip() for item in list(related_controls or []) if str(item).strip()],
            }
        )

    for index, item in enumerate(list(review.get("broken_controls") or []), start=1):
        if not isinstance(item, dict):
            continue
        control = str(item.get("control") or f"control-{index}").strip()
        surface = str(item.get("surface") or "/workspace").strip()
        add_brief(
            brief_id=f"broken-control-{index}-{control.lower().replace(' ', '-')}",
            title=f"Repair {control}",
            surface=surface,
            severity="critical",
            problem=str(item.get("failure_mode") or item.get("problem") or "Broken or misleading UI control.").strip(),
            recommended_action=str(item.get("repair") or "Repair the broken control and clarify the next state transition.").strip(),
            validation_checks=[
                f"Click `{control}` on `{surface}` and confirm the next complaint step is visibly obvious.",
                "Ensure the actor journey can proceed without losing shared complaint state.",
            ],
            files=target_files,
            related_controls=[control],
        )

    for index, item in enumerate(recommended_changes, start=1):
        if not isinstance(item, dict):
            continue
        shared_code_path = str(item.get("shared_code_path") or "").strip()
        validation_checks = [
            str(item.get("sdk_considerations") or "").strip(),
            "Re-run the Playwright complaint flow and verify complaint generation and exports still succeed.",
        ]
        files = [shared_code_path] if shared_code_path else list(target_files)
        add_brief(
            brief_id=f"recommended-change-{index}",
            title=str(item.get("title") or f"Recommended change {index}").strip(),
            surface="/workspace",
            severity="warning",
            problem=str(item.get("implementation_notes") or "Recommended UI/UX improvement from actor/critic review.").strip(),
            recommended_action=str(item.get("implementation_notes") or "Apply the recommended UI/UX repair.").strip(),
            validation_checks=validation_checks,
            files=files,
        )

    formal_diagnostics = dict(complaint_output_feedback.get("formal_diagnostics") or {})
    top_formal_findings = [
        str(item).strip()
        for item in list(formal_diagnostics.get("top_formal_findings") or [])
        if str(item).strip()
    ]
    if top_formal_findings:
        add_brief(
            brief_id="complaint-output-formality",
            title="Restore filing-ready complaint shape",
            surface="/workspace?tab=draft",
            severity="critical",
            problem="The generated complaint output still has filing-quality defects.",
            recommended_action="Adjust draft-stage guidance, release gating, and export warnings until the generated complaint consistently preserves formal pleading structure.",
            validation_checks=[
                "Generate a complaint and confirm the preview and exported markdown/PDF include caption, jurisdiction or venue, counts, prayer for relief, and signature block.",
                *top_formal_findings[:3],
            ],
            files=["templates/workspace.html", "applications/complaint_workspace.py"],
            related_controls=["Generate Draft", "Export Markdown", "Export PDF", "Analyze Output"],
        )

    alignment_score_raw = complaint_output_feedback.get("claim_type_alignment_score")
    alignment_score = None
    if alignment_score_raw is not None and str(alignment_score_raw).strip():
        try:
            alignment_score = int(alignment_score_raw)
        except Exception:
            alignment_score = None
    if alignment_score is not None and 0 <= alignment_score < 80:
        add_brief(
            brief_id="claim-type-alignment",
            title="Prevent claim-type drift before export",
            surface="/workspace?tab=draft",
            severity="critical",
            problem="The UI allowed the selected claim type and the final pleading shape to drift apart.",
            recommended_action="Keep claim type, complaint heading, and expected count heading visible during draft and export, and block release when alignment drops.",
            validation_checks=[
                "Switch claim types in the workspace and confirm the draft title, complaint heading, and count heading all update together.",
                "Verify exported markdown/PDF match the selected claim type.",
            ],
            files=["templates/workspace.html", "applications/complaint_workspace.py", "playwright/tests/complaint-flow.spec.js"],
            related_controls=["Claim Type", "Generate Draft", "Export Packet"],
        )

    return briefs

def build_ui_patch_tasks(
    self,
    *,
    ui_review_report: Dict[str, Any],
    method: str = "test_driven",
    priority: int = 72,
    constraints: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    components: Optional[Dict[str, Any]] = None,
) -> List[Any]:
    components = components or self._resolve_agentic_optimizer_components()
    task_cls = components["OptimizationTask"]
    method_enum = components["OptimizationMethod"]
    normalized_method = str(method or "test_driven").strip().lower().replace("-", "_")
    if normalized_method not in {"actor_critic", "adversarial", "test_driven", "chaos"}:
        raise ValueError(f"Unsupported agentic optimization method: {method}")

    bundle = self.build_ui_optimization_bundle(ui_review_report=ui_review_report)
    if not bundle.recommended_changes and not bundle.issues:
        return []

    summary = bundle.summary or "Improve the complaint dashboard UI and complaint-handling flow."
    recommendations = [
        str(item.get("title") or item.get("recommended_fix") or "").strip()
        for item in bundle.recommended_changes + bundle.issues + bundle.broken_controls
        if isinstance(item, dict)
    ]
    recommendations = [item for item in recommendations if item]
    report_patch_briefs_path = str(
        (ui_review_report or {}).get("patch_briefs_path")
        or (metadata or {}).get("patch_briefs_path")
        or ""
    ).strip()
    artifact_patch_briefs = self._load_patch_briefs_from_artifact(report_patch_briefs_path)
    prioritized_patch_briefs = self._prioritize_ui_patch_briefs(
        artifact_patch_briefs or list(bundle.patch_briefs or [])
    )
    selected_patch_briefs = self._select_ui_patch_briefs(
        prioritized_patch_briefs,
        max_items=self._ui_patch_brief_batch_limit(prioritized_patch_briefs),
    )
    top_patch_brief = dict(selected_patch_briefs[0]) if selected_patch_briefs else {}
    selected_target_files: List[Path] = []
    for brief in selected_patch_briefs:
        for raw_path in list(brief.get("target_files") or []):
            text = str(raw_path).strip()
            if not text:
                continue
            candidate = Path(text)
            if candidate not in selected_target_files:
                selected_target_files.append(candidate)
    narrowed_target_files = selected_target_files or [Path(path) for path in bundle.target_files]
    recommendation_coverage = {
        "total_patch_briefs": len(prioritized_patch_briefs),
        "selected_patch_briefs_count": len(selected_patch_briefs),
        "uncovered_patch_briefs_count": max(0, len(prioritized_patch_briefs) - len(selected_patch_briefs)),
        "selected_patch_brief_titles": [
            str((item or {}).get("title") or "").strip()
            for item in selected_patch_briefs
            if str((item or {}).get("title") or "").strip()
        ],
        "selected_target_files": [str(path) for path in selected_target_files] if selected_target_files else [],
    }
    if selected_patch_briefs:
        selected_brief_summary = "Selected patch briefs: " + " ".join(
            (
                f"[{index}] {str(brief.get('title') or '').strip()} "
                f"(surface: {str(brief.get('surface') or '').strip()}; "
                f"problem: {str(brief.get('problem') or '').strip()}; "
                f"action: {str(brief.get('recommended_action') or '').strip()})."
            )
            for index, brief in enumerate(selected_patch_briefs, start=1)
        )
    else:
        selected_brief_summary = "No single patch brief outranked the others; use the overall report summary."
    task = task_cls(
        task_id=f"ui_ux_autopatch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
        description=(
            "Use the screenshot-driven UI optimization lane to improve the complaint MCP workspace, "
            "preserve JavaScript MCP SDK usage, and keep the package/CLI/MCP contract coherent. "
            f"Current review summary: {summary} {selected_brief_summary}"
        ),
        target_files=narrowed_target_files,
        method=getattr(method_enum, normalized_method.upper()),
        priority=int(priority),
        constraints=dict(constraints or {}),
        metadata={
            "source": "adversarial_harness_ui_review",
            "workflow_phase": "ui_ux_review",
            "workflow_phase_status": "warning" if bundle.issues else "ready",
            "workflow_phase_priority": 1,
            "report_summary": {
                "summary": bundle.summary,
                "recommendations": recommendations[:5],
                "broken_controls": list(bundle.broken_controls or []),
                "complaint_journey": dict(bundle.complaint_journey or {}),
                "actor_plan": dict(bundle.actor_plan or {}),
                "critic_review": dict(bundle.critic_review or {}),
                "playwright_followups": list(bundle.playwright_followups or []),
                "screenshot_paths": list(bundle.screenshot_paths or []),
                "complaint_output_feedback": dict(bundle.complaint_output_feedback or {}),
                "complaint_output_suggestions": list((bundle.complaint_output_feedback or {}).get("ui_suggestions") or []),
                "formal_diagnostics": dict((bundle.complaint_output_feedback or {}).get("formal_diagnostics") or {}),
                "claim_type_alignment_score": int((bundle.complaint_output_feedback or {}).get("claim_type_alignment_score") or 0),
                "draft_strategy": str((bundle.complaint_output_feedback or {}).get("draft_strategy") or ""),
                "draft_fallback_reason": str((bundle.complaint_output_feedback or {}).get("draft_fallback_reason") or ""),
                "draft_normalizations": list((bundle.complaint_output_feedback or {}).get("draft_normalizations") or []),
                "recommended_target_files": list(bundle.target_files or []),
                "patch_briefs": list(bundle.patch_briefs or []),
                "patch_briefs_path": report_patch_briefs_path,
                "prioritized_patch_briefs": prioritized_patch_briefs,
                "selected_patch_briefs": selected_patch_briefs,
                "top_patch_brief": top_patch_brief,
                "recommendation_coverage": recommendation_coverage,
                "active_target_files": [str(path) for path in narrowed_target_files],
            },
            "ui_review_report": dict(ui_review_report or {}),
            **dict(metadata or {}),
        },
    )
    return [task]

