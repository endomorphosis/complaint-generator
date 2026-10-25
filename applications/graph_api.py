"""Read one current encrypted case graph under live browser/case authority.

A mediator cache is not a private-read capability. The bound workspace decrypts
the current session twice around the pure projection. Changed source, locked
keys, or expired request authority refuse publication. This owner-key path does
not issue delegated decryption authority or claim WebSocket/SSE support.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.complaint_workspace import (
    ComplaintWorkspaceService, WorkspaceAccess, WorkspaceAuthorizationDenied,
    WorkspacePersistenceError, workspace_access_scope,
)
from applications.workspace_case_authority import (
    WorkspaceCaseAuthorityError, current_workspace_case_authority,
)
from complaint_phases.knowledge_graph import FactualReviewError, KnowledgeGraph
from mediator.integrations.graph_tools import FactualGraphProjectionError, project_factual_kg

TASK_ID = "CIMP-GUI-21"
REVIEW_TASK_ID = "CIMP-GUI-22"
FACTUAL_GRAPH_PREFIX = "/api/graphs"


def factual_graph_http_status(code: str) -> int:
    if code in {"graph_revision_changed", "stale_graph_revision", "event_conflict"}:
        return 409
    if code in {"unknown_target", "proposal_missing"}:
        return 404
    if code in {"constrained_text", "constrained_record", "source_required", "source_not_user_fact",
                "proposal_required", "proposal_not_hypothesis", "target_required", "unknown_action",
                "revision_refused"}:
        return 400
    if code in {"graph_read_ungranted", "cross_case_id", "actor_authority_required", "actor_not_permitted"}:
        return 403
    if code in {"mediator_graph_hook_unavailable", "knowledge_graph_unavailable", "data_graph_owner_unavailable",
                "workspace_graph_read_unavailable", "private_graph_unavailable", "unlock_needed"}:
        return 503
    return 403


def _read_snapshot(workspace, authority, actor, case_id):
    """Use the public read-only session seam; never an in-memory mediator graph."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.read" or authority.case_id != case_id:
        raise FactualGraphProjectionError("graph_read_ungranted")
    response = workspace.get_session(actor, case_id=case_id)
    state = response.get("session") if isinstance(response, dict) else None
    if (not isinstance(state, dict) or state.get("case_id") != case_id
            or state.get("user_id") != decision.canonical_owner_principal_id):
        raise FactualGraphProjectionError("cross_case_id")
    interview = state.get("shared_interview")
    graph = interview.get("knowledge_graph") if isinstance(interview, dict) else None
    if not isinstance(graph, dict) or not graph:
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "shared_interview": interview,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        hydrated = KnowledgeGraph.from_dict(graph)
    except (ValueError, TypeError, KeyError):
        raise FactualGraphProjectionError("knowledge_graph_unavailable") from None
    authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    return hydrated, identity


def _project_current(workspace, authority, actor, case_id):
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        graph, before = _read_snapshot(workspace, authority, actor, case_id)
        payload = project_factual_kg(graph, case_id=case_id)
        _current_graph, after = _read_snapshot(workspace, authority, actor, case_id)
        if before != after:
            raise FactualGraphProjectionError("graph_revision_changed")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        payload["factual_review_revision"] = graph.factual_review_revision()
        return payload


def _json_object(raw: bytes) -> dict:
    if not raw:
        raise FactualReviewError("constrained_text")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FactualReviewError("constrained_text") from None
    if not isinstance(payload, dict):
        raise FactualReviewError("constrained_text")
    return payload


def _owner_graph_state(workspace, authority, actor, case_id):
    """Load the encrypted graph without the read path's case.update save."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.update" or authority.case_id != case_id or decision.membership != "owner":
        raise FactualReviewError("actor_authority_required")
    backend = getattr(getattr(workspace, "request_handlers", None), "workspace", None)
    if backend is None or not hasattr(backend, "_load_state"):
        raise FactualGraphProjectionError("workspace_graph_read_unavailable")
    state = backend._load_state(decision.canonical_owner_principal_id, case_id=case_id)
    if str(state.get("user_id") or "") != decision.canonical_owner_principal_id or state.get("case_id") != case_id:
        raise FactualGraphProjectionError("cross_case_id")
    interview = state.get("shared_interview")
    graph_payload = interview.get("knowledge_graph") if isinstance(interview, dict) else None
    if not isinstance(graph_payload, dict) or not graph_payload:
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "knowledge_graph": graph_payload,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        hydrated = KnowledgeGraph.from_dict(graph_payload)
    except (ValueError, TypeError, KeyError):
        raise FactualGraphProjectionError("knowledge_graph_unavailable") from None
    return backend, state, hydrated, identity


def _review_current(workspace, authority, actor, case_id, body: dict):
    """Review one proposal on the decrypted graph, then seal that session."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        backend, state, graph, before = _owner_graph_state(workspace, authority, actor, case_id)
        result = graph.apply_factual_review(
            actor_role="user",
            actor_principal_id=decision.actor_principal_id,
            authority_granted=True,
            expected_revision=str(body.get("expected_graph_revision") or ""),
            action=str(body.get("review_action") or ""),
            text=body.get("text") if isinstance(body.get("text"), str) else "",
            source_text=body.get("source_text") if isinstance(body.get("source_text"), str) else "",
            message_id=str(body.get("message_id") or ""),
            target_stable_id=str(body.get("target_stable_id") or ""),
            proposal_id=str(body.get("proposal_id") or ""),
            origin=str(body.get("origin") or "actor"),
            event_id=str(body.get("event_id") or ""),
            case_id=case_id,
            record_class=str(body.get("record_class") or ""),
        )
        _backend_again, _state_again, _graph_again, after = _owner_graph_state(workspace, authority, actor, case_id)
        if before != after:
            raise FactualGraphProjectionError("graph_revision_changed")
        interview = state.get("shared_interview")
        if not isinstance(interview, dict):
            raise FactualGraphProjectionError("knowledge_graph_unavailable")
        interview["knowledge_graph"] = graph.to_dict()
        state["shared_interview"] = interview
        backend._save_state(state)
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        result["case_id"] = case_id
        result["task_id"] = REVIEW_TASK_ID
        return result


def mount_factual_graph_routes(app: Any) -> None:
    """Mount the factual projection. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS

    def _fail(exc: FactualGraphProjectionError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied"}, status_code=factual_graph_http_status(exc.code))

    def _review_fail(exc: FactualReviewError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "refused"}, status_code=factual_graph_http_status(exc.code))

    @app.get(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual")
    async def read_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.read":
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualGraphProjectionError("graph_read_ungranted")
            # ContextVars carry the real issued capability into the managed
            # thread; concurrent logout/revoke can still complete on the loop.
            payload = await run_in_threadpool(_project_current, workspace, authority, actor, authorized_case)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        payload["task_id"] = TASK_ID
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual/reviews")
    async def review_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.update":
            return _review_fail(FactualReviewError("actor_authority_required"))
        if getattr(decision, "membership", "") != "owner":
            return _review_fail(FactualReviewError("actor_not_permitted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        if authorized_case != case_id:
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            raw = await request.body()
            body = _json_object(raw)
            supplied_case = str(body.get("case_id") or "")
            if supplied_case and supplied_case != authorized_case:
                return _fail(FactualGraphProjectionError("cross_case_id"))
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualReviewError("actor_authority_required")
            payload = await run_in_threadpool(
                _review_current, workspace, authority, actor, authorized_case, body,
            )
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _review_fail(FactualReviewError("actor_authority_required"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualReviewError as exc:
            return _review_fail(exc)
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        return JSONResponse(payload)


LAW_DEPENDENCY_TASK_ID = "CIMP-GUI-27"
_LAW_LINK_KINDS = frozenset({"supports", "contradicts", "missing_evidence"})
_MODEL_ORIGINS = frozenset({"model", "llm", "inference", "model_output", "llm_text"})
_NARRATIVE_KEYS = ("user_narrative", "model_output", "llm_text")


class LegalDependencyGraphError(Exception):
    """Fail-closed law-derived graph error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


def legal_dependency_http_status(code: str) -> int:
    if code in {"narrative_not_law", "legal_dependency_field"}:
        return 400
    if code in {"graph_read_ungranted", "cross_case_id", "actor_authority_required"}:
        return 403
    if code in {"legal_dependency_unavailable", "mediator_graph_hook_unavailable"}:
        return 503
    return 403


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _admitted_authority(record: Mapping[str, Any] | dict) -> bool:
    return (
        isinstance(record, dict)
        and record.get("admitted_law") is True
        and record.get("status") == "admitted"
        and bool(_clean_text(record.get("source_passage")))
        and bool(_clean_text(record.get("content_hash")))
    )


def _passage_index(case_file: Mapping[str, Any]) -> dict:
    index = case_file.get("legal_source_passage_index")
    return index if isinstance(index, dict) else {}


def _burden_from_authority(admission: Mapping[str, Any], stored: Mapping[str, Any] | None) -> tuple[str, str]:
    """A burden is law only when the stored admitted passage contains that text.

    A burden string on the review record, a user narrative, or model output
    does not become the burden unless the stored passage index already has it.
    """
    passage = _clean_text(admission.get("source_passage"))
    stored_burden = _clean_text((stored or {}).get("burden"))
    if stored_burden and stored_burden in passage:
        return stored_burden, "admitted_passage"
    return "", "missing_from_admitted_authority"


def _requirement_from_admission(admission: Mapping[str, Any], stored: Mapping[str, Any] | None) -> dict:
    passage = _clean_text(admission.get("source_passage"))
    exceptions = admission.get("exceptions")
    if not isinstance(exceptions, list):
        exceptions = []
    exceptions = [item for item in exceptions if isinstance(item, str)]
    burden, burden_status = _burden_from_authority(admission, stored)
    stored_applicability = _clean_text((stored or {}).get("applicability"))
    applicability = _clean_text(admission.get("applicability"))
    if stored is not None and stored_applicability and applicability != stored_applicability:
        applicability = stored_applicability
    return {
        "content_hash": _clean_text(admission.get("content_hash")),
        "authority_identity": _clean_text(admission.get("authority_identity")),
        "requirement": passage,
        "burden": burden,
        "burden_status": burden_status,
        "exceptions": exceptions,
        "applicability": applicability,
        "jurisdiction": _clean_text(admission.get("jurisdiction")),
        "effective_date": _clean_text(admission.get("effective_date")),
        "treatment_state": _clean_text(admission.get("treatment_state")),
        "version": _clean_text(admission.get("version")),
        "source": "admitted_authority",
        "admitted_law": True,
        "proof": False,
        "legal_sufficiency": False,
        "rewritten_by_user_or_model": False,
    }


def _node_rows(graph: Any) -> list[dict]:
    if graph is None:
        return []
    raw_nodes = getattr(graph, "nodes", None)
    if raw_nodes is None and isinstance(graph, dict):
        raw_nodes = graph.get("nodes")
    rows = []
    if isinstance(raw_nodes, dict):
        values = list(raw_nodes.values())
    elif isinstance(raw_nodes, list):
        values = raw_nodes
    else:
        return []
    for item in values:
        if hasattr(item, "to_dict"):
            item = item.to_dict()
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _edge_rows(graph: Any) -> list[dict]:
    if graph is None:
        return []
    raw = getattr(graph, "dependencies", None)
    if raw is None and isinstance(graph, dict):
        raw = graph.get("edges") if isinstance(graph.get("edges"), list) else graph.get("dependencies")
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = raw
    else:
        return []
    rows = []
    for item in values:
        if hasattr(item, "to_dict"):
            item = item.to_dict()
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _node_text(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("description") or node.get("name") or attributes.get("description"))


def _node_origin(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("origin") or attributes.get("origin") or node.get("source") or attributes.get("source")).lower()


def _node_hash(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    return _clean_text(node.get("content_hash") or attributes.get("content_hash") or attributes.get("authority_text_sha256"))


def _node_source_id(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    provenance = node.get("provenance") if isinstance(node.get("provenance"), dict) else {}
    return _clean_text(
        node.get("source_id")
        or node.get("immutable_source_id")
        or attributes.get("source_id")
        or provenance.get("source_id")
        or node.get("id")
    )


def _edge_kind(edge: Mapping[str, Any]) -> str:
    kind = _clean_text(edge.get("dependency_type") or edge.get("link_kind")).lower()
    if kind == "supports":
        return "supports"
    if kind == "contradicts":
        return "contradicts"
    return ""


def _edge_endpoint(edge: Mapping[str, Any], side: str) -> str:
    return _clean_text(edge.get(side) or edge.get(side.replace("_id", "")) or "")


def project_law_derived_dependency_graph(
    case_file: Mapping[str, Any] | None,
    *,
    dependency_graph: Any = None,
    case_id: str = "",
) -> dict:
    """Project legal rules from admitted authorities and facts as separate links.

    User narratives and model text may show support, contradiction, or a
    missing-evidence gap. They never replace requirement, burden, exception,
    or applicability text taken from an admitted authority.
    """
    if not isinstance(case_file, Mapping):
        raise LegalDependencyGraphError("legal_dependency_unavailable")
    index = _passage_index(case_file)
    rows = case_file.get("legal_authority_admissions")
    admissions = [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    requirements = []
    rejected = []
    seen_hashes = set()
    for item in admissions:
        if not _admitted_authority(item):
            rejected.append({
                "origin": "unadmitted_record",
                "content_hash": _clean_text(item.get("content_hash")),
                "text": _clean_text(item.get("source_passage"))[:500],
                "reason": _clean_text(item.get("reason")) or "not_admitted_authority",
                "rewrites_legal_rule": False,
            })
            continue
        content_hash = _clean_text(item.get("content_hash"))
        stored = index.get(content_hash) if isinstance(index.get(content_hash), dict) else None
        if stored is None or _clean_text(stored.get("source_passage")) != _clean_text(item.get("source_passage")):
            rejected.append({
                "origin": "admission_without_stored_passage",
                "content_hash": content_hash,
                "text": _clean_text(item.get("source_passage"))[:500],
                "reason": "stored_passage_mismatch",
                "rewrites_legal_rule": False,
            })
            continue
        if content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        claimed_rule = _clean_text(item.get("requirement") or item.get("rule_text"))
        passage = _clean_text(item.get("source_passage"))
        if claimed_rule and claimed_rule != passage:
            rejected.append({
                "origin": "admission_rewrite",
                "content_hash": content_hash,
                "text": claimed_rule[:500],
                "reason": "user_or_model_text_not_law",
                "rewrites_legal_rule": False,
            })
        requirements.append(_requirement_from_admission(item, stored))
    for key in _NARRATIVE_KEYS:
        text = _clean_text(case_file.get(key))
        if text:
            rejected.append({
                "origin": key,
                "content_hash": "",
                "text": text[:500],
                "reason": "user_or_model_text_not_law",
                "rewrites_legal_rule": False,
            })
    nodes = {_clean_text(node.get("id")): node for node in _node_rows(dependency_graph)}
    factual_links = []
    supported = set()
    rewritten_hashes = set()
    for edge in _edge_rows(dependency_graph):
        kind = _edge_kind(edge)
        if not kind:
            continue
        source = nodes.get(_edge_endpoint(edge, "source_id"))
        target = nodes.get(_edge_endpoint(edge, "target_id"))
        if source is None or target is None:
            continue
        source_hash = _node_hash(source)
        target_hash = _node_hash(target)
        if target_hash in seen_hashes:
            content_hash, rule_node, fact = target_hash, target, source
        elif source_hash in seen_hashes:
            content_hash, rule_node, fact = source_hash, source, target
        else:
            rejected.append({
                "origin": _node_origin(target) or _node_origin(source) or "dependency_graph",
                "content_hash": target_hash or source_hash,
                "text": (_node_text(target) or _node_text(source))[:500],
                "reason": "unadmitted_dependency",
                "rewrites_legal_rule": False,
            })
            continue
        rule = next(item for item in requirements if item["content_hash"] == content_hash)
        graph_rule = _node_text(rule_node)
        if graph_rule and graph_rule != rule["requirement"] and content_hash not in rewritten_hashes:
            rewritten_hashes.add(content_hash)
            rejected.append({
                "origin": _node_origin(rule_node) or "dependency_graph",
                "content_hash": content_hash,
                "text": graph_rule[:500],
                "reason": "graph_text_does_not_rewrite_admitted_rule",
                "rewrites_legal_rule": False,
            })
        origin = _node_origin(fact) or "fact"
        factual_links.append({
            "link_kind": kind,
            "content_hash": content_hash,
            "fact_source_id": _node_source_id(fact),
            "fact_text": _node_text(fact),
            "origin": origin,
            "authority_is_user_fact": origin not in _MODEL_ORIGINS and origin not in {"legal", "authority"},
            "rewrites_legal_rule": False,
            "reason": "",
        })
        if kind == "supports":
            supported.add(content_hash)
    for rule in requirements:
        if rule["content_hash"] not in supported:
            factual_links.append({
                "link_kind": "missing_evidence",
                "content_hash": rule["content_hash"],
                "fact_source_id": "",
                "fact_text": "",
                "origin": "projection",
                "authority_is_user_fact": False,
                "rewrites_legal_rule": False,
                "reason": "no_supporting_fact",
            })
        if rule["burden_status"] != "admitted_passage":
            factual_links.append({
                "link_kind": "missing_evidence",
                "content_hash": rule["content_hash"],
                "fact_source_id": "",
                "fact_text": "",
                "origin": "projection",
                "authority_is_user_fact": False,
                "rewrites_legal_rule": False,
                "reason": "burden_not_in_admitted_authority",
            })
    requirement_text = "\n".join(item["requirement"] for item in requirements)
    for rejected_item in rejected:
        if rejected_item["text"] and rejected_item["text"] == requirement_text and rejected_item["origin"] in _NARRATIVE_KEYS:
            rejected_item["reason"] = "narrative_matches_passage_but_is_not_the_authority"
    return {
        "task_id": LAW_DEPENDENCY_TASK_ID,
        "case_id": case_id,
        "requirements": requirements,
        "factual_links": factual_links,
        "rejected_narratives": rejected,
        "admitted_count": len(requirements),
        "user_facts_are_not_law": True,
        "rules_rewritten_by_user_or_model": False,
        "proof": False,
        "legal_sufficiency": False,
        "research_gap": "" if requirements else "no_admitted_authority",
        "limitations": [
            "Requirements, burdens, exceptions, and applicability come only from admitted authority passages.",
            "User narratives, search snippets, and model output do not rewrite legal rules.",
            "Factual support, contradiction, and missing evidence stay links beside the rule.",
            "This projection is not a proof of legal sufficiency.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def _materials_from_mediator(mediator: Any) -> tuple[dict, Any]:
    from complaint_phases.phase_manager import ComplaintPhase

    case_file = None
    graph = None
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            case_file = stored
        graph = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    if case_file is None:
        stored = getattr(mediator, "intake_case_file", None)
        if isinstance(stored, dict):
            case_file = stored
    if graph is None:
        graph = getattr(mediator, "dependency_graph", None)
    if case_file is None:
        raise LegalDependencyGraphError("legal_dependency_unavailable")
    return case_file, graph


def mount_law_dependency_graph_routes(app: Any) -> None:
    """Mount the read-only law-derived dependency graph beside the factual graph."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS
    from applications.workspace_case_authority import current_workspace_case_authority

    def _fail(exc: LegalDependencyGraphError) -> JSONResponse:
        return JSONResponse(
            {"error": exc.code, "status": "denied", "rules_rewritten_by_user_or_model": False, "proof": False},
            status_code=legal_dependency_http_status(exc.code),
        )

    def _authorized(request: Request, case_id: str):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise LegalDependencyGraphError("graph_read_ungranted")
        action = getattr(decision, "action", "")
        expected = "case.read" if request.method.upper() in {"GET", "HEAD"} else "case.update"
        if action != expected:
            raise LegalDependencyGraphError("graph_read_ungranted")
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            raise LegalDependencyGraphError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalDependencyGraphError("mediator_graph_hook_unavailable")
        try:
            mediator, _workspace, _root = resolver()
            authority = current_workspace_case_authority()
        except Exception as exc:
            raise LegalDependencyGraphError("mediator_graph_hook_unavailable") from exc
        if mediator is None or authority is None or getattr(authority, "case_id", None) != case_id:
            raise LegalDependencyGraphError("graph_read_ungranted")
        return mediator

    @app.get(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency")
    async def read_law_dependency_graph(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            case_file, graph = _materials_from_mediator(mediator)
            payload = project_law_derived_dependency_graph(case_file, dependency_graph=graph, case_id=case_id)
        except LegalDependencyGraphError as exc:
            return _fail(exc)
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/legal-dependency")
    async def reject_law_dependency_rewrite(case_id: str, request: Request):
        """User narratives and model output cannot be posted back as legal rules."""
        try:
            _authorized(request, case_id)
            raw = await request.body()
            if raw:
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise LegalDependencyGraphError("legal_dependency_field")
        except LegalDependencyGraphError as exc:
            return _fail(exc)
        except (UnicodeDecodeError, ValueError):
            return _fail(LegalDependencyGraphError("legal_dependency_field"))
        return JSONResponse(
            {
                "error": "narrative_not_law",
                "status": "refused",
                "task_id": LAW_DEPENDENCY_TASK_ID,
                "rules_rewritten_by_user_or_model": False,
                "proof": False,
            },
            status_code=400,
        )
