"""Terminal graph and interview handlers delegated from the complaint workspace."""

from __future__ import annotations

from applications.complaint_workspace import (
    DEFAULT_USER_ID,
    ORIGINAL_COMPLAINT_QUESTION_ID,
    ORIGINAL_COMPLAINT_SCHEMA,
    WorkspaceAuthorizationDenied,
    WorkspacePersistenceError,
    _NARRATIVE_INQUIRY,
    _PRIVACY_MODE_NOTICE,
    _ReviewFactAcceptance,
    _append_correction_history,
    _correction_actor_ids,
    _edit_source_context,
    _eligible_correction_for_actor,
    _last_eligible_accepted_answer,
    _legal_graph_digest,
    _narrative_is_open,
    _narrative_record,
    _note_terminal_edit_controls,
    _pending_inquiry_copy,
    _privacy_helpers,
    _record_support_projection,
    _reselect_affected_pending,
    _state_case_id,
    _terminal_edit_receipt,
    deepcopy,
    format_legal_research_result,
    format_terminal_why,
    hashlib,
    json,
    re,
    uuid,
)

def apply_terminal_graph_edit(
    self,
    user_id: Optional[str],
    replacement: str,
    *,
    expected_graph_revision: Optional[str] = None,
    expected_session_revision: Optional[int] = None,
    target_stable_id: Optional[str] = None,
    actor_principal_id: Optional[str] = None,
    require_expected_revision: bool = False,
    _review_acceptance: Optional[_ReviewFactAcceptance] = None,
) -> Dict[str, Any]:
    """Correct the last eligible accepted answer on the shared factual graph.

    Display history is not a second source of truth. The public correction
    keeps the previous assertion and appends a revision. An unrelated
    pending question stays pending. A pending question bound to the corrected
    target is reopened. A stale graph or session revision is refused.
    """

    text = str(replacement or "").strip()
    if not text:
        return _terminal_edit_receipt(
            status="refused",
            message="Edit needs replacement text. The pending question is unchanged.",
            error_code="correction_required",
        )
    try:
        state = self._load_state(user_id)
    except WorkspacePersistenceError as exc:
        return _terminal_edit_receipt(
            status="unavailable",
            message=f"Edit is unavailable ({exc.code or 'unavailable'}). The pending question is unchanged.",
            error_code=str(exc.code or "unavailable"),
        )
    user = str(state.get("user_id") or user_id or DEFAULT_USER_ID)
    case_id = _state_case_id(state, user)
    actor_id, canonical_owner = _correction_actor_ids(state)
    claimed_actor = str(actor_principal_id or "").strip()
    if _review_acceptance is not None:
        if type(_review_acceptance) is not _ReviewFactAcceptance:
            raise WorkspaceAuthorizationDenied()
        _review_acceptance.check_preimage(state, workspace=self.workspace, actor=actor_id, case_id=case_id)

    def finish(receipt: Dict[str, Any]) -> Dict[str, Any]:
        receipt["actor_principal_id"] = actor_id
        receipt["canonical_owner_principal_id"] = canonical_owner
        receipt["actor_matches_canonical_owner"] = bool(canonical_owner) and actor_id == canonical_owner
        if _review_acceptance is not None and receipt.get("status") == "applied":
            receipt["review_acceptance"] = deepcopy(state["canonical_review_acceptances"][_review_acceptance.request_id])
        return receipt

    if claimed_actor and claimed_actor != actor_id:
        return finish(_terminal_edit_receipt(
            status="refused",
            message="This actor cannot edit that answer. Other participants were left unchanged.",
            error_code="unauthorized_actor",
            pending_inquiry=_pending_inquiry_copy(state),
        ))
    if require_expected_revision and (
        expected_graph_revision is None or str(expected_graph_revision).strip() == "" or expected_session_revision is None
    ):
        return finish(_terminal_edit_receipt(
            status="refused",
            message="A correction needs the expected graph and session revisions. Nothing was changed.",
            error_code="stale_target",
            pending_inquiry=_pending_inquiry_copy(state),
        ))
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else None
    before_factual = deepcopy(projection.get("knowledge_graph") or {}) if isinstance(projection, dict) else {}
    legal_snapshot = deepcopy(projection.get("dependency_graph")) if isinstance(projection, dict) and isinstance(projection.get("dependency_graph"), dict) else None
    legal_digest = _legal_graph_digest(legal_snapshot)
    if not isinstance(projection, dict) or projection.get("schema_version") != "shared-interview-session-v1":
        return _terminal_edit_receipt(
            status="unavailable",
            message="Edit is unavailable (session_missing). The pending question is unchanged.",
            error_code="session_missing",
            pending_inquiry=_pending_inquiry_copy(state),
        )
    try:
        publication_guard = self.workspace._terminal_graph_edit_publication_guard(
            state, actor_principal_id=actor_id, case_id=case_id)
    except WorkspacePersistenceError as exc:
        return finish(_terminal_edit_receipt(status="unavailable",
            message="Edit is unavailable. The pending question is unchanged.",
            error_code=str(exc.code or "unavailable"), pending_inquiry=_pending_inquiry_copy(state)))
    before_case_publish = publication_guard
    if _review_acceptance is not None:
        if publication_guard is None:
            raise WorkspaceAuthorizationDenied()
        def before_case_publish():
            publication_guard()
            _review_acceptance.reprove_review()
    try:
        # Never publish a request-local draft through the shared cache,
        # even briefly between factory construction and its removal.
        mediator = self.workspace._mediator_for_shared_interview(user, case_id,
            **({"cache": False} if publication_guard is not None else {}))
        actions = mediator.workflow_actions
        if not actions.interview_started:
            restored = actions.restore_session_projection(projection)
            if restored.get("error"):
                code = str((restored.get("error") or {}).get("code") or "session_missing")
                return _terminal_edit_receipt(
                    status="unavailable",
                    message=f"Edit is unavailable ({code}). The pending question is unchanged.",
                    error_code=code,
                    pending_inquiry=_pending_inquiry_copy(state),
                )
        actions.bind_interview_privacy(state.get("privacy_policy"), user_id=user, case_id=case_id)
        router_state = state.get("intake_router") if isinstance(state.get("intake_router"), dict) else {}
        router_session = str(router_state.get("session_id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", router_session):
            router_session = uuid.uuid4().hex
        begin_router = getattr(mediator, "begin_intake_router_action", None)
        if callable(begin_router):
            begin_router(
                owner_id=user,
                case_id=case_id,
                session_id=router_session,
                revision=int((actions._interview_meta or {}).get("session_revision") or 0),
                previous=router_state,
            )
    except WorkspacePersistenceError as exc:
        return _terminal_edit_receipt(
            status="unavailable",
            message=f"Edit is unavailable ({exc.code or 'unavailable'}). The pending question is unchanged.",
            error_code=str(exc.code or "unavailable"),
            pending_inquiry=_pending_inquiry_copy(state),
        )
    except Exception as exc:
        return _terminal_edit_receipt(
            status="unavailable",
            message=f"Edit is unavailable ({type(exc).__name__}). The pending question is unchanged.",
            error_code="capability_unavailable",
            pending_inquiry=_pending_inquiry_copy(state),
        )
    from complaint_phases.phase_manager import ComplaintPhase

    knowledge = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    if knowledge is None or not hasattr(knowledge, "factual_ledger"):
        return _terminal_edit_receipt(
            status="unavailable",
            message="Edit is unavailable (capability_unavailable). The pending question is unchanged.",
            error_code="capability_unavailable",
            pending_inquiry=_pending_inquiry_copy(state),
        )
    metadata = getattr(knowledge, "metadata", None)
    if isinstance(metadata, dict) and not str(metadata.get("case_id") or "").strip():
        metadata["case_id"] = case_id
    pending_before = _pending_inquiry_copy(state)
    from mediator.hook_runtime import graph_revision_token

    current_token = graph_revision_token(knowledge)
    current_session = int((actions._interview_meta or {}).get("session_revision") or 0)
    if require_expected_revision and (
        str(expected_graph_revision) != current_token or int(expected_session_revision or 0) != current_session
    ):
        return finish(_terminal_edit_receipt(
            status="refused",
            message="Stale concurrent edit rejected. The pending inquiry was kept.",
            error_code="stale_target",
            pending_inquiry=pending_before,
        ))
    if require_expected_revision:
        target, selection_code = _eligible_correction_for_actor(
            state, knowledge, actor_id, str(target_stable_id or ""),
        )
    else:
        target, selection_code = _last_eligible_accepted_answer(state, knowledge), None
    if target is None:
        code = selection_code or "missing_target"
        if code == "unauthorized_actor":
            message = "This actor cannot edit that answer. Other participants were left unchanged."
        else:
            message = "Nothing to edit yet. The pending question is unchanged."
        return finish(_terminal_edit_receipt(
            status="refused",
            message=message,
            error_code=code,
            pending_inquiry=pending_before,
        ))
    if require_expected_revision:
        graph_token = str(expected_graph_revision)
        session_revision = int(expected_session_revision or 0)
    else:
        graph_token = current_token if expected_graph_revision is None else str(expected_graph_revision)
        session_revision = current_session if expected_session_revision is None else int(expected_session_revision)
    event_id = "edit-" + hashlib.sha256(
        f"{target['stable_id']}|{text}".encode("utf-8")
    ).hexdigest()[:24]
    source_context = _edit_source_context(target.get("envelope") or {}, text, event_id)
    receipt = mediator.apply_factual_correction(
        action="correct",
        target_stable_id=target["stable_id"],
        replacement=text,
        source_context=source_context,
        event_id=event_id,
        case_id=case_id,
        expected_graph_revision=graph_token,
        expected_session_revision=session_revision,
    )
    status = str(receipt.get("status") or "")
    error = receipt.get("error") if isinstance(receipt.get("error"), dict) else {}
    error_code = str(error.get("code") or "")
    if status != "applied":
        if error_code == "stale_target":
            message = "Stale concurrent edit rejected. The pending inquiry was kept."
        elif error_code == "missing_target":
            message = "Nothing to edit yet. The pending question is unchanged."
        elif status == "unavailable":
            message = f"Edit is unavailable ({error_code or 'unavailable'}). The pending question is unchanged."
        else:
            message = f"Edit was refused ({error_code or status or 'refused'}). The pending question is unchanged."
        return finish(_terminal_edit_receipt(
            status=status or "refused",
            message=message,
            error_code=error_code or None,
            pending_inquiry=pending_before,
            correction=receipt,
        ))
    pending, reselected = _reselect_affected_pending(actions, knowledge, target, pending_before)
    exported = actions.export_session_projection()
    if isinstance(exported, dict) and legal_snapshot is not None:
        # A factual correction may invalidate support. It must not rewrite
        # the admitted legal dependency graph that was current at the edit.
        exported["dependency_graph"] = legal_snapshot
    if not isinstance(exported, dict):
        return finish(_terminal_edit_receipt(
            status="unavailable",
            message="Edit is unavailable (projection_invalid). The pending question is unchanged.",
            error_code="projection_invalid",
            pending_inquiry=pending_before,
            correction=receipt,
        ))
    state["shared_interview"] = exported
    if receipt.get("idempotent_replay") is not True:
        _append_correction_history(
            state, target, text, receipt,
            actor_principal_id=actor_id if require_expected_revision else "",
        )
        _record_support_projection(
            state,
            effect_id="correction:" + str(receipt.get("event_id") or target.get("stable_id") or ""),
            kind="correction",
            inquiry_id=str(target.get("question_id") or ""),
            revision=expected_session_revision,
            before_graph=before_factual,
            after_graph=exported.get("knowledge_graph") or {},
            legal_digest=legal_digest,
            affected=list(receipt.get("affected_support_targets") or []),
        )
    _note_terminal_edit_controls(
        state,
        pending=pending,
        question_id=str(target.get("question_id") or ""),
        previous=str(target.get("answer") or ""),
        replacement=text,
        target_stable_id=str(target.get("stable_id") or ""),
        replacement_stable_id=str(receipt.get("replacement_stable_id") or ""),
        graph_token=str(receipt.get("graph_revision") or ""),
        session_revision=int(exported.get("session_revision") or 0),
    )
    if _review_acceptance is not None:
        _review_acceptance.write_receipt(state, receipt, exported)
    try:
        if publication_guard is not None:
            publication_guard()
            self.workspace._save_state(state, before_publish=before_case_publish)
        else:
            self.workspace._save_state(state)
    except WorkspacePersistenceError as exc:
        return finish(_terminal_edit_receipt(
            status="unavailable",
            message=f"Edit is unavailable ({exc.code or 'durability_unproven'}). The pending question is unchanged.",
            error_code=str(exc.code or "durability_unproven"),
            pending_inquiry=pending_before,
            correction=receipt,
        ))
    finally:
        if publication_guard is not None:
            self.workspace._interview_mediators.pop((user, case_id), None)
    if reselected:
        message = "Edited the last recorded answer. The pending question was reopened because its target changed."
    else:
        message = "Edited the last recorded answer. The pending question is unchanged."
    return finish(_terminal_edit_receipt(
        status="applied",
        message=message,
        pending_inquiry=pending,
        pending_reselected=reselected,
        correction=receipt,
        graph_revision=str(receipt.get("graph_revision") or ""),
        session_revision=int(exported.get("session_revision") or 0),
    ))


def run_intake_chat_turn(
    self,
    user_id: Optional[str],
    *,
    message: Optional[str] = None,
    question_id: Optional[str] = None,
    expected_question_revision: Optional[int] = None,
    interview_action: Optional[str] = None,
    expected_graph_revision: Optional[str] = None,
    expected_session_revision: Optional[int] = None,
) -> Dict[str, Any]:
    workspace = self.workspace
    if str(interview_action or "").strip().lower() == "encrypted_resume":
        # Resume opens the encrypted snapshot before any session read so a
        # locked or missing key stays explicit and a browser cache is ignored.
        return workspace.resume_encrypted_browser_interview(user_id, browser_cache=message)
    state = self._load_state(user_id)
    normalized_message = str(message or "").strip()
    if normalized_message.lower() == "/why":
        why = format_terminal_why(state=state)
        payload = workspace._build_intake_chat_payload(state)
        payload["why"] = why
        payload["command"] = "/why"
        payload["stored_as_answer"] = False
        payload["awaiting_user"] = True
        payload["worker_stalled"] = False
        payload["legal_sufficiency"] = False
        payload["question_support"] = why.get("question_support")
        payload["diagnostic_receipt"] = why.get("diagnostic_receipt")
        payload["message"] = why["display"]
        return payload
    if normalized_message.lower() == "/research":
        research = workspace.run_legal_research(
            str(state.get("user_id") or user_id),
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
        )
        fresh = workspace._load_state(str(state.get("user_id") or user_id))
        payload = workspace._build_intake_chat_payload(fresh)
        payload["legal_research"] = research
        payload["command"] = "/research"
        payload["stored_as_answer"] = False
        payload["awaiting_user"] = research.get("error_code") != "stale_research"
        payload["legal_sufficiency"] = False
        payload["status"] = research.get("status")
        payload["message"] = str(research.get("display") or format_legal_research_result(research))
        return payload
    normalized_action = str(interview_action or "").strip().lower()
    if normalized_action in {"pause", "cancel", "cap", "unavailable", "saturate"}:
        return workspace.record_finite_interview_stop(state, normalized_action)
    if normalized_action == "correct" or normalized_message.lower().startswith("/edit"):
        return self._apply_gui_factual_correction(
            state,
            message=normalized_message,
            expected_graph_revision=expected_graph_revision,
            expected_session_revision=expected_session_revision,
        )
    if normalized_action == "resume":
        interview = workspace.apply_shared_interview(
            state,
            message=None,
            question_id=None,
            expected_question_revision=None,
            interview_action="resume",
            narrative_turn=False,
        )
        workspace._save_state(state)
        payload = workspace._build_intake_chat_payload(state)
        payload["interview"] = interview
        return payload
    normalized_question_id = str(question_id or "").strip()
    interview_projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    before_factual = deepcopy(interview_projection.get("knowledge_graph") or {})
    before_legal_digest = _legal_graph_digest(interview_projection.get("dependency_graph"))
    narrative_turn = normalized_question_id == ORIGINAL_COMPLAINT_QUESTION_ID or (
        not normalized_question_id and _narrative_is_open(state)
    )
    if narrative_turn:
        target_question = dict(_NARRATIVE_INQUIRY)
    else:
        target_question = (
            workspace._question_by_id(normalized_question_id)
            if normalized_question_id
            else workspace._next_question(state.get("intake_answers") or {})
        )
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    pending_graph = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else {}
    if not normalized_question_id and not narrative_turn and message and pending_graph.get("inquiry_id"):
        normalized_question_id = str(pending_graph["inquiry_id"])
    graph_inquiry = normalized_question_id.startswith("inq-")
    if normalized_question_id and target_question is None and not graph_inquiry:
        raise ValueError(f"Unknown intake question_id: {question_id}")

    accepted_answer: Optional[Dict[str, Any]] = None
    normalized_message = str(message or "").strip()
    privacy_command = normalized_message.lower()
    if privacy_command in {"/privacy local", "/privacy grok"}:
        helpers = _privacy_helpers()
        mode = "grok" if privacy_command.endswith("grok") else "local"
        case_id = _state_case_id(state, str(state.get("user_id") or self._normalize_user_id(user_id)))
        state["case_id"] = case_id
        state["privacy_policy"] = helpers["privacy_policy_for_mode"](
            str(state.get("user_id") or case_id),
            case_id,
            mode,
        )
        state["public_processing_mode"] = "grok" if mode == "grok" else "local"
        state["privacy_notice_shown"] = True
        workspace._save_state(state)
        payload = workspace._build_intake_chat_payload(
            state,
            accepted_answer=None,
            requested_question_id=question_id,
        )
        payload["privacy_command"] = {
            "applied": True,
            "stored_as_answer": False,
            "processing_mode": state["privacy_policy"]["processing_mode"],
        }
        payload["privacy_notice"] = _PRIVACY_MODE_NOTICE
        pending = payload.get("message") or ""
        payload["message"] = f"Saved privacy mode for this case. The pending question is unchanged.\n{pending}".strip()
        return payload

    joined_effect = None
    if normalized_message and normalized_action not in {"status", "resume"}:
        identity_question = normalized_question_id or str((target_question or {}).get("id") or "")
        joined_effect = workspace._joined_chat_identity(state, identity_question, normalized_message,
                                                        expected_question_revision)
        if any(item.get("effect_id") == joined_effect for item in state.get("intake_history", []) if isinstance(item, dict)):
            payload = workspace._build_intake_chat_payload(state)
            payload["duplicate_answer_effect"] = True
            return payload
    show_privacy_notice = not bool(state.get("privacy_notice_shown"))
    if show_privacy_notice:
        state["privacy_notice_shown"] = True
    if normalized_message and not (graph_inquiry or normalized_action in {"answer", "status"}):
        if target_question is None:
            raise ValueError("The intake flow is already complete for this session.")
        if narrative_turn:
            record = _narrative_record(state)
            revision = int(record.get("revision") or 0) + 1
            captured_at = self._timestamp()
            revisions = list(record.get("revisions") or [])
            revisions.append(
                {
                    "revision": revision,
                    "text": normalized_message,
                    "captured_at": captured_at,
                    "source": "intake_chat",
                }
            )
            record["schema_version"] = ORIGINAL_COMPLAINT_SCHEMA
            record["text"] = normalized_message
            record["revision"] = revision
            record["revisions"] = revisions
            state["original_complaint"] = record
            accepted_answer = {
                "question_id": ORIGINAL_COMPLAINT_QUESTION_ID,
                "answer": normalized_message,
                "captured_at": captured_at,
                "kind": "narrative",
                "revision": revision,
            }
        else:
            answer_map = state.setdefault("intake_answers", {})
            history = state.setdefault("intake_history", [])
            answer_map[target_question["id"]] = normalized_message
            accepted_answer = {
                "question_id": target_question["id"],
                "answer": normalized_message,
                "captured_at": self._timestamp(),
            }
            history.append(deepcopy(accepted_answer))

    interview = workspace.apply_shared_interview(
        state,
        message=normalized_message or None,
        question_id=normalized_question_id or None,
        expected_question_revision=expected_question_revision,
        interview_action=normalized_action or None,
        narrative_turn=bool(normalized_message and narrative_turn),
    )
    if interview.get("status") == "refused":
        payload = workspace._build_intake_chat_payload(state)
        payload["interview"] = interview
        payload["support_projection_updated"] = False
        payload["changes_law"] = False
        return payload
    accepted_graph_answer = bool(
        normalized_message
        and interview.get("status") not in {"refused", "unavailable"}
        and (graph_inquiry or normalized_action == "answer")
        and normalized_action not in {"status", "resume", "review", "why"}
    )
    support_update = {"applied": False, "duplicate": False, "count": len(state.get("affected_support_projection") or [])}
    if accepted_graph_answer:
        after_interview = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
        support_update = _record_support_projection(
            state,
            effect_id=f"answer:{normalized_question_id}:{expected_question_revision}",
            kind="answer",
            inquiry_id=normalized_question_id,
            revision=expected_question_revision,
            before_graph=before_factual,
            after_graph=after_interview.get("knowledge_graph") or {},
            legal_digest=before_legal_digest,
        )
    if joined_effect is not None:
        workspace._commit_joined_snapshot(state, effect_id=joined_effect,
            question_id=identity_question, answer=normalized_message)
    else:
        workspace._save_state(state)
    payload = workspace._build_intake_chat_payload(
        state,
        accepted_answer=accepted_answer,
        requested_question_id=None if accepted_answer is not None or graph_inquiry else question_id,
    )
    payload["interview"] = interview
    payload["support_projection_updated"] = bool(support_update.get("applied"))
    payload["support_projection_duplicate"] = bool(support_update.get("duplicate"))
    payload["changes_law"] = False
    if show_privacy_notice:
        payload["privacy_notice"] = _PRIVACY_MODE_NOTICE
        if str(payload.get("message") or "").startswith("Let's start with the basics."):
            payload["message"] = f"{_PRIVACY_MODE_NOTICE}\n\n{payload['message']}"
    return payload


def commit_factual_graph_revision(
    self,
    user_id: str,
    graph: Any,
    *,
    case_id: str,
    transaction_id: str,
    effect_id: str,
    expected_revision: Optional[str] = None,
    backend: Any = None,
) -> Dict[str, Any]:
    """Commit factual revision provenance inside the encrypted case transaction.

    The graph bytes are sealed by the automatic private-artifact owner.
    The transaction records that ciphertext id with the canonical document.
    A failed seal or commit does not replace the last committed head, and
    nothing is written as plaintext JSON, a plaintext CID, or a second graph store.
    """
    from integrations.ipfs_datasets.graphs import (
        FACTUAL_GRAPH_ARTIFACT_KIND,
        encode_factual_graph_artifact,
        seal_factual_graph_artifact,
    )
    from integrations.private_storage import PrivateRevisionError, PrivateStorageError, commit_private_revision

    resolved = self._check_access(user_id, ability="write", case_id=case_id)
    context = self._private_artifact_context(resolved, case_id)
    binding_case = str(context["case_id"])
    state = self._load_state(resolved, case_id=binding_case)
    if str(state.get("user_id") or "") != resolved:
        raise WorkspaceAuthorizationDenied()
    current = str(state.get("private_revision") or "0")
    expected = current if expected_revision in {None, ""} else str(expected_revision)
    if current != expected:
        raise WorkspacePersistenceError(
            "stale revision",
            code="revision_conflict",
            public_status="recoverable",
        )
    history = [item for item in list(state.get("intake_history") or []) if isinstance(item, dict)]
    if any(str(item.get("effect_id") or "") == effect_id for item in history):
        raise WorkspacePersistenceError(
            "effect already recorded",
            code="duplicate_effect",
            public_status="recoverable",
        )
    next_revision = str(int(expected) + 1)
    artifact_revision = f"fact-graph-{next_revision}"
    transport = backend if backend is not None else self._private_local_backend()
    backend_name = "local_cache" if backend is None else "kit"
    try:
        sealed = seal_factual_graph_artifact(
            graph,
            access=context["access"],
            tenant_id=str(context["tenant_id"]),
            case_id=binding_case,
            principal_id=str(context["principal_id"]),
            revision=artifact_revision,
            backend=transport,
            backend_name=backend_name,
            key_provider=context["key_provider"],
            pin_content=backend is not None,
        )
    except (PrivateStorageError, ValueError, TypeError) as exc:
        raise WorkspacePersistenceError(
            "Factual graph storage is unavailable.",
            code=str(getattr(exc, "code", "") or "artifact_unavailable"),
            public_status="unavailable",
        ) from None
    document = sealed["document"]
    if encode_factual_graph_artifact(document) != sealed["payload"]:
        raise WorkspacePersistenceError(
            "Factual graph artifact did not round-trip before commit.",
            code="readback_mismatch",
            public_status="recoverable",
        )
    annotation = state.get("annotation_knowledge_graph")
    if not isinstance(annotation, dict):
        annotation = {"entities": [], "relationships": []}
    relationships = [item for item in list(annotation.get("relationships") or []) if isinstance(item, dict)]
    annotation["relationships"] = relationships
    state["annotation_knowledge_graph"] = annotation
    proofs = [item for item in list(state.get("proof_history") or []) if isinstance(item, dict)]
    proofs.append({
        "effect_id": effect_id,
        "transaction_id": transaction_id,
        "kind": "factual-graph-revision",
        "revision": next_revision,
        "ciphertext_storage_id": sealed["ciphertext_storage_id"],
    })
    history.append({
        "question_id": "factual-graph",
        "answer": "",
        "effect_id": effect_id,
        "transaction_id": transaction_id,
        "kind": "factual-graph-revision",
    })
    state["intake_history"] = history
    state["proof_history"] = proofs
    state["private_revision"] = next_revision
    state["factual_graph_binding"] = {
        "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
        "artifact_revision": artifact_revision,
        "ciphertext_storage_id": sealed["ciphertext_storage_id"],
        "case_id": binding_case,
        "owner": resolved,
    }
    state.update(missing_new_session=False, session_readable=True, at_rest_protection="private_envelope")
    fact_document = {
        "relationships": relationships,
        "effect_id": effect_id,
        "revision": next_revision,
        "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
        "artifact_revision": artifact_revision,
        "ciphertext_storage_id": sealed["ciphertext_storage_id"],
        "factual_artifact": document,
    }
    proof_document = {"entries": proofs, "effect_id": effect_id, "revision": next_revision}
    _joined_context, key_id, key = self._joined_key(resolved, binding_case)
    try:
        publication = commit_private_revision(
            self.joined_revision_repository(resolved, binding_case),
            tenant_id=resolved,
            case_id=binding_case,
            principal_id=resolved,
            key=key,
            key_id=key_id,
            expected_revision=expected,
            session=json.dumps(state, sort_keys=True).encode("utf-8"),
            fact_graph=json.dumps(fact_document, sort_keys=True).encode("utf-8"),
            proof=json.dumps(proof_document, sort_keys=True).encode("utf-8"),
            transaction_id=transaction_id,
            effect_id=effect_id,
            key_resolver=self._joined_key_resolver(resolved, binding_case),
        publication_scope=self._joined_publication_scope(resolved, binding_case, key_id, key))
    except PrivateRevisionError as exc:
        raise WorkspacePersistenceError(
            "Factual graph revision did not commit.",
            code=str(exc.code or "transaction_failed"),
            public_status="recoverable",
        ) from None
    except PrivateStorageError as exc:
        raise WorkspacePersistenceError(
            "Factual graph revision did not commit.",
            code=str(exc.code or "artifact_unavailable"),
            public_status="recoverable",
        ) from None
    if not publication.committed:
        raise WorkspacePersistenceError(
            "Factual graph revision did not commit.",
            code="durability_unproven",
            public_status="recoverable",
        )
    receipt = publication.as_dict()
    receipt.update({
        "network_pinned": False,
        "private_artifact": True,
        "plaintext_fallback": False,
        "plaintext_catalog": False,
        "ciphertext_storage_id": sealed["ciphertext_storage_id"],
        "artifact_kind": FACTUAL_GRAPH_ARTIFACT_KIND,
        "artifact_revision": artifact_revision,
        "case_id": binding_case,
        "owner": resolved,
        "graph_registry_used": False,
    })
    return receipt


def resume_encrypted_interview(self, user_id: Optional[str], *, browser_cache: Any = None) -> Dict[str, Any]:
    """Restore one interview from the encrypted revision without replaying it.

    A new process supplies the same unlocked case key. Pending inquiry, case
    identity, consent, graph revisions, deferred gaps, and corrections come
    from that revision. Browser caches and caller messages are ignored.
    Denied, revoked, and missing-key results name the failure and omit case
    plaintext. This read does not call mediator hooks or append history.
    """

    def denial(status: str, code: str) -> Dict[str, Any]:
        return {
            "schema": "encrypted-interview-resume-v1",
            "status": status,
            "code": code,
            "resumed": False,
            "hooks_replayed": False,
            "messages_replayed": False,
            "reconstructed_from_browser_cache": False,
            "browser_cache_ignored": True,
            "pending_inquiry": None,
            "case": None,
            "consent": None,
            "factual_graph_revision": None,
            "legal_graph_revision": None,
            "deferred_gaps": [],
            "corrections": [],
            "legal_sufficiency": False,
            "plaintext_case_state": None,
            "encrypted_resume": {
                "status": status,
                "code": code,
                "resumed": False,
                "hooks_replayed": False,
                "messages_replayed": False,
                "reconstructed_from_browser_cache": False,
            },
        }

    del browser_cache
    try:
        resolved = self._check_access(user_id, ability="read")
    except WorkspaceAuthorizationDenied:
        return denial("denied", "authorization_denied")
    try:
        keys = self._private_key_session()
    except WorkspaceAuthorizationDenied:
        return denial("denied", "authorization_denied")
    if not keys.unlocked:
        return denial("missing_key", "missing_key")
    try:
        state = self._load_state(resolved)
    except WorkspaceAuthorizationDenied:
        return denial("denied", "authorization_denied")
    except WorkspacePersistenceError as exc:
        code = str(exc.code or "")
        if code in {"unlock_needed", "key_unavailable"}:
            return denial("missing_key", "missing_key")
        if code in {"authentication_failed", "corrupt_session"}:
            return denial("missing_key", code)
        return denial("missing_key", code or "missing_key")
    case_id = _state_case_id(state, resolved)
    source_identity = self._case_legal_context_identity(state)
    try:
        _, source_key_id, source_key = self._joined_key(resolved, case_id)
    except WorkspaceAuthorizationDenied:
        return denial("denied", "authorization_denied")
    except WorkspacePersistenceError as exc:
        return denial("missing_key", str(exc.code or "missing_key"))
    grant = state.get("case_key_grant") if isinstance(state.get("case_key_grant"), dict) else {}
    consent = state.get("operation_consent") if isinstance(state.get("operation_consent"), dict) else {}
    if grant.get("revoked") is True or str(grant.get("status") or "") == "revoked":
        return denial("revoked", "key_revoked")
    if consent.get("revoked") is True:
        return denial("revoked", "consent_revoked")
    projection = state.get("shared_interview") if isinstance(state.get("shared_interview"), dict) else {}
    pending = projection.get("pending_inquiry") if isinstance(projection.get("pending_inquiry"), dict) else None
    gaps = [deepcopy(item) for item in (projection.get("preserved_gaps") or []) if isinstance(item, dict)]
    deferred = [item for item in gaps if str(item.get("disposition") or "") == "deferred"]
    history = [item for item in (state.get("intake_history") or []) if isinstance(item, dict)]
    corrections: List[Dict[str, Any]] = []
    for item in history:
        if str(item.get("disposition") or "") in {"corrected", "correction"}:
            corrections.append({"source": "intake_history", "record": deepcopy(item)})
    graph_payload = projection.get("knowledge_graph") if isinstance(projection.get("knowledge_graph"), dict) else {}
    legal_payload = projection.get("dependency_graph") if isinstance(projection.get("dependency_graph"), dict) else {}
    factual_revision = None
    if graph_payload:
        try:
            from complaint_phases.knowledge_graph import KnowledgeGraph
            from mediator.hook_runtime import graph_revision_token
            factual_revision = graph_revision_token(KnowledgeGraph.from_dict(graph_payload))
        except Exception:
            factual_revision = None
        metadata = graph_payload.get("metadata") if isinstance(graph_payload.get("metadata"), dict) else {}
        ledger = metadata.get("factual_ledger") if isinstance(metadata.get("factual_ledger"), dict) else {}
        revision_rows = list(graph_payload.get("revisions") or []) + list(ledger.get("revisions") or [])
        for revision in revision_rows:
            if isinstance(revision, dict) and str(revision.get("action") or "") in {"correct", "correction", "supersede", "edit"}:
                corrections.append({"source": "factual_graph", "record": deepcopy(revision)})
    legal_revision = hashlib.sha256(
        json.dumps(legal_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    view = {
        "schema": "encrypted-interview-resume-v1",
        "status": "resumed",
        "code": "resumed",
        "resumed": True,
        "hooks_replayed": False,
        "messages_replayed": False,
        "reconstructed_from_browser_cache": False,
        "browser_cache_ignored": True,
        "case": {
            "case_id": _state_case_id(state, resolved),
            "user_id": str(state.get("user_id") or resolved),
            "session_revision": projection.get("session_revision"),
            "private_revision": state.get("private_revision"),
        },
        "consent": deepcopy(consent) if consent else None,
        "pending_inquiry": deepcopy(pending) if pending else None,
        "factual_graph_revision": factual_revision,
        "legal_graph_revision": legal_revision,
        "deferred_gaps": deferred,
        "preserved_gaps": gaps,
        "corrections": corrections,
        "legal_sufficiency": False,
    }
    payload = self.request_handlers._build_session_payload(state)
    payload["encrypted_resume"] = view
    payload["interview"] = {
        "contract_version": "interview-transition-v1",
        "action": "encrypted_resume",
        "status": "resumed",
        "inquiry": deepcopy(pending) if pending else None,
        "hooks_replayed": False,
        "messages_replayed": False,
        "legal_sufficiency": False,
        "error": None,
    }
    payload.update({
        "schema": view["schema"],
        "status": "resumed",
        "code": "resumed",
        "resumed": True,
        "hooks_replayed": False,
        "messages_replayed": False,
        "reconstructed_from_browser_cache": False,
        "browser_cache_ignored": True,
        "legal_sufficiency": False,
    })
    # Projection is not delivery authority. Reopen the real current case
    # and resolve its live key after all projection work, then reprove the
    # issued cookie/case capability immediately before returning plaintext.
    try:
        current = self._load_state(resolved, case_id=case_id)
        _, current_key_id, current_key = self._joined_key(resolved, case_id)
        if (self._case_legal_context_identity(current) != source_identity
                or (current_key_id, current_key) != (source_key_id, source_key)):
            return denial("stale", "revision_conflict")
        self._check_access(resolved, ability="read", case_id=case_id)
    except WorkspaceAuthorizationDenied:
        return denial("denied", "authorization_denied")
    except WorkspacePersistenceError as exc:
        return denial("missing_key", str(exc.code or "missing_key"))
    return payload
