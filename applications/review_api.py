from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from claim_support_review import (
    ClaimSupportDocumentSaveRequest,
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportIntakeSummaryConfirmRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReparseDocumentRequest,
    ClaimSupportReviewRequest,
    ClaimSupportTestimonySaveRequest,
    build_claim_support_document_payload,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_intake_summary_confirmation_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_reparse_document_payload,
    build_claim_support_review_payload,
    build_claim_support_testimony_payload,
    build_claim_support_uploaded_document_payload,
)
from .document_api import attach_document_routes

try:
    import python_multipart  # type: ignore  # noqa: F401

    _MULTIPART_AVAILABLE = True
except Exception:
    _MULTIPART_AVAILABLE = False


REVIEW_EXECUTION_COMPATIBILITY_NOTICE = {
    "deprecated": True,
    "field": "execute_follow_up",
    "route": "/api/claim-support/review",
    "replacement_route": "/api/claim-support/execute-follow-up",
    "message": (
        "execute_follow_up on /api/claim-support/review is deprecated; "
        "use /api/claim-support/execute-follow-up for side effects."
    ),
}
REVIEW_EXECUTION_SUNSET = "Wed, 30 Sep 2026 23:59:59 GMT"


def _apply_review_execution_compatibility_notice(
    payload: Dict[str, Any],
    response: Response,
) -> Dict[str, Any]:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = REVIEW_EXECUTION_SUNSET
    response.headers["Link"] = (
        '</api/claim-support/execute-follow-up>; rel="successor-version"'
    )
    response.headers["Warning"] = (
        '299 - "execute_follow_up on /api/claim-support/review is deprecated; '
        'use /api/claim-support/execute-follow-up"'
    )
    payload["compatibility_notice"] = dict(REVIEW_EXECUTION_COMPATIBILITY_NOTICE)
    return payload


def _normalize_required_support_kinds_form(
    raw_value: Optional[str],
) -> List[str]:
    if not raw_value:
        return []
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


def create_claim_support_review_router(mediator: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/claim-support/review")
    async def claim_support_review(
        request: ClaimSupportReviewRequest,
        response: Response,
    ) -> Dict[str, Any]:
        payload = build_claim_support_review_payload(mediator, request)
        if request.execute_follow_up:
            return _apply_review_execution_compatibility_notice(payload, response)
        return payload

    @router.post("/api/claim-support/execute-follow-up")
    async def claim_support_execute_follow_up(
        request: ClaimSupportFollowUpExecuteRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_follow_up_execution_payload(mediator, request)

    @router.post("/api/claim-support/confirm-intake-summary")
    async def claim_support_confirm_intake_summary(
        request: ClaimSupportIntakeSummaryConfirmRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_intake_summary_confirmation_payload(mediator, request)

    @router.post("/api/claim-support/resolve-manual-review")
    async def claim_support_resolve_manual_review(
        request: ClaimSupportManualReviewResolveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_manual_review_resolution_payload(mediator, request)

    @router.post("/api/claim-support/save-testimony")
    async def claim_support_save_testimony(
        request: ClaimSupportTestimonySaveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_testimony_payload(mediator, request)

    @router.post("/api/claim-support/save-document")
    async def claim_support_save_document(
        request: ClaimSupportDocumentSaveRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_document_payload(mediator, request)

    if _MULTIPART_AVAILABLE:

        @router.post("/api/claim-support/upload-document")
        async def claim_support_upload_document(
            file: UploadFile = File(...),
            user_id: Optional[str] = Form(default=None),
            claim_type: Optional[str] = Form(default=None),
            claim_element_id: Optional[str] = Form(default=None),
            claim_element: Optional[str] = Form(default=None),
            document_label: Optional[str] = Form(default=None),
            source_url: Optional[str] = Form(default=None),
            mime_type: Optional[str] = Form(default=None),
            evidence_type: str = Form(default="document"),
            testimony_id: Optional[str] = Form(default=None),
            required_support_kinds: Optional[str] = Form(default=None),
            include_post_save_review: bool = Form(default=True),
            include_support_summary: bool = Form(default=True),
            include_overview: bool = Form(default=True),
            include_follow_up_plan: bool = Form(default=True),
        ) -> Dict[str, Any]:
            file_bytes = await file.read()
            return build_claim_support_uploaded_document_payload(
                mediator,
                user_id=user_id,
                claim_type=claim_type,
                claim_element_id=claim_element_id,
                claim_element=claim_element,
                file_bytes=file_bytes,
                filename=file.filename,
                document_label=document_label,
                source_url=source_url,
                mime_type=mime_type or file.content_type,
                evidence_type=evidence_type,
                testimony_id=testimony_id,
                document_metadata={},
                required_support_kinds=_normalize_required_support_kinds_form(required_support_kinds),
                include_post_save_review=include_post_save_review,
                include_support_summary=include_support_summary,
                include_overview=include_overview,
                include_follow_up_plan=include_follow_up_plan,
            )
    else:

        @router.post("/api/claim-support/upload-document")
        async def claim_support_upload_document_unavailable(_: Request) -> Dict[str, Any]:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Document upload requires the optional dependency 'python-multipart'. "
                    "Install it to enable multipart evidence uploads."
                ),
            )

    # -----------------------------------------------------------------------
    # M1: Document Intake And Decomposition — reparse action
    # -----------------------------------------------------------------------

    @router.post("/api/claim-support/reparse-document")
    async def claim_support_reparse_document(
        request: ClaimSupportReparseDocumentRequest,
    ) -> Dict[str, Any]:
        return build_claim_support_reparse_document_payload(mediator, request)

    # -----------------------------------------------------------------------
    # M0: Question And Testimony Foundation
    # -----------------------------------------------------------------------

    @router.get("/api/claim-support/question-recommendations")
    async def claim_support_question_recommendations(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        max_recommendations: int = Query(default=20, ge=1, le=200),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_question_recommendations(
            resolved_user,
            claim_type=claim_type,
            max_recommendations=max_recommendations,
        )

    # -----------------------------------------------------------------------
    # M3: Graph snapshot persistence and support-path query routes.
    # -----------------------------------------------------------------------

    @router.get("/api/claim-support/support-paths")
    async def claim_support_paths(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        path_kind: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_support_paths_for_element(
            claim_type or "",
            user_id=resolved_user,
            claim_element_id=claim_element_id,
            path_kind=path_kind,
            limit=limit,
        )

    @router.get("/api/claim-support/contradiction-paths")
    async def claim_contradiction_paths(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_contradiction_paths_for_element(
            claim_type or "",
            user_id=resolved_user,
            claim_element_id=claim_element_id,
            limit=limit,
        )

    @router.get("/api/claim-support/graph-snapshots")
    async def claim_support_graph_snapshots(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        refs = mediator.get_graph_snapshot_refs_for_element(
            claim_type or "",
            user_id=resolved_user,
            claim_element_id=claim_element_id,
        )
        return {
            'available': True,
            'user_id': resolved_user,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'graph_snapshot_refs': refs,
            'graph_snapshot_count': len(refs),
        }

    # -----------------------------------------------------------------------
    # M4: Operator drilldown routes (timeline, archive-history, graph-trace,
    #     enrichment-queue, background enrichment submission).
    # -----------------------------------------------------------------------

    @router.get("/api/claim-support/support-timeline")
    async def claim_support_timeline(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_support_timeline(
            claim_type=claim_type,
            user_id=resolved_user,
            claim_element_id=claim_element_id,
            limit=limit,
        )

    @router.get("/api/claim-support/archive-history")
    async def claim_support_archive_history(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        domain: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_archive_history(
            user_id=resolved_user,
            claim_type=claim_type,
            domain=domain,
            limit=limit,
        )

    @router.get("/api/claim-support/graph-trace")
    async def claim_support_graph_trace(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        support_ref: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_graph_trace_drilldown(
            user_id=resolved_user,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            support_ref=support_ref,
        )

    @router.get("/api/claim-support/enrichment-queue")
    async def claim_support_enrichment_queue(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_enrichment_queue_state(
            user_id=resolved_user,
            claim_type=claim_type,
            status=status,
        )

    @router.get("/api/claim-support/enrichment-job/{job_id}")
    async def claim_support_enrichment_job(
        job_id: int,
        user_id: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_background_enrichment_job(
            job_id=job_id,
            user_id=resolved_user,
        )

    @router.post("/api/claim-support/enrich-background")
    async def claim_support_enrich_background(
        enrichment_type: str = Query(...),
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        priority: int = Query(default=0, ge=0, le=10),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        submission = mediator.submit_background_enrichment_job(
            enrichment_type=enrichment_type,
            user_id=resolved_user,
            claim_type=claim_type,
            priority=priority,
        )
        if not isinstance(submission, dict):
            submission = {"submitted": False, "error": "Invalid enrichment queue response"}
        get_queue_state = getattr(mediator, "get_enrichment_queue_state", None)
        if callable(get_queue_state):
            queue_state = get_queue_state(
                resolved_user,
                claim_type=claim_type,
            )
            if isinstance(queue_state, dict):
                submission["queue_state"] = queue_state
        return submission

    # M4: Retrieval session routes
    @router.post("/api/claim-support/retrieval-session")
    async def create_retrieval_session(
        user_id: Optional[str] = Query(default=None),
        claim_type: str = Query(...),
        claim_element_id: Optional[str] = Query(default=None),
        claim_element_text: Optional[str] = Query(default=None),
        query_text: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.create_retrieval_session(
            claim_type,
            user_id=resolved_user,
            claim_element_id=claim_element_id or '',
            claim_element_text=claim_element_text or '',
            query_text=query_text or '',
        )

    @router.get("/api/claim-support/retrieval-session")
    async def get_retrieval_session(
        session_id: str = Query(...),
        user_id: Optional[str] = Query(default=None),
        max_results: int = Query(default=50, ge=1, le=200),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_retrieval_session(
            session_id,
            user_id=resolved_user,
            max_results=max_results,
        )

    @router.get("/api/claim-support/retrieval-sessions")
    async def list_retrieval_sessions(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
        claim_element_id: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.list_retrieval_sessions(
            user_id=resolved_user,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            limit=limit,
        )

    @router.get("/api/claim-support/retrieval-context")
    async def get_retrieval_context(
        user_id: Optional[str] = Query(default=None),
        claim_type: str = Query(...),
        claim_element_id: str = Query(...),
        max_results: int = Query(default=10, ge=1, le=50),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_retrieval_context_for_element(
            claim_type,
            claim_element_id,
            user_id=resolved_user,
            max_results=max_results,
        )

    @router.get("/api/claim-support/element-proof-cards")
    async def get_element_proof_cards(
        user_id: Optional[str] = Query(default=None),
        claim_type: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_element_proof_cards(resolved_user, claim_type=claim_type)

    @router.get("/api/claim-support/element-proof-card")
    async def get_element_proof_card(
        user_id: Optional[str] = Query(default=None),
        claim_type: str = Query(...),
        claim_element_id: Optional[str] = Query(default=None),
        claim_element_text: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        resolved_user = user_id or getattr(getattr(mediator, "state", None), "username", None) or "anonymous"
        return mediator.get_element_proof_card(
            resolved_user,
            claim_type,
            claim_element_id=claim_element_id,
            claim_element_text=claim_element_text,
        )

    return router


def attach_claim_support_review_routes(app: FastAPI, mediator: Any) -> FastAPI:
    app.include_router(create_claim_support_review_router(mediator))
    return app


def create_review_api_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review API")
    attach_claim_support_review_routes(app, mediator)
    attach_document_routes(app, mediator)
    return app
