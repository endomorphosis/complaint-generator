"""Mike integration helpers delegated from ComplaintWorkspaceService.

The functions keep the original method bodies. The class methods forward here.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from applications.complaint_workspace import (
    DEFAULT_USER_ID,
    MIKE_SKILL_ASSET_MANIFEST_VERSION,
    MIKE_STATUS_CONTRACT_VERSION,
    MIKE_WORKFLOW_STATE_LABELS,
    ComplaintWorkspaceService,
    _leanstral_status_snapshot,
    _legal_source_availability_snapshot,
    _prefer_checkout,
    _run_hybrid_reasoning_safely,
    _utc_now,
)


def _build_mike_submodule_inventory(cls) -> Dict[str, Any]:
    repo_root = cls._repo_root()
    mike_root = _prefer_checkout(repo_root, "mike")
    ipfs_root = _prefer_checkout(repo_root, "ipfs_datasets_py")
    accelerate_root = _prefer_checkout(repo_root, "ipfs_accelerate_py")
    kit_root = _prefer_checkout(repo_root, "ipfs_kit_py")
    mike_frontend_package = cls._safe_read_json_file(mike_root / "frontend" / "package.json")
    mike_backend_package = cls._safe_read_json_file(mike_root / "backend" / "package.json")
    ipfs_pyproject = cls._safe_read_toml_file(cls._ipfs_project_file(ipfs_root))
    skill_asset_manifest = cls._build_mike_skill_asset_manifest()
    frontend_src = mike_root / "frontend" / "src"
    backend_src = mike_root / "backend" / "src"
    editor_modules = [
        "frontend/src/app/components/projects/ProjectWorkspace.tsx",
        "frontend/src/app/components/projects/ProjectDocumentsView.tsx",
        "frontend/src/app/components/assistant/CaseLawPanel.tsx",
        "frontend/src/app/components/shared/views/DocxView.tsx",
        "frontend/src/app/lib/mikeApi.ts",
        "backend/src/routes/documents.ts",
        "backend/src/routes/chat.ts",
        "backend/src/routes/caseLaw.ts",
        "backend/src/lib/mcp/client.ts",
    ]
    existing_editor_modules = [path for path in editor_modules if (mike_root / path).is_file()]
    editor_module_inventory = [
        {"path": path, "path_found": (mike_root / path).is_file()}
        for path in editor_modules
    ]
    return {
        "strategy": {
            "mike": "external/mike@origin/main",
            "ipfs_datasets_py": "external/ipfs_datasets_py@origin/main",
            "ipfs_accelerate_py": "external/ipfs_accelerate_py@origin/main",
            "ipfs_kit_py": "external/ipfs_kit_py@origin/main",
            "workspace_adapters": "promote_stable_contracts_inside_complaint_generator",
            "editor_assets_decoupled_from_legal_processors": True,
        },
        "mike": {
            "available": mike_root.is_dir() and (mike_root / "README.md").exists(),
            "root": str(mike_root),
            "commit": cls._safe_read_git_ref(mike_root, "HEAD"),
            "origin_main_commit": cls._safe_read_git_ref(mike_root, "origin/main"),
            "frontend_package_name": str(mike_frontend_package.get("name") or ""),
            "backend_package_name": str(mike_backend_package.get("name") or ""),
            "frontend_dependencies": sorted(dict(mike_frontend_package.get("dependencies") or {}).keys())[:20],
            "backend_dependencies": sorted(dict(mike_backend_package.get("dependencies") or {}).keys())[:20],
            "editor_modules": existing_editor_modules,
            "editor_module_inventory": editor_module_inventory,
            "editor_module_count": len(existing_editor_modules),
            "skill_assets": deepcopy(skill_asset_manifest.get("assets") or []),
            "skill_asset_count": int(skill_asset_manifest.get("asset_count") or 0),
            "skill_asset_manifest_version": str(skill_asset_manifest.get("version") or ""),
            "upgrade_path": [
                "refresh_submodule",
                "recompute_compatibility_matrix",
                "verify_mike_contract_tests",
                "re-run_release_gate_regression",
            ],
        },
        "ipfs_datasets_py": {
            "available": ipfs_root.is_dir() and (ipfs_root / "README.md").exists(),
            "root": str(ipfs_root),
            "commit": cls._safe_read_git_ref(ipfs_root, "HEAD"),
            "origin_main_commit": cls._safe_read_git_ref(ipfs_root, "origin/main"),
            "python_project_name": str(((ipfs_pyproject.get("project") or {}).get("name") or "")),
            "logic_bridge_present": (ipfs_root / "ipfs_datasets_py" / "logic").exists(),
            "legal_processors_present": (ipfs_root / "ipfs_datasets_py" / "processors" / "legal_data").exists(),
            "theorem_bridge_present": (ipfs_root / "ipfs_datasets_py" / "logic" / "external_provers").exists(),
            "legal_search_sources": _legal_source_availability_snapshot(),
            "upgrade_path": [
                "refresh_submodule",
                "verify_adapter_imports",
                "run_workspace_logic_regression",
                "re-run_strict_grounding_tests",
            ],
        },
        "ipfs_accelerate_py": {
            "available": accelerate_root.is_dir() and (accelerate_root / "README.md").exists(),
            "root": str(accelerate_root),
            "commit": cls._safe_read_git_ref(accelerate_root, "HEAD"),
            "origin_main_commit": cls._safe_read_git_ref(accelerate_root, "origin/main"),
        },
        "ipfs_kit_py": {
            "available": kit_root.is_dir() and (kit_root / "README.md").exists(),
            "root": str(kit_root),
            "commit": cls._safe_read_git_ref(kit_root, "HEAD"),
            "origin_main_commit": cls._safe_read_git_ref(kit_root, "origin/main"),
        },
        "workspace_adapter_boundary": {
            "router_adapter": "integrations/ipfs_datasets/llm.py",
            "legal_adapter": "integrations/ipfs_datasets/legal.py",
            "logic_adapter": "integrations/ipfs_datasets/logic.py",
            "storage_adapter": "integrations/ipfs_datasets/storage.py",
            "graph_adapter": "integrations/ipfs_datasets/graphs.py",
            "multimedia_adapter": "integrations/ipfs_datasets/multimedia.py",
            "accelerate_router_facade": "integrations/ipfs_accelerate/routers.py",
            "workspace_contract_owner": "applications/complaint_workspace.py",
        },
    }

def _normalize_mike_sync_provenance(
    cls,
    sync_provenance: Optional[Mapping[str, Any]],
    *,
    base_draft_identity: Optional[Mapping[str, Any]] = None,
    redline_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(sync_provenance or {})
    skill_asset_ids = [
        str(value).strip()
        for value in list(payload.get("skill_asset_ids") or payload.get("enabled_skill_ids") or [])
        if str(value).strip()
    ]
    known_skill_asset_ids = set(cls._build_mike_skill_asset_manifest().get("asset_ids") or [])
    enabled_skill_ids = [value for value in skill_asset_ids if value in known_skill_asset_ids]
    unknown_skill_asset_ids = [value for value in skill_asset_ids if value not in known_skill_asset_ids]
    base_identity = dict(base_draft_identity or {})
    payload_base_identity = payload.get("base_draft_identity")
    if isinstance(payload_base_identity, Mapping):
        base_identity.update(dict(payload_base_identity))
    base_draft_hash = str(payload.get("base_draft_hash") or base_identity.get("hash") or "").strip() or None
    normalized_redline_metadata = dict(redline_metadata or {})
    payload_redline_metadata = payload.get("redline_metadata")
    if isinstance(payload_redline_metadata, Mapping):
        normalized_redline_metadata.update(dict(payload_redline_metadata))
    return {
        "editor_version": str(payload.get("editor_version") or "").strip() or None,
        "skill_asset_ids": skill_asset_ids,
        "enabled_skill_ids": enabled_skill_ids,
        "unknown_skill_asset_ids": unknown_skill_asset_ids,
        "skill_asset_manifest_version": MIKE_SKILL_ASSET_MANIFEST_VERSION,
        "base_draft_hash": base_draft_hash,
        "base_draft_identity": {
            "title": str(base_identity.get("title") or "").strip() or None,
            "updated_at": str(base_identity.get("updated_at") or "").strip() or None,
            "draft_strategy": str(base_identity.get("draft_strategy") or "").strip() or None,
            "sync_source": str(base_identity.get("sync_source") or "").strip() or None,
            "hash": base_draft_hash,
        },
        "redline_metadata": {
            "summary": str(normalized_redline_metadata.get("summary") or "").strip() or None,
            "structured_delta_count": int(normalized_redline_metadata.get("structured_delta_count") or 0),
            "has_structured_redlines": bool(normalized_redline_metadata.get("has_structured_redlines")),
        },
        "source_transport": str(payload.get("source_transport") or "").strip() or None,
        "upstream_project": str(payload.get("upstream_project") or "mike").strip(),
    }

def _summarize_mike_evidence_context(state: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    evidence = dict(state.get("evidence") or {})
    testimony = list(evidence.get("testimony") or [])
    documents = list(evidence.get("documents") or [])
    support_matrix = list((review or {}).get("support_matrix") or [])
    testimony_by_element: Dict[str, List[Dict[str, Any]]] = {}
    for item in testimony:
        element_id = str((item or {}).get("claim_element_id") or "").strip()
        if not element_id:
            continue
        testimony_by_element.setdefault(element_id, []).append(item)
    documents_by_element: Dict[str, List[Dict[str, Any]]] = {}
    for item in documents:
        element_id = str((item or {}).get("claim_element_id") or "").strip()
        if not element_id:
            continue
        documents_by_element.setdefault(element_id, []).append(item)
    evidence_by_element: Dict[str, Dict[str, Any]] = {}
    for element in support_matrix:
        element_id = str((element or {}).get("id") or "").strip()
        if not element_id:
            continue
        matching_testimony = list(testimony_by_element.get(element_id) or [])
        matching_documents = list(documents_by_element.get(element_id) or [])
        samples = [
            str((item or {}).get("title") or "").strip()
            for item in (matching_testimony + matching_documents)
            if str((item or {}).get("title") or "").strip()
        ][:3]
        evidence_by_element[element_id] = {
            "label": str((element or {}).get("label") or element_id),
            "supported": bool((element or {}).get("supported")),
            "testimony_count": len(matching_testimony),
            "document_count": len(matching_documents),
            "sample_titles": samples,
        }
    return {
        "testimony_count": len(testimony),
        "document_count": len(documents),
        "elements": evidence_by_element,
        "missing_element_ids": [
            str((element or {}).get("id") or "").strip()
            for element in support_matrix
            if not bool((element or {}).get("supported"))
        ],
    }

def _build_mike_reasoning_predicates(
    *,
    state: Mapping[str, Any],
    review: Mapping[str, Any],
    assertion_annotations: List[Dict[str, Any]],
    authority_links: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    claim_type = str(review.get("claim_type") or state.get("claim_type") or "retaliation")
    support_matrix = list((review or {}).get("support_matrix") or [])
    predicates: List[Dict[str, Any]] = []
    for item in support_matrix:
        element_id = str((item or {}).get("id") or "").strip()
        label = str((item or {}).get("label") or element_id).strip()
        if not element_id:
            continue
        predicates.append(
            {
                "predicate_id": f"claim-{element_id}",
                "predicate_text": label,
                "predicate_type": "claim_element",
                "claim_type": claim_type,
                "claim_element_id": element_id,
                "claim_element_text": label,
                "coverage_status": "supported" if bool((item or {}).get("supported")) else "missing",
            }
        )
    authority_ids = {item["authority_id"] for item in authority_links if item.get("authority_id")}
    for index, item in enumerate(assertion_annotations, start=1):
        assertion_type = str(item.get("assertion_type") or "factual_statement").strip()
        predicate_type = {
            "factual_statement": "support_trace",
            "legal_conclusion": "claim_element",
            "temporal_assertion": "temporal_fact",
            "requested_relief": "support_trace",
            "unsupported_rhetoric": "contradiction_candidate",
        }.get(assertion_type, "support_trace")
        predicate: Dict[str, Any] = {
            "predicate_id": str(item.get("assertion_id") or f"assertion-{index:03d}"),
            "predicate_text": str(item.get("text") or "").strip(),
            "predicate_type": predicate_type,
            "claim_type": claim_type,
            "authority_ids": [value for value in list(item.get("authority_ids") or []) if value in authority_ids] or list(item.get("authority_ids") or []),
            "grounded_fact_ids": list(item.get("fact_ids") or []),
        }
        if predicate_type == "support_trace":
            predicate["support_ref"] = str(item.get("paragraph_id") or predicate["predicate_id"])
            predicate["support_kind"] = assertion_type
            predicate["text"] = predicate["predicate_text"]
        elif predicate_type == "temporal_fact":
            predicate["fact_id"] = str(item.get("assertion_id") or predicate["predicate_id"])
            predicate["text"] = predicate["predicate_text"]
            predicate["start_date"] = str(item.get("start_date") or "").strip() or None
            predicate["end_date"] = str(item.get("end_date") or "").strip() or None
        elif predicate_type == "claim_element":
            predicate["claim_element_id"] = str(item.get("claim_element_id") or "edited_claim").strip()
            predicate["claim_element_text"] = predicate["predicate_text"]
            predicate["coverage_status"] = "supported" if bool(item.get("grounded")) else "missing"
        else:
            predicate["summary"] = predicate["predicate_text"]
            predicate["severity"] = "warning" if bool(item.get("unsupported")) else "info"
        predicates.append(predicate)
    return predicates

def _build_mike_logic_review(
    cls,
    *,
    state: Mapping[str, Any],
    review: Mapping[str, Any],
    assertion_annotations: List[Dict[str, Any]],
    authority_links: List[Dict[str, Any]],
) -> Dict[str, Any]:
    reasoning_payload = {
        "predicates": cls._build_mike_reasoning_predicates(
            state=state,
            review=review,
            assertion_annotations=assertion_annotations,
            authority_links=authority_links,
        ),
        "claim_support_temporal_handoff": cls._build_claim_support_temporal_handoff_from_review(state, review),
        "claim_reasoning_review": {
            str(review.get("claim_type") or state.get("claim_type") or "retaliation"): {
                "unsupported_claim_elements": [
                    str((item or {}).get("id") or "").strip()
                    for item in list((review or {}).get("support_matrix") or [])
                    if str((item or {}).get("id") or "").strip() and not bool((item or {}).get("supported"))
                ]
            }
        },
    }
    hybrid_reasoning = _run_hybrid_reasoning_safely(reasoning_payload)
    temporal_reasoning_payload = dict(hybrid_reasoning.get("temporal_reasoning_payload") or {})
    result = dict(hybrid_reasoning.get("result") or {})
    proof_artifact = dict(result.get("proof_artifact") or {})
    contradiction_count = int(result.get("contradiction_signal_count") or 0)
    chronology_blocked = bool(dict(result.get("theorem_export_metadata") or {}).get("chronology_blocked"))
    unsupported_claim_elements = list(
        (reasoning_payload.get("claim_reasoning_review") or {})
        .get(str(review.get("claim_type") or state.get("claim_type") or "retaliation"), {})
        .get("unsupported_claim_elements", [])
    )
    proof_status = str(proof_artifact.get("proof_status") or proof_artifact.get("status") or "needs_review")
    has_blockers = bool(
        unsupported_claim_elements
        or contradiction_count
        or chronology_blocked
        or proof_status in {"error", "failed", "violation", "needs_review"}
    )
    theorem_export_metadata = deepcopy(result.get("theorem_export_metadata") or {})
    leanstral_status = _leanstral_status_snapshot()
    leanstral_assist = {
        "eligible": has_blockers,
        "status": (
            "ready"
            if has_blockers and bool(leanstral_status.get("backend_available"))
            else "not_needed"
            if not has_blockers
            else "unavailable"
        ),
        "provider": str(leanstral_status.get("provider") or "ipfs_accelerate_py"),
        "model": str(leanstral_status.get("model") or "leanstral"),
        "bypass_release_gate": False,
        "proof_objectives": list(theorem_export_metadata.get("temporal_proof_objectives") or []),
        "unresolved_claim_element_ids": unsupported_claim_elements,
        "proposed_steps": [
            f"Ground unsupported claim element `{claim_id}` with authority-backed proof predicates."
            for claim_id in unsupported_claim_elements[:3]
        ]
        + (
            ["Resolve chronology blockers before retrying theorem export."]
            if chronology_blocked
            else []
        )
        + (
            ["Review contradiction candidates before requesting additional prover assistance."]
            if contradiction_count
            else []
        ),
    }
    return {
        "reasoning_payload": reasoning_payload,
        "hybrid_reasoning": hybrid_reasoning,
        "proof_status": proof_status,
        "proof_passed": not has_blockers and proof_status not in {"error", "failed", "violation"},
        "contradiction_count": contradiction_count,
        "chronology_blocked": chronology_blocked,
        "unsupported_claim_element_count": len(unsupported_claim_elements),
        "unsupported_claim_element_ids": unsupported_claim_elements,
        "temporal_formula_count": int(temporal_reasoning_payload.get("tdfol_formula_count") or 0),
        "dcec_formula_count": int(temporal_reasoning_payload.get("dcec_formula_count") or 0),
        "has_blockers": has_blockers,
        "theorem_export_metadata": theorem_export_metadata,
        "proof_artifact": proof_artifact,
        "leanstral_assist": leanstral_assist,
    }

def _check_mike_citation_links(
    self,
    state: Dict[str, Any],
    citation_links: List[Dict[str, Any]],
    *,
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate Mike citation links against claim elements and detect citation conflicts.

    Args:
        state: Current workspace state payload.
        citation_links: Citation-link objects supplied on Mike sync.
        review: Optional precomputed review payload to avoid recomputing support_matrix.

    Returns:
        Dict with total link count, known/unknown claim elements, per-citation conflicts,
        and an aggregate has_conflicts boolean.
    """
    review_payload = dict(review or {})
    if not review_payload:
        review_payload = self._build_review(state)
    support_matrix = list((review_payload or {}).get("support_matrix") or [])

    known_element_ids: Set[str] = set()
    for item in support_matrix:
        element_id = str((item or {}).get("id") or "").strip()
        if element_id:
            known_element_ids.add(element_id)
    normalized_links = self._normalize_mike_citation_links(citation_links)
    unknown_claim_element_ids: Set[str] = set()
    for item in normalized_links:
        claim_element_id = self._extract_mike_claim_element_id(item)
        if claim_element_id and claim_element_id not in known_element_ids:
            unknown_claim_element_ids.add(claim_element_id)
    citation_to_elements: Dict[str, Set[str]] = {}
    for item in normalized_links:
        citation_key = self._extract_mike_citation_key(item)
        claim_element_id = self._extract_mike_claim_element_id(item)
        if not citation_key or not claim_element_id:
            continue
        citation_to_elements.setdefault(citation_key, set()).add(claim_element_id)
    conflicts = [
        {
            "citation_id": citation_id,
            # Keep deterministic claim-element ordering for tests and downstream diffs.
            "claim_element_ids": sorted(claim_element_ids),
        }
        for citation_id, claim_element_ids in sorted(citation_to_elements.items())
        if len(claim_element_ids) > 1
    ]
    return {
        "total_links": len(normalized_links),
        "known_claim_element_ids": sorted(known_element_ids),
        "unknown_claim_element_ids": sorted(unknown_claim_element_ids),
        "conflicts": conflicts,
        "has_conflicts": bool(conflicts or unknown_claim_element_ids),
    }

def _build_mike_sync_diagnostics(
    *,
    citation_link_check: Mapping[str, Any],
    review_payload: Mapping[str, Any],
    structured_deltas: List[Dict[str, Any]],
    legal_corpus_review: Mapping[str, Any],
    logic_review: Mapping[str, Any],
) -> Dict[str, Any]:
    conflict_count = len(list((citation_link_check or {}).get("conflicts") or []))
    unknown_count = len(list((citation_link_check or {}).get("unknown_claim_element_ids") or []))
    overview = dict((review_payload or {}).get("overview") or {})
    missing_count = int(overview.get("missing_elements") or 0)
    corpus_review = dict(legal_corpus_review or {})
    reasoning_review = dict(logic_review or {})
    unsupported_assertion_count = int(corpus_review.get("unsupported_assertion_count") or 0)
    extra_corpus_assertion_count = int(corpus_review.get("extra_corpus_assertion_count") or 0)
    contradiction_count = int(reasoning_review.get("contradiction_count") or 0)
    chronology_blocked = bool(reasoning_review.get("chronology_blocked"))
    proof_status = str(reasoning_review.get("proof_status") or "needs_review")
    theorem_check_state = ComplaintWorkspaceService._derive_mike_theorem_export_check_state(
        missing_count=missing_count,
        contradiction_count=contradiction_count,
        chronology_blocked=chronology_blocked,
        proof_status=proof_status,
    )
    sync_state = ComplaintWorkspaceService._derive_mike_sync_overall_state(
        conflict_count=conflict_count,
        unknown_count=unknown_count,
        corpus_has_blockers=bool(corpus_review.get("has_blockers")),
        chronology_blocked=chronology_blocked,
        contradiction_count=contradiction_count,
        missing_count=missing_count,
        unsupported_assertion_count=unsupported_assertion_count,
        proof_status=proof_status,
    )
    diagnostics = [
        {
            "id": "citation_link_integrity",
            "severity": "error" if (conflict_count or unknown_count) else "info",
            "status": "failed" if (conflict_count or unknown_count) else "passed",
            "message": (
                f"Detected {conflict_count} citation-link conflict(s) and {unknown_count} unknown claim element link(s)."
                if (conflict_count or unknown_count)
                else "Citation-link integrity check passed."
            ),
            "remediation": "Resolve conflicts in Mike and sync again."
            if (conflict_count or unknown_count)
            else "No action required.",
        },
        {
            "id": "corpus_grounding_coverage",
            "severity": "error" if bool(corpus_review.get("has_blockers")) else ("warning" if unsupported_assertion_count else "info"),
            "status": "failed" if bool(corpus_review.get("has_blockers")) else ("needs_review" if unsupported_assertion_count else "passed"),
            "message": (
                f"Legal-corpus grounding covers {int(corpus_review.get('coverage_percent') or 0)}% of substantive assertions with "
                f"{unsupported_assertion_count} unsupported and {extra_corpus_assertion_count} extra-corpus assertion(s)."
            ),
            "remediation": "Ground each substantive legal assertion in ipfs_datasets_py legal authority results before export.",
        },
        {
            "id": "claim_proof_coverage",
            "severity": "warning" if missing_count else "info",
            "status": "needs_review" if missing_count else "passed",
            "message": (
                f"Support review still reports {missing_count} missing claim element(s)."
                if missing_count
                else "Support review reports complete claim-element coverage."
            ),
            "remediation": "Collect additional corroboration before export." if missing_count else "No action required.",
        },
        {
            "id": "theorem_export_compatibility",
            "severity": str(theorem_check_state.get("severity") or "warning"),
            "status": str(theorem_check_state.get("status") or "needs_review"),
            "message": (
                f"Theorem/export compatibility reports proof_status={proof_status}, contradiction_count={contradiction_count}, chronology_blocked={chronology_blocked}."
                if bool(theorem_check_state.get("needs_review"))
                else "No proof-gap regressions detected for theorem/export compatibility."
            ),
            "remediation": "Run complaint.review_case and complaint.get_client_release_gate before filing.",
        },
    ]
    normalized_invalid_op_count = sum(
        1
        for item in structured_deltas
        if bool(dict(item.get("metadata") or {}).get("normalized_from_invalid_op"))
    )
    return {
        "severity": str(sync_state.get("severity") or "warning"),
        "has_blockers": bool(sync_state.get("has_blockers")),
        "checks": diagnostics,
        "structured_delta_count": len(structured_deltas),
        "normalized_invalid_op_count": normalized_invalid_op_count,
        "grounding_coverage_percent": int(corpus_review.get("coverage_percent") or 0),
        "proof_status": proof_status,
        "contradiction_count": contradiction_count,
    }

def get_mike_integration_status(self, user_id: Optional[str]) -> Dict[str, Any]:
    state = self._load_state(str(user_id or DEFAULT_USER_ID))
    mike_integration = dict(state.get("mike_integration") or {})
    last_handoff = dict(mike_integration.get("last_handoff") or {})
    last_sync = dict(mike_integration.get("last_sync") or {})
    handoff_history = [dict(item) for item in list(mike_integration.get("handoff_history") or []) if isinstance(item, dict)]
    sync_history = [dict(item) for item in list(mike_integration.get("sync_history") or []) if isinstance(item, dict)]
    draft = dict(state.get("draft") or {})
    draft_sync_source = str(draft.get("sync_source") or "").strip().lower()
    has_mike_synced_draft = draft_sync_source == "mike" and bool(str(draft.get("body") or "").strip())
    draft_updated_at_raw = str(draft.get("updated_at") or "").strip()
    latest_sync_timestamp_raw = str(last_sync.get("synced_at") or "").strip()
    if has_mike_synced_draft and draft_updated_at_raw and latest_sync_timestamp_raw:
        try:
            draft_updated_at = datetime.fromisoformat(draft_updated_at_raw)
            latest_sync_timestamp = datetime.fromisoformat(latest_sync_timestamp_raw)
            # Equality is intentional because Mike sync writes both timestamps in one operation.
            # If they differ, the draft changed after sync and should no longer be treated as current.
            has_mike_synced_draft = draft_updated_at == latest_sync_timestamp
        except ValueError:
            has_mike_synced_draft = draft_updated_at_raw == latest_sync_timestamp_raw
    draft_sync_metadata = dict(draft.get("sync_metadata") or {})
    raw_citation_link_check = dict(draft_sync_metadata.get("citation_link_check") or {})
    has_citation_link_conflicts = bool(raw_citation_link_check.get("has_conflicts"))
    citation_link_conflict_count = len(list(raw_citation_link_check.get("conflicts") or []))
    citation_link_unknown_element_count = len(list(raw_citation_link_check.get("unknown_claim_element_ids") or []))
    legal_corpus_review = dict(draft_sync_metadata.get("legal_corpus_review") or {})
    logic_review = dict(draft_sync_metadata.get("logic_review") or {})
    router_policy = dict(draft_sync_metadata.get("router_policy") or self._build_mike_router_policy_snapshot())
    latest_handoff_id = str(last_handoff.get("handoff_id") or "").strip()
    latest_sync_handoff_id = str(last_sync.get("handoff_id") or "").strip()
    # When latest_sync_handoff_id is empty, no Mike sync has been persisted yet for this session.
    pending_sync = bool(latest_handoff_id) and latest_handoff_id != latest_sync_handoff_id
    workflow_state = self._build_mike_workflow_state(
        latest_handoff_id=latest_handoff_id,
        pending_sync=pending_sync,
        has_mike_synced_draft=has_mike_synced_draft,
        has_citation_link_conflicts=has_citation_link_conflicts,
    )
    recommended_action = self._derive_mike_recommended_action(
        workflow_state_key=workflow_state["key"],
        has_citation_link_conflicts=has_citation_link_conflicts,
    )
    pending_sync_implies_handoff = (not pending_sync) or bool(latest_handoff_id)
    synced_handoff_never_pending = not (
        bool(latest_handoff_id)
        and latest_handoff_id == latest_sync_handoff_id
        and pending_sync
    )
    conflict_count_non_null = isinstance(citation_link_conflict_count, int) and citation_link_conflict_count >= 0
    unknown_count_non_null = isinstance(citation_link_unknown_element_count, int) and citation_link_unknown_element_count >= 0
    recommended_action_valid = bool(str(recommended_action or "").strip())
    conflict_component = {
        "conflict_count": int(citation_link_conflict_count),
        "unknown_element_count": int(citation_link_unknown_element_count),
        "impact_statement": (
            "Export readiness is blocked until Mike citation-link conflicts are resolved and synced again."
            if has_citation_link_conflicts
            else "No citation-link blockers are currently reported."
        ),
        "required_next_action": recommended_action,
        "why_blocked": (
            "Citation-link integrity checks found conflicts or unknown claim elements."
            if has_citation_link_conflicts
            else ""
        ),
    }
    grounding_component = {
        "grounding_mode": str(draft_sync_metadata.get("grounding_mode") or self._resolve_mike_grounding_mode()).strip(),
        "coverage_percent": int(legal_corpus_review.get("coverage_percent") or 0),
        "unsupported_assertion_count": int(legal_corpus_review.get("unsupported_assertion_count") or 0),
        "extra_corpus_assertion_count": int(legal_corpus_review.get("extra_corpus_assertion_count") or 0),
        "weak_grounding_count": int(legal_corpus_review.get("weak_grounding_count") or 0),
        "has_blockers": bool(legal_corpus_review.get("has_blockers")),
        "impact_statement": (
            "Strict legal-corpus containment is blocking export until unsupported or extra-corpus assertions are grounded."
            if bool(legal_corpus_review.get("has_blockers"))
            else "No strict legal-corpus grounding blockers are currently reported."
        ),
    }
    proof_component = {
        "proof_status": str(logic_review.get("proof_status") or "needs_review"),
        "proof_passed": bool(logic_review.get("proof_passed")),
        "contradiction_count": int(logic_review.get("contradiction_count") or 0),
        "chronology_blocked": bool(logic_review.get("chronology_blocked")),
        "unsupported_claim_element_count": int(logic_review.get("unsupported_claim_element_count") or 0),
        "has_blockers": bool(logic_review.get("has_blockers")),
        "impact_statement": (
            "Formal proof or chronology checks are blocking export until Mike edits preserve claim coverage."
            if bool(logic_review.get("has_blockers"))
            else "No formal proof blockers are currently reported."
        ),
    }
    return {
        "user_id": str(state.get("user_id") or DEFAULT_USER_ID),
        "status": "ok",
        "status_contract_version": MIKE_STATUS_CONTRACT_VERSION,
        "status_contract": {
            "version": MIKE_STATUS_CONTRACT_VERSION,
            "canonical_source": "/api/complaint-workspace/mike/status",
            "state_mapping": deepcopy(MIKE_WORKFLOW_STATE_LABELS),
        },
        "last_handoff": last_handoff or None,
        "last_sync": last_sync or None,
        "handoff_history_count": len(handoff_history),
        "sync_history_count": len(sync_history),
        "latest_handoff_id": latest_handoff_id or None,
        "latest_sync_handoff_id": latest_sync_handoff_id or None,
        "pending_sync": pending_sync,
        "workflow_state": workflow_state,
        "has_mike_synced_draft": has_mike_synced_draft,
        "has_citation_link_conflicts": has_citation_link_conflicts,
        "citation_link_conflict_count": citation_link_conflict_count,
        "citation_link_unknown_element_count": citation_link_unknown_element_count,
        "conflict_component": conflict_component,
        "grounding_component": grounding_component,
        "proof_component": proof_component,
        "router_policy": router_policy,
        "draft_sync_source": draft_sync_source or None,
        "recommended_action": recommended_action,
        "invariants": {
            "pending_sync_implies_handoff": pending_sync_implies_handoff,
            "synced_handoff_never_pending": synced_handoff_never_pending,
            "conflict_counters_non_null_numeric": bool(conflict_count_non_null and unknown_count_non_null),
            "recommended_action_present": recommended_action_valid,
        },
        "status_freshness": {
            "last_handoff_at": str(last_handoff.get("created_at") or "").strip() or None,
            "last_sync_at": str(last_sync.get("synced_at") or "").strip() or None,
            "latest_status_observed_at": _utc_now(),
        },
    }

