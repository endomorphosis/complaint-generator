"""Research and shared-interview methods delegated from ComplaintWorkspaceService."""

from __future__ import annotations

from applications.complaint_workspace import (
    DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN,
    DEFAULT_USER_ID,
    WorkspacePersistenceError,
    _llm_draft_timeout_for_provider,
    _narrative_record,
    _preserve_adaptive_gap,
    _require_ipfs_attr,
    _state_case_id,
    deepcopy,
    format_legal_research_result,
    hashlib,
    json,
    os,
    re,
    shutil,
    uuid,
)


def apply_shared_interview(
    self,
    state: Dict[str, Any],
    *,
    message: Optional[str],
    question_id: Optional[str],
    expected_question_revision: Optional[int],
    interview_action: Optional[str],
    narrative_turn: bool,
) -> Dict[str, Any]:
    """Delegate narrative start, graph answers, and resume to one mediator transition."""
    user_id = str(state.get("user_id") or DEFAULT_USER_ID)
    case_id = _state_case_id(state, user_id)
    self._check_access(user_id, ability="write", case_id=case_id, record_case_id=case_id)
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else None
    action = str(interview_action or "").strip().lower()
    graph_question = str(question_id or "").startswith("inq-")
    should_run = bool(narrative_turn or graph_question or action in {"resume", "status", "start", "answer"} or projection)
    if not should_run:
        return {
            "contract_version": "interview-transition-v1",
            "action": "deferred",
            "status": "awaiting_user",
            "awaiting_user": True,
            "legal_sufficiency": False,
            "error": None,
        }
    try:
        # GUI mutations operate on the authenticated DTO in this request.
        # A refused publication must not leave an advanced mediator in the
        # process cache and turn the next legitimate retry into stale input.
        mediator = (self._mediator_for_shared_interview(user_id, case_id, cache=False)
            if self._owner_case_authority() is not None
            else self._mediator_for_shared_interview(user_id, case_id))
        begin_router = getattr(mediator, "begin_intake_router_action", None)
        if callable(begin_router):
            previous_router = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
            router_session = str(previous_router.get("session_id") or "")
            if not re.fullmatch(r"[0-9a-f]{32}", router_session):
                router_session = uuid.uuid4().hex
            begin_router(owner_id=user_id, case_id=case_id, session_id=router_session,
                         revision=int((projection or {}).get("session_revision") or 0), previous=previous_router)
        kwargs: Dict[str, Any] = {
            "privacy_policy": state.get("privacy_policy"),
            "user_id": user_id,
            "case_id": case_id,
        }
        # Rehydrate first, then apply this same request. A cold answer is
        # never silently consumed as a resume-only operation.
        if projection and not mediator.workflow_actions.interview_started:
            restored = mediator.transition_shared_interview(action="resume", session_projection=projection, **kwargs)
            if restored.get("error"):
                return restored
        prior_pending = None
        legal_snapshot = None
        if graph_question or action == "answer":
            current_projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
            current_pending = current_projection.get("pending_inquiry") if isinstance(current_projection.get("pending_inquiry"), dict) else None
            prior_pending = dict(current_pending) if current_pending else None
            if isinstance(current_projection.get("dependency_graph"), dict):
                legal_snapshot = deepcopy(current_projection.get("dependency_graph"))
        if action == "resume":
            receipt = mediator.transition_shared_interview(action="resume", **kwargs)
        elif narrative_turn or action == "start":
            receipt = mediator.transition_shared_interview(
                action="start",
                narrative=message or _narrative_record(state).get("text"),
                **kwargs,
            )
        elif graph_question or action == "answer":
            receipt = mediator.transition_shared_interview(
                action="answer",
                answer=message,
                inquiry_id=question_id,
                expected_question_revision=expected_question_revision,
                **kwargs,
            )
        else:
            receipt = mediator.transition_shared_interview(action="status", **kwargs)
        # Refusals are authoritative and have no accepted transition to
        # publish. In particular, an older provider-stage error must not
        # replace a stale-question receipt or change its saved projection.
        if receipt.get("status") == "refused":
            return receipt
        exported = mediator.workflow_actions.export_session_projection()
        if isinstance(exported, dict) and legal_snapshot is not None:
            exported["dependency_graph"] = legal_snapshot
        if exported:
            state["shared_interview"] = exported
            pending = exported.get("pending_inquiry") if isinstance(exported.get("pending_inquiry"), dict) else None
            if isinstance(pending, dict):
                state["explained_inquiry"] = {
                    key: pending.get(key)
                    for key in (
                        "inquiry_id",
                        "objective_id",
                        "target_id",
                        "target_revision",
                        "why_it_matters",
                        "expected_answer_contract",
                        "expected_update_contract",
                        "source_references",
                        "source_references_status",
                        "grounding_status",
                        "question",
                    )
                }
        snapshot_router = getattr(mediator, "intake_router_snapshot", None)
        if callable(snapshot_router):
            snapshot = snapshot_router()
            previous_router = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
            prior_receipts = []
            association_keys = {
                "schema", "invocation_label", "purpose", "case_id", "session_id",
                "accepted_graph_revision", "live_model_identity_verified", "prompt_logged",
                "provider_replayed",
            }
            for item in previous_router.get("receipts") or []:
                if not isinstance(item, dict):
                    continue
                keys = set(item)
                core = {"operation", "request_id", "binding_id", "status", "intake_complete"}
                if not core <= keys or keys - core - association_keys:
                    continue
                if (item.get("operation") in {"extract_facts", "propose_questions"}
                        and item.get("status") in {"available", "privacy_denied", "provider_unavailable", "malformed_output", "quota", "timeout", "cancelled", "stale_request"}
                        and all(isinstance(item.get(key), str) and re.fullmatch(r"[0-9a-f]{32}", item[key]) for key in ("request_id", "binding_id"))
                        and (item.get("invocation_label") in {None, "real", "fake"})):
                    prior_receipts.append(dict(item))
            seen = {item["request_id"] for item in prior_receipts}
            from mediator.hook_runtime import invocation_association, invocation_label_for_receipt

            graph_payload = exported.get("knowledge_graph") if isinstance(exported, dict) else None
            accepted_revision = ""
            if isinstance(graph_payload, dict):
                try:
                    from complaint_phases.knowledge_graph import KnowledgeGraph
                    from mediator.hook_runtime import graph_revision_token
                    accepted_revision = graph_revision_token(KnowledgeGraph.from_dict(graph_payload))
                except Exception:
                    accepted_revision = ""
            backend = getattr(mediator, "_terminal_router_backend", None)
            if backend is None:
                backends = getattr(mediator, "backends", None) or []
                backend = backends[0] if backends else None
            backend_by_request = {}
            for backend_receipt in getattr(backend, "task_receipts", []) or []:
                if isinstance(backend_receipt, dict) and type(backend_receipt.get("request_id")) is str:
                    backend_by_request[backend_receipt["request_id"]] = backend_receipt
            for item in snapshot["receipts"]:
                if item["request_id"] in seen:
                    continue
                matched = backend_by_request.get(item["request_id"]) or {}
                association = invocation_association(
                    invocation_label=invocation_label_for_receipt(matched) if matched else "fake",
                    purpose=item.get("operation"),
                    request_id=item.get("request_id"),
                    case_id=case_id,
                    session_id=router_session,
                    accepted_graph_revision=accepted_revision,
                    live_model_identity_verified=bool(matched.get("live_model_identity_verified")) if matched else False,
                )
                stored = dict(item)
                stored.update(association)
                prior_receipts.append(stored)
                seen.add(item["request_id"])
            state["intake_router"] = {**snapshot, "session_id": router_session,
                                      "receipts": prior_receipts[-32:]}
            if snapshot["errors"] and not receipt.get("error"):
                # Accepted user answers and their graph effects remain in
                # this same transaction. An unresolved provider stage is
                # explicit on resume and can never establish completion.
                receipt["status"] = "awaiting_user" if receipt.get("inquiry") else "unavailable"
                receipt["awaiting_user"] = bool(receipt.get("inquiry"))
                receipt["intake_complete"] = False
                receipt["readiness"] = {"ready_to_advance": False, "legal_sufficiency": False}
                receipt["error"] = {"code": "provider_unavailable", "resumable": True,
                                    "router_failures": dict(snapshot["errors"]), "legal_sufficiency": False}
            receipt["intake_router"] = deepcopy(state["intake_router"])
        if prior_pending and receipt.get("status") != "refused":
            _preserve_adaptive_gap(state, message, prior_pending)
        return receipt
    except Exception as exc:
        return {
            "contract_version": "interview-transition-v1",
            "action": action or "status",
            "status": "unavailable",
            "awaiting_user": False,
            "legal_sufficiency": False,
            "error": {
                "code": "capability_unavailable",
                "resumable": True,
                "error_type": type(exc).__name__,
                "legal_sufficiency": False,
            },
        }
def get_provider_diagnostics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
    def _vault_value(*names: str) -> str:
        if str(os.getenv("COMPLAINT_PROVIDER_DIAGNOSTICS_CHECK_SECRETS", "") or "").strip() != "1":
            return ""
        try:
            get_secrets_vault = _require_ipfs_attr(
                "ipfs_datasets_py.mcp_server.secrets_vault",
                "get_secrets_vault",
            )

            vault = get_secrets_vault()
            for name in names:
                resolved = str(vault.get(name) or "").strip()
                if resolved:
                    return resolved
        except Exception:
            pass
        return ""

    def _keyring_value(*names: str) -> str:
        if str(os.getenv("COMPLAINT_PROVIDER_DIAGNOSTICS_CHECK_SECRETS", "") or "").strip() != "1":
            return ""
        try:
            import keyring  # type: ignore

            for name in names:
                resolved = str(keyring.get_password("ipfs_datasets_py", name) or "").strip()
                if resolved:
                    return resolved
        except Exception:
            pass
        return ""

    def _first_env(*names: str) -> str:
        for name in names:
            resolved = str(os.getenv(name, "") or "").strip()
            if resolved:
                return resolved
        return ""

    def _source_for_openai() -> str:
        if _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
            return "env"
        if _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
            return "vault"
        if _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN"):
            return "keyring"
        return "unavailable"

    def _resolve_openai_key() -> str:
        resolved = _first_env("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
        if resolved:
            return resolved

        resolved = _vault_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
        if resolved:
            return resolved

        resolved = _keyring_value("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_TOKEN")
        if resolved:
            return resolved
        return ""

    def _source_for_hf() -> str:
        if _first_env(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        ):
            return "env"
        if _vault_value(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        ):
            return "vault"
        if _keyring_value(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        ):
            return "keyring"
        return "unavailable"

    def _resolve_hf_token_for_diagnostics() -> str:
        resolved = _first_env(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        )
        if resolved:
            return resolved
        resolved = _vault_value(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        )
        if resolved:
            return resolved
        return _keyring_value(
            "IPFS_DATASETS_PY_HF_API_TOKEN",
            "HUGGINGFACEHUB_API_TOKEN",
            "HF_TOKEN",
            "HUGGINGFACE_HUB_TOKEN",
            "HUGGINGFACE_API_KEY",
            "HUGGINGFACE_API_TOKEN",
            "HF_API_TOKEN",
        )

    def _copilot_command_available(command: str) -> bool:
        parts = str(command or "").strip().split()
        if not parts:
            return False
        if parts[0] == "npx":
            return True
        return shutil.which(parts[0]) is not None

    def _copilot_supports_image_inputs_for_diagnostics() -> bool:
        explicit = str(os.getenv("IPFS_DATASETS_PY_COPILOT_CLI_SUPPORTS_IMAGE_INPUTS", "") or "").strip().lower()
        if explicit:
            return explicit in {"1", "true", "yes", "on"}
        # Avoid running `copilot --help` or `npx ... --help` here; provider diagnostics
        # must stay fast and should not spawn long-lived CLI probes from the browser UI.
        return False

    raw_default_order = [
        "codex_cli",
        "copilot_cli",
        "openai",
        "hf_inference_api",
        "openrouter",
        "gemini_cli",
        "claude_code",
        "claude_py",
        "gemini_py",
        "copilot_sdk",
    ]
    preferred_default_order = [
        "codex_cli",
        "copilot_cli",
        "openai",
        "hf_inference_api",
    ]
    default_order = [
        item
        for item in preferred_default_order
        if item in set(raw_default_order) or item in {"codex_cli", "copilot_cli", "openai", "hf_inference_api"}
    ]
    default_order.extend(
        item
        for item in raw_default_order
        if item and item not in default_order
    )
    forced_provider = str(os.getenv("IPFS_DATASETS_PY_LLM_PROVIDER", "") or "").strip()
    codex_path = shutil.which("codex") or ""
    copilot_path = shutil.which("copilot") or ""
    openai_key = _resolve_openai_key()
    copilot_command = os.getenv("IPFS_DATASETS_PY_COPILOT_CLI_CMD", "npx --yes @github/copilot -p {prompt}")
    hf_token = _resolve_hf_token_for_diagnostics()
    copilot_available = _copilot_command_available(copilot_command)
    copilot_supports_image_inputs = _copilot_supports_image_inputs_for_diagnostics()

    providers = [
        {
            "name": "codex_cli",
            "available": bool(codex_path),
            "reason": "Codex CLI is installed and available on PATH." if codex_path else "Codex CLI binary not found on PATH.",
            "binary_path": codex_path or None,
            "credential_source": "local_codex_auth" if codex_path else "unavailable",
            "supports_multimodal": bool(codex_path),
            "draft_timeout_seconds": _llm_draft_timeout_for_provider("codex_cli"),
        },
        {
            "name": "openai",
            "available": bool(openai_key),
            "reason": "OpenAI API key resolved for direct chat-completions use." if openai_key else "No OpenAI API key resolved from env, vault, keyring, or local CLI config.",
            "credential_source": _source_for_openai(),
            "base_url": str(os.getenv("IPFS_DATASETS_PY_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
            "draft_timeout_seconds": _llm_draft_timeout_for_provider("openai"),
        },
        {
            "name": "copilot_cli",
            "available": copilot_available,
            "reason": (
                "Copilot CLI command template resolved and is available."
                if copilot_available and copilot_path
                else "Copilot fallback is available through the configured command template."
                if copilot_available
                else "Copilot CLI command is not currently available on this machine."
            ),
            "binary_path": copilot_path or None,
            "supports_multimodal": bool(copilot_path),
            "supports_multimodal_ui_review": copilot_supports_image_inputs,
            "credential_source": (
                "github_copilot_cli"
                if copilot_available and copilot_path
                else "github_copilot_command_template"
                if copilot_available
                else "unavailable"
            ),
            "draft_timeout_seconds": _llm_draft_timeout_for_provider("copilot_cli"),
        },
        {
            "name": "hf_inference_api",
            "available": bool(hf_token),
            "reason": "Hugging Face token resolved for hosted inference/router use." if hf_token else "No Hugging Face token resolved from env, vault, keyring, or huggingface_hub CLI login.",
            "credential_source": _source_for_hf(),
            "base_url": str(os.getenv("IPFS_DATASETS_PY_HF_INFERENCE_BASE_URL", "https://router.huggingface.co/hf-inference/models")).rstrip("/"),
            "draft_timeout_seconds": _llm_draft_timeout_for_provider("hf_inference_api"),
            "ui_review_model": str(
                os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_HF_INFERENCE_API", "") or ""
            ).strip()
            or "Qwen/Qwen2.5-VL-7B-Instruct",
            "ui_review_timeout_seconds": _llm_draft_timeout_for_provider("hf_inference_api"),
        },
    ]

    effective_default = next((item["name"] for item in providers if item["available"]), None)
    return {
        "user_id": str(user_id or DEFAULT_USER_ID),
        "forced_provider": forced_provider or None,
        "default_order": default_order,
        "effective_default_provider": forced_provider or effective_default,
        "complaint_draft_default_order": list(DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN),
        "effective_complaint_draft_provider": (
            str(os.getenv("COMPLAINT_GENERATOR_LLM_DRAFT_PROVIDER", "") or "").strip()
            or DEFAULT_LLM_DRAFT_PROVIDER_FALLBACK_CHAIN[0]
        ),
        "ui_review_default_provider": str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_PROVIDER", "") or "").strip()
        or "codex_cli",
        "ui_review_default_model": str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_CODEX_CLI", "") or "").strip()
        or str(os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL", "") or "").strip()
        or "gpt-5.3-codex",
        "ui_review_multimodal_rate_limit_fallbacks": {
            "codex_cli": ["copilot_cli", "hf_inference_api"],
            "copilot_cli": ["hf_inference_api"],
        },
        "ui_review_hf_fallback_model": str(
            os.getenv("COMPLAINT_GENERATOR_UI_REVIEW_MODEL_HF_INFERENCE_API", "") or ""
        ).strip()
        or "Qwen/Qwen2.5-VL-7B-Instruct",
        "providers": providers,
        "summary": {
            "codex_available": bool(codex_path),
            "openai_available": bool(openai_key),
            "copilot_available": copilot_available,
            "huggingface_available": bool(hf_token),
        },
    }
def run_legal_research(
    self,
    user_id: Optional[str],
    *,
    local_rows: Optional[Dict[str, Any]] = None,
    cancelled: bool = False,
    retrieval_mode: str = "cache",
    storage_available: Optional[bool] = None,
    context_updates: Optional[Dict[str, Any]] = None,
    dependency_change: Optional[Dict[str, Any]] = None,
    effect_receipt: Optional[Dict[str, Any]] = None,
    expected_graph_revision: Optional[str] = None,
    expected_session_revision: Optional[int] = None,
) -> Dict[str, Any]:
    """Run one deliberate legal-research action for the saved case.

    Status and resume do not call this. Replaying the same action returns
    the stored receipt and does not acquire or admit again. The receipt is
    not an intake answer.
    """

    gui_authority = self._owner_case_authority()
    if gui_authority is not None:
        from applications.legal_research_api import LegalResearchError, _purpose_decision
        try:
            if context_updates or dependency_change or effect_receipt or storage_available is not None:
                raise LegalResearchError("explicit_legal_research_request_required")
            actor, selected_case = gui_authority.actor_principal_id, gui_authority.case_id
            snapshot = self.read_case_legal_research_snapshot(actor, case_id=selected_case)
            case_file = snapshot["state"]["shared_interview"]["intake_case_file"]
            claims = case_file.get("candidate_claims") or []
            claim = next((str(row.get("claim_type") or "").strip() for row in claims
                if isinstance(row, dict) and str(row.get("claim_type") or "").strip() not in {"", "unknown"}), "")
            if not claim:
                raise LegalResearchError("legal_context_not_ready")
            view = gui_authority.processing_consent(purpose="citation_acquisition", actor_principal_id=actor, workspace=self)
            generation = _purpose_decision(view, "citation_acquisition").get("generation")
            request = {"purpose": "citation_acquisition", "query": claim.replace("_", " ") + " statute",
                "retrieval_mode": retrieval_mode, "local_rows": local_rows,
                "cancelled": bool(cancelled), "max_results": 5, "max_bytes": 4096, "deadline_seconds": 5.0,
                "expected_consent_generation": generation}
            if local_rows is None:
                prior_receipt = case_file.get("legal_source_candidate_receipt") or {}
                operations = case_file.get("legal_source_operations") or {}
                prior = operations.get(prior_receipt.get("operation_id")) if isinstance(operations, dict) else None
                prior_request = prior.get("request") if isinstance(prior, dict) else None
                if (isinstance(prior_request, dict) and prior.get("source_scope_sha256") == snapshot["source_scope_sha256"]
                        and all(prior_request.get(name) == request.get(name) for name in
                            ("purpose", "query", "retrieval_mode", "cancelled", "expected_consent_generation"))):
                    # An issued /research shortcut may replay an actual
                    # owned cache request. It never reconstructs source
                    # provenance or pretends an unavailable asset exists.
                    request = deepcopy(prior_request)
            if not request.get("operation_id"):
                request["operation_id"] = hashlib.sha256(json.dumps({"source": snapshot["source_scope_sha256"],
                    "request": request}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if expected_graph_revision is not None:
                request["expected_graph_revision"] = expected_graph_revision
            if expected_session_revision is not None:
                request["expected_session_revision"] = expected_session_revision
            receipt = self.acquire_case_legal_research(actor, case_id=selected_case, request=request)
            counts = {"retrieved": int(receipt.get("candidate_count") or 0), "admitted": 0,
                "rejected": int(receipt.get("research_gap_count") or 0),
                "unavailable": int(receipt.get("status") in {"unavailable", "timeout", "error", "refused", "blocked"})}
            result = {**receipt, "action": "legal_research", "acquisition_status": receipt.get("status"),
                "admission_status": "not_admitted", "counts": counts, "proves_complaint": False,
                "stored_as_answer": False, "legal_sufficiency": False, "proof": False,
                "fingerprint": request["operation_id"], "next_action": "continue_pending_inquiry"}
            result["display"] = format_legal_research_result(result)
            return result
        except LegalResearchError as exc:
            return self._legal_research_failure(exc.code, public_status="refused")
        except WorkspacePersistenceError as exc:
            return self._legal_research_failure("stale_research" if exc.code == "revision_conflict" else exc.code,
                public_status="refused" if exc.code == "revision_conflict" else exc.public_status)

    resolved = self._check_access(str(user_id or DEFAULT_USER_ID), ability="write")
    try:
        state = self._load_state(resolved)
    except WorkspacePersistenceError as exc:
        return self._legal_research_failure(exc.code or "unavailable", public_status=exc.public_status)
    case_id = _state_case_id(state, resolved)
    narrative = _narrative_record(state)
    narrative_text = str(narrative.get("text") or "")
    claim_type = str(state.get("claim_type") or "termination")
    claims = [{"type": claim_type, "name": claim_type, "claim_type": claim_type}]
    case_file = {
        "source_complaint_text": narrative_text,
        "candidate_claims": list(claims),
    }
    storage_available = self._legal_research_storage_available() if storage_available is None else bool(storage_available)
    fingerprint = self._legal_research_fingerprint(
        case_id=case_id,
        narrative_text=narrative_text,
        claim_type=claim_type,
        local_rows=local_rows,
        storage_available=storage_available,
        cancelled=cancelled,
        retrieval_mode=retrieval_mode,
        context_updates=context_updates,
        dependency_change=dependency_change,
        effect_receipt=effect_receipt,
    )
    stored = state.get("legal_research") if isinstance(state.get("legal_research"), dict) else {}
    receipts = stored.get("receipts") if isinstance(stored.get("receipts"), dict) else {}
    stale = self._legal_research_stale(
        state,
        expected_graph_revision=expected_graph_revision,
        expected_session_revision=expected_session_revision,
    )
    if stale is not None:
        stale["fingerprint"] = fingerprint
        stale["display"] = "Stale concurrent research rejected. The pending inquiry was kept."
        return stale
    pending_operation = stored.get("pending_operation") if isinstance(stored.get("pending_operation"), dict) else None
    if (
        isinstance(pending_operation, dict)
        and pending_operation.get("fingerprint") == fingerprint
        and pending_operation.get("dispatched") is True
        and not isinstance(receipts.get(fingerprint), dict)
    ):
        receipt = self._legal_research_failure("interrupted_operation", public_status="unavailable")
        receipt["replayed"] = True
        receipt["dispatched"] = False
        receipt["fingerprint"] = fingerprint
        receipt["next_action"] = "continue_pending_inquiry"
        receipt["display"] = format_legal_research_result(receipt)
        self._store_legal_research_receipt(state, fingerprint, receipt)
        try:
            self._save_state(state)
        except WorkspacePersistenceError as exc:
            return self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
        return receipt
    previous = receipts.get(fingerprint)
    if isinstance(previous, dict):
        replay = dict(previous)
        replay["replayed"] = True
        replay["dispatched"] = False
        replay["stored_as_answer"] = False
        replay["proves_complaint"] = False
        replay["legal_sufficiency"] = False
        replay["proof"] = False
        replay["display"] = format_legal_research_result(replay)
        return replay
    answers_before = deepcopy(state.get("intake_answers") or {})
    history_before = deepcopy(state.get("intake_history") or [])
    legal_research = state.setdefault("legal_research", {})
    if not isinstance(legal_research, dict):
        legal_research = {}
        state["legal_research"] = legal_research
    legal_research["pending_operation"] = {
        "kind": "legal_research",
        "fingerprint": fingerprint,
        "status": "claimed",
        "dispatched": True,
    }
    legal_research["dispatch_count"] = int(legal_research.get("dispatch_count") or 0) + 1
    try:
        self._save_state(state)
    except WorkspacePersistenceError as exc:
        return self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
    mediator = None
    try:
        from complaint_phases.intake_case_file import apply_explicit_legal_context
        from complaint_phases.phase_manager import ComplaintPhase

        mediator = self._mediator_for_shared_interview(resolved, case_id)
        if isinstance(context_updates, dict) and context_updates:
            phase_case = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
            if isinstance(phase_case, dict) and phase_case:
                mediator.apply_explicit_legal_context(phase_case, **context_updates)
            case_file = apply_explicit_legal_context(case_file, **context_updates)
        if isinstance(effect_receipt, dict):
            mediator._pending_legal_effect_receipt = dict(effect_receipt)
        if isinstance(dependency_change, dict):
            mediator._pending_legal_dependency_change = dict(dependency_change)
        receipt = mediator.workflow_actions.research_legal_source_gap(
            user_id=resolved,
            case_id=case_id,
            intake_case_file=case_file,
            claims=claims,
            query_terms=[f"{claim_type} statute"],
            local_rows=local_rows,
            retrieval_mode=retrieval_mode,
            storage_available=storage_available,
            cancelled=cancelled,
            operation_id=fingerprint,
        )
    except WorkspacePersistenceError as exc:
        return self._legal_research_failure(exc.code or "unavailable", public_status=exc.public_status)
    except Exception:
        receipt = self._legal_research_failure("acquisition_unavailable", public_status="unavailable")
    self._legal_research_dispatch_count = int(getattr(self, "_legal_research_dispatch_count", 0) or 0) + 1
    receipt = dict(receipt)
    receipt["stored_as_answer"] = False
    receipt["proves_complaint"] = False
    receipt["legal_sufficiency"] = False
    receipt["proof"] = False
    receipt["fingerprint"] = fingerprint
    receipt["display"] = format_legal_research_result(receipt)
    refresh = None
    if mediator is not None:
        from complaint_phases.phase_manager import ComplaintPhase

        refresh = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "verified_dependency_refresh")
        pending_change = getattr(mediator, "_pending_legal_dependency_change", None)
        if isinstance(pending_change, dict) and pending_change:
            mediator._pending_legal_dependency_change = None
            if pending_change.get("source_outage") or pending_change.get("version_changed") or pending_change.get("treatment_changed") or pending_change.get("jurisdiction_changed") or pending_change.get("date_changed"):
                refresh = mediator.refresh_verified_legal_dependencies(pending_change)
    if isinstance(refresh, dict):
        receipt["dependency_refresh"] = {
            "affected_node_ids": list(refresh.get("affected_node_ids") or []),
            "preserved_node_ids": list(refresh.get("preserved_node_ids") or []),
            "case_revision": refresh.get("case_revision"),
            "atomic_case_revision": refresh.get("atomic_case_revision"),
            "source_outage": bool(refresh.get("source_outage")),
            "graph_replaced": False,
            "empty_success": False,
            "effect_request_id": refresh.get("effect_request_id") or "",
            "source_admission_reread": bool(refresh.get("source_admission_reread")),
        }
    state["intake_answers"] = answers_before
    state["intake_history"] = history_before
    self._store_legal_research_receipt(state, fingerprint, receipt)
    try:
        self._save_state(state)
    except WorkspacePersistenceError as exc:
        failed = self._legal_research_failure(exc.code or "durability_unproven", public_status=exc.public_status)
        failed["counts"] = dict(receipt.get("counts") or failed["counts"])
        failed["dispatched"] = True
        return failed
    return receipt
def _build_workspace_logic_flow(
    cls,
    formal_logic: Dict[str, Any],
    *,
    entity_query: str = "",
    document_id: str = "",
    modality: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    normalized_query = str(entity_query or "").strip().lower()
    normalized_document_id = str(document_id or "").strip()
    normalized_modality = cls._normalize_workspace_modality(modality)
    apply_modality_filter = bool(str(modality or "").strip())
    document_analyses = {
        str(key): dict(value)
        for key, value in dict(formal_logic.get("document_analyses") or {}).items()
        if isinstance(value, dict)
    }
    proof_store = dict(formal_logic.get("proof_store") or {})
    certificates = [dict(item) for item in list(proof_store.get("certificates") or []) if isinstance(item, dict)]
    certificate_by_theorem: Dict[str, List[Dict[str, Any]]] = {}
    for certificate in certificates:
        theorem = str(certificate.get("theorem") or "").strip().lower()
        if theorem:
            certificate_by_theorem.setdefault(theorem, []).append(certificate)

    rows: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    deontic_analysis: List[Dict[str, Any]] = []
    event_rows: List[Dict[str, Any]] = []
    event_flow_edges: List[Dict[str, Any]] = []
    status_counts = {"allowed": 0, "required": 0, "prohibited": 0, "conditional": 0, "unknown": 0}
    for current_document_id, analysis in document_analyses.items():
        if normalized_document_id and normalized_document_id not in current_document_id:
            continue
        statements = [dict(item) for item in list(analysis.get("deontic_statements") or []) if isinstance(item, dict)]
        frames = [dict(item) for item in list(analysis.get("frames") or []) if isinstance(item, dict)]
        events = [dict(item) for item in list(analysis.get("events") or []) if isinstance(item, dict)]
        frame_by_statement_id = {
            str((frame.get("slots") or {}).get("statement_id") or frame.get("object_id") or frame.get("frame_id") or ""): frame
            for frame in frames
        }
        for statement in statements:
            if normalized_query and normalized_query not in cls._workspace_logic_statement_text(statement):
                continue
            deontic_status = cls._normalize_workspace_modality(statement.get("modality"))
            if apply_modality_filter and deontic_status != normalized_modality:
                continue
            statement_id = str(statement.get("id") or f"{current_document_id}:statement:{len(rows) + 1}")
            action = str(statement.get("action") or "")
            entity = str(statement.get("entity") or "")
            conditions = [str(item) for item in list(statement.get("conditions") or []) if str(item or "").strip()]
            exceptions = [str(item) for item in list(statement.get("exceptions") or []) if str(item or "").strip()]
            matched_events = cls._statement_event_candidates(statement, events)
            theorem_key = action.strip().lower()
            matching_certificates = [
                dict(certificate)
                for key, theorem_certificates in certificate_by_theorem.items()
                if theorem_key and (theorem_key in key or key in theorem_key)
                for certificate in theorem_certificates[:2]
            ]
            proof_backends = sorted({str(certificate.get("backend") or "") for certificate in matching_certificates if str(certificate.get("backend") or "").strip()})
            zkp_certificate_ids = [
                str(certificate.get("certificate_id") or "")
                for certificate in matching_certificates
                if str(certificate.get("backend") or "").lower() == "groth16"
                or "groth16" in str(certificate.get("format") or "").lower()
            ]
            frame = frame_by_statement_id.get(statement_id) or {}
            rows.append(
                {
                    "document_id": current_document_id,
                    "statement_id": statement_id,
                    "entity": entity,
                    "modality": str(statement.get("modality") or ""),
                    "deontic_status": deontic_status,
                    "action": action,
                    "event_label": str((matched_events[0] if matched_events else {}).get("label") or action),
                    "conditions": conditions,
                    "exceptions": exceptions,
                    "source_text": str(statement.get("source_text") or "")[:500],
                    "frame_id": str(frame.get("frame_id") or frame.get("object_id") or ""),
                    "event_ids": [str(event.get("id") or "") for event in matched_events],
                    "proof_certificate_count": len(matching_certificates),
                    "proof_status": "proved" if matching_certificates else "unproved",
                    "proof_backends": proof_backends,
                    "zkp_certificate_ids": zkp_certificate_ids,
                    "proof_certificates": [
                        cls._compact_workspace_proof_certificate(certificate)
                        for certificate in matching_certificates[:2]
                    ],
                }
            )
            status_counts[deontic_status if deontic_status in status_counts else "unknown"] += 1
            deontic_analysis.append(
                {
                    "entity": entity,
                    "event": str((matched_events[0] if matched_events else {}).get("label") or action),
                    "status": deontic_status,
                    "modality": str(statement.get("modality") or ""),
                    "conditions": conditions,
                    "exceptions": exceptions,
                    "document_id": current_document_id,
                    "statement_id": statement_id,
                    "source_text": str(statement.get("source_text") or "")[:500],
                    "proof_certificate_count": len(matching_certificates),
                    "proof_status": "proved" if matching_certificates else "unproved",
                    "proof_backends": proof_backends,
                    "zkp_certificate_ids": zkp_certificate_ids,
                }
            )
            for event in matched_events:
                event_id = str(event.get("id") or "")
                if event_id and not any(str(item.get("id") or "") == event_id for item in event_rows):
                    event_rows.append(
                        {
                            "id": event_id,
                            "label": str(event.get("label") or ""),
                            "agent": str(event.get("agent") or ""),
                            "time": str(event.get("time") or ""),
                            "document_id": current_document_id,
                        }
                    )
            edges.extend(
                [
                    {
                        "source": current_document_id,
                        "target": statement_id,
                        "type": "EXTRACTED_STATEMENT",
                        "label": "document -> statement",
                    },
                    {
                        "source": statement_id,
                        "target": entity or "unknown_entity",
                        "type": deontic_status.upper(),
                        "label": "statement -> entity",
                    },
                ]
            )
            for event in matched_events:
                event_id = str(event.get("id") or "")
                if event_id:
                    event_flow_edges.extend(
                        [
                            {
                                "source": statement_id,
                                "target": event_id,
                                "type": "GOVERNS_EVENT",
                                "label": f"{deontic_status} event",
                            },
                            {
                                "source": entity or "unknown_entity",
                                "target": event_id,
                                "type": deontic_status.upper(),
                                "label": f"{entity or 'entity'} is {deontic_status}",
                            },
                        ]
                    )
            for index, condition in enumerate(conditions, start=1):
                event_flow_edges.append(
                    {
                        "source": f"{statement_id}:condition:{index}",
                        "target": statement_id,
                        "type": "CONDITION_FOR",
                        "label": condition,
                    }
                )
            for index, exception in enumerate(exceptions, start=1):
                event_flow_edges.append(
                    {
                        "source": f"{statement_id}:exception:{index}",
                        "target": statement_id,
                        "type": "EXCEPTION_TO",
                        "label": exception,
                    }
                )
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    conflicts = [dict(item) for item in list(formal_logic.get("deontic_conflicts") or []) if isinstance(item, dict)]
    if normalized_query:
        conflicts = [
            conflict
            for conflict in conflicts
            if normalized_query in json.dumps(conflict, ensure_ascii=False).lower()
        ]
    formulas = {
        "temporal_fol": list((formal_logic.get("temporal_fol") or {}).get("formulas") or [])[: min(limit, 20)],
        "first_order_logic": list((formal_logic.get("first_order_logic") or {}).get("formulas") or [])[: min(limit, 20)],
        "dcec": list((formal_logic.get("deontic_cognitive_event_calculus") or {}).get("formulas") or [])[: min(limit, 20)],
        "frame_logic": list(dict(formal_logic.get("frame_logic") or {}).values())[: min(limit, 20)],
    }
    logic_systems = cls._build_workspace_logic_systems(formal_logic, query=entity_query, limit=limit)
    proof_system = cls._build_workspace_proof_system(proof_store, query=entity_query, limit=limit)
    return {
        "statements": rows,
        "flow_edges": edges[: limit * 2],
        "events": event_rows[:limit],
        "event_flow_edges": event_flow_edges[: limit * 3],
        "deontic_analysis": deontic_analysis[:limit],
        "deontic_status_counts": status_counts,
        "conflicts": conflicts[: min(limit, 20)],
        "formulas": formulas,
        "logic_systems": logic_systems,
        "proof_system": proof_system,
        "returned_statement_count": len(rows),
        "returned_flow_edge_count": min(len(edges), limit * 2),
        "returned_event_count": min(len(event_rows), limit),
        "returned_event_flow_edge_count": min(len(event_flow_edges), limit * 3),
        "returned_deontic_analysis_count": min(len(deontic_analysis), limit),
        "returned_conflict_count": min(len(conflicts), min(limit, 20)),
    }
