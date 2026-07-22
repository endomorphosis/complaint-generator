from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from claim_support_review import (
    ClaimSupportDocumentSaveRequest,
    ClaimSupportFollowUpExecuteRequest,
    ClaimSupportIntakeSummaryConfirmRequest,
    ClaimSupportManualReviewResolveRequest,
    ClaimSupportReviewRequest,
    ClaimSupportTestimonySaveRequest,
    build_claim_support_document_payload,
    build_claim_support_follow_up_execution_payload,
    build_claim_support_intake_summary_confirmation_payload,
    build_claim_support_manual_review_resolution_payload,
    build_claim_support_review_payload,
    build_claim_support_testimony_payload,
    build_claim_support_uploaded_document_payload,
)
from .document_api import create_document_router

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


_COVERAGE_SUMMARY_FIELDS = (
    "claim_coverage_summary",
    "claim_support_snapshot_summary",
)
_FOLLOW_UP_SUMMARY_FIELDS = (
    "follow_up_history_summary",
    "follow_up_plan_summary",
    "follow_up_execution_summary",
    "execution_quality_summary",
)
_SUPPORT_PATH_SUMMARY_FIELDS = frozenset(
    {
        "graph_trace_summary",
        "support_packet_summary",
        "support_trace_summary",
    }
)


@dataclass(frozen=True)
class ReviewSummaryDTO:
    """Pass-through DTO for a review summary object.

    Review summaries intentionally carry extension fields added by the mediator.  A
    pass-through DTO gives the web boundary a stable mapping contract without
    forcing every producer and consumer to release in lockstep.
    """

    values: Dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "ReviewSummaryDTO":
        return cls(dict(value) if isinstance(value, Mapping) else {})

    def to_payload(self) -> Dict[str, Any]:
        return dict(self.values)


def normalize_coverage_summary_dto(value: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize a claim-keyed coverage summary for an API response."""

    if not isinstance(value, Mapping):
        return {}
    return {
        str(claim_name): ReviewSummaryDTO.from_value(summary).to_payload()
        for claim_name, summary in value.items()
    }


def normalize_follow_up_summary_dto(value: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize a claim-keyed follow-up summary for an API response."""

    if not isinstance(value, Mapping):
        return {}
    return {
        str(claim_name): ReviewSummaryDTO.from_value(summary).to_payload()
        for claim_name, summary in value.items()
    }


def normalize_support_path_summary_dto(value: Any) -> Dict[str, Any]:
    """Normalize one graph/trace/packet support-path summary."""

    return ReviewSummaryDTO.from_value(value).to_payload()


def _normalize_nested_support_path_summaries(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                normalize_support_path_summary_dto(item)
                if str(key) in _SUPPORT_PATH_SUMMARY_FIELDS
                else _normalize_nested_support_path_summaries(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_nested_support_path_summaries(item) for item in value]
    return value


def normalize_review_response_dto(value: Any) -> Dict[str, Any]:
    """Return the stable JSON-ready DTO used by all claim-support routes.

    The helper owns response-boundary normalization.  Route handlers only choose
    the application operation; they no longer need to know where coverage,
    follow-up, or graph support-path summaries live in nested payloads.
    """

    if not isinstance(value, Mapping):
        return {}
    payload = _normalize_nested_support_path_summaries(value)
    for field in _COVERAGE_SUMMARY_FIELDS:
        if field in payload:
            payload[field] = normalize_coverage_summary_dto(payload[field])
    for field in _FOLLOW_UP_SUMMARY_FIELDS:
        if field in payload:
            payload[field] = normalize_follow_up_summary_dto(payload[field])
    return payload


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


def _include_router_routes(app: FastAPI, router: APIRouter) -> None:
    existing = {
        (getattr(route, "path", None), tuple(sorted(getattr(route, "methods", []) or [])))
        for route in app.routes
    }
    for route in router.routes:
        route_key = (getattr(route, "path", None), tuple(sorted(getattr(route, "methods", []) or [])))
        if route_key in existing:
            continue
        if hasattr(route, "dependency_overrides_provider"):
            route.dependency_overrides_provider = app
        app.router.routes.append(route)
        existing.add(route_key)


def create_claim_support_review_router(mediator: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/claim-support/review")
    async def claim_support_review(
        request: ClaimSupportReviewRequest,
        response: Response,
    ) -> Dict[str, Any]:
        payload = normalize_review_response_dto(
            build_claim_support_review_payload(mediator, request)
        )
        if request.execute_follow_up:
            return _apply_review_execution_compatibility_notice(payload, response)
        return payload

    @router.post("/api/claim-support/execute-follow-up")
    async def claim_support_execute_follow_up(
        request: ClaimSupportFollowUpExecuteRequest,
    ) -> Dict[str, Any]:
        return normalize_review_response_dto(
            build_claim_support_follow_up_execution_payload(mediator, request)
        )

    @router.post("/api/claim-support/confirm-intake-summary")
    async def claim_support_confirm_intake_summary(
        request: ClaimSupportIntakeSummaryConfirmRequest,
    ) -> Dict[str, Any]:
        return normalize_review_response_dto(
            build_claim_support_intake_summary_confirmation_payload(mediator, request)
        )

    @router.post("/api/claim-support/resolve-manual-review")
    async def claim_support_resolve_manual_review(
        request: ClaimSupportManualReviewResolveRequest,
    ) -> Dict[str, Any]:
        return normalize_review_response_dto(
            build_claim_support_manual_review_resolution_payload(mediator, request)
        )

    @router.post("/api/claim-support/save-testimony")
    async def claim_support_save_testimony(
        request: ClaimSupportTestimonySaveRequest,
    ) -> Dict[str, Any]:
        return normalize_review_response_dto(
            build_claim_support_testimony_payload(mediator, request)
        )

    @router.post("/api/claim-support/save-document")
    async def claim_support_save_document(
        request: ClaimSupportDocumentSaveRequest,
    ) -> Dict[str, Any]:
        return normalize_review_response_dto(
            build_claim_support_document_payload(mediator, request)
        )

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
            required_support_kinds: Optional[str] = Form(default=None),
            include_post_save_review: bool = Form(default=True),
            include_support_summary: bool = Form(default=True),
            include_overview: bool = Form(default=True),
            include_follow_up_plan: bool = Form(default=True),
        ) -> Dict[str, Any]:
            file_bytes = await file.read()
            return normalize_review_response_dto(
                build_claim_support_uploaded_document_payload(
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
                    document_metadata={},
                    required_support_kinds=_normalize_required_support_kinds_form(required_support_kinds),
                    include_post_save_review=include_post_save_review,
                    include_support_summary=include_support_summary,
                    include_overview=include_overview,
                    include_follow_up_plan=include_follow_up_plan,
                )
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

    return router


def attach_claim_support_review_routes(app: FastAPI, mediator: Any) -> FastAPI:
    _include_router_routes(app, create_claim_support_review_router(mediator))
    return app


def create_review_api_app(mediator: Any) -> FastAPI:
    app = FastAPI(title="Complaint Generator Review API")
    attach_claim_support_review_routes(app, mediator)
    _include_router_routes(app, create_document_router(mediator))
    return app
