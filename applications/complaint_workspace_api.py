from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .complaint_mcp_protocol import handle_jsonrpc_message, tool_list_payload
from .complaint_workspace import ComplaintWorkspaceService, generate_decentralized_id


class IntakeRequest(BaseModel):
    user_id: Optional[str] = None
    answers: Dict[str, Any] = Field(default_factory=dict)


class EvidenceRequest(BaseModel):
    user_id: Optional[str] = None
    kind: str = "testimony"
    claim_element_id: str
    title: str
    content: str
    source: Optional[str] = None


class GmailEvidenceImportRequest(BaseModel):
    user_id: Optional[str] = None
    addresses: List[str] = Field(default_factory=list)
    collect_all_messages: bool = False
    claim_element_id: str = "causation"
    folder: str = "INBOX"
    folders: List[str] = Field(default_factory=list)
    limit: Optional[int] = None
    date_after: Optional[str] = None
    date_before: Optional[str] = None
    years_back: Optional[int] = None
    evidence_root: Optional[str] = None
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    use_gmail_oauth: bool = False
    gmail_oauth_client_secrets: Optional[str] = None
    gmail_oauth_token_cache: Optional[str] = None
    gmail_oauth_open_browser: bool = True
    complaint_query: Optional[str] = None
    complaint_keywords: List[str] = Field(default_factory=list)
    min_relevance_score: float = 0.0
    use_uid_checkpoint: bool = False
    checkpoint_name: Optional[str] = None
    uid_window_size: Optional[int] = None


class GmailDuckdbPipelineRequest(BaseModel):
    user_id: Optional[str] = None
    addresses: List[str] = Field(default_factory=list)
    collect_all_messages: bool = False
    claim_element_id: str = "causation"
    folder: str = "INBOX"
    folders: List[str] = Field(default_factory=list)
    years_back: Optional[int] = 2
    date_after: Optional[str] = None
    date_before: Optional[str] = None
    complaint_query: Optional[str] = None
    complaint_keywords: List[str] = Field(default_factory=list)
    min_relevance_score: float = 0.0
    evidence_root: Optional[str] = None
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    use_gmail_oauth: bool = False
    gmail_oauth_client_secrets: Optional[str] = None
    gmail_oauth_token_cache: Optional[str] = None
    gmail_oauth_open_browser: bool = True
    checkpoint_name: str = "gmail-duckdb-pipeline"
    uid_window_size: int = 500
    duckdb_build_every_batches: int = 10
    max_batches: int = 20
    duckdb_output_dir: Optional[str] = None
    append_to_existing_corpus: bool = False
    bm25_search_query: Optional[str] = None
    bm25_search_limit: int = 20


class EmailDuckdbSearchRequest(BaseModel):
    index_path: str
    query: str
    limit: int = 20
    ranking: str = "bm25"
    bm25_k1: float = 1.2
    bm25_b: float = 0.75


class LocalEvidenceImportRequest(BaseModel):
    user_id: Optional[str] = None
    paths: List[str] = Field(default_factory=list)
    claim_element_id: str = "causation"
    kind: str = "document"
    evidence_root: Optional[str] = None


class GenerateRequest(BaseModel):
    user_id: Optional[str] = None
    requested_relief: List[str] = Field(default_factory=list)
    title_override: Optional[str] = None
    use_llm: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    config_path: Optional[str] = None
    backend_id: Optional[str] = None


class DraftUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    requested_relief: Optional[List[str]] = None


class SynopsisUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    synopsis: str


class McpCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)


def create_complaint_workspace_router(service: Optional[ComplaintWorkspaceService] = None) -> APIRouter:
    router = APIRouter()
    workspace = service or ComplaintWorkspaceService()

    @router.get("/api/complaint-workspace/session")
    async def get_session(user_id: Optional[str] = None) -> Dict[str, Any]:
        return workspace.get_session(user_id)

    @router.post("/api/complaint-workspace/identity")
    async def create_identity() -> Dict[str, Any]:
        return generate_decentralized_id()

    @router.post("/api/complaint-workspace/intake")
    async def submit_intake(request: IntakeRequest) -> Dict[str, Any]:
        return workspace.submit_intake_answers(request.user_id, request.answers)

    @router.post("/api/complaint-workspace/evidence")
    async def save_evidence(request: EvidenceRequest) -> Dict[str, Any]:
        return workspace.save_evidence(
            request.user_id,
            kind=request.kind,
            claim_element_id=request.claim_element_id,
            title=request.title,
            content=request.content,
            source=request.source,
        )

    @router.post("/api/complaint-workspace/import-gmail-evidence")
    async def import_gmail_evidence_route(request: GmailEvidenceImportRequest) -> Dict[str, Any]:
        return workspace.import_gmail_evidence(
            request.user_id,
            addresses=list(request.addresses or []),
            collect_all_messages=bool(request.collect_all_messages),
            claim_element_id=request.claim_element_id,
            folder=request.folder,
            folders=list(request.folders or []),
            limit=request.limit,
            date_after=request.date_after,
            date_before=request.date_before,
            years_back=request.years_back,
            evidence_root=request.evidence_root,
            gmail_user=request.gmail_user,
            gmail_app_password=request.gmail_app_password,
            use_gmail_oauth=request.use_gmail_oauth,
            gmail_oauth_client_secrets=request.gmail_oauth_client_secrets,
            gmail_oauth_token_cache=request.gmail_oauth_token_cache,
            gmail_oauth_open_browser=request.gmail_oauth_open_browser,
            complaint_query=request.complaint_query,
            complaint_keywords=list(request.complaint_keywords or []),
            min_relevance_score=request.min_relevance_score,
            use_uid_checkpoint=request.use_uid_checkpoint,
            checkpoint_name=request.checkpoint_name,
            uid_window_size=request.uid_window_size,
        )

    @router.post("/api/complaint-workspace/import-local-evidence")
    async def import_local_evidence_route(request: LocalEvidenceImportRequest) -> Dict[str, Any]:
        return workspace.import_local_evidence(
            request.user_id,
            paths=list(request.paths or []),
            claim_element_id=request.claim_element_id,
            kind=request.kind,
            evidence_root=request.evidence_root,
        )

    @router.post("/api/complaint-workspace/run-gmail-duckdb-pipeline")
    async def run_gmail_duckdb_pipeline_route(request: GmailDuckdbPipelineRequest) -> Dict[str, Any]:
        return workspace.run_gmail_duckdb_pipeline(
            request.user_id,
            addresses=list(request.addresses or []),
            collect_all_messages=bool(request.collect_all_messages),
            claim_element_id=request.claim_element_id,
            folder=request.folder,
            folders=list(request.folders or []),
            years_back=request.years_back,
            date_after=request.date_after,
            date_before=request.date_before,
            complaint_query=request.complaint_query,
            complaint_keywords=list(request.complaint_keywords or []),
            min_relevance_score=request.min_relevance_score,
            evidence_root=request.evidence_root,
            gmail_user=request.gmail_user,
            gmail_app_password=request.gmail_app_password,
            use_gmail_oauth=request.use_gmail_oauth,
            gmail_oauth_client_secrets=request.gmail_oauth_client_secrets,
            gmail_oauth_token_cache=request.gmail_oauth_token_cache,
            gmail_oauth_open_browser=request.gmail_oauth_open_browser,
            checkpoint_name=request.checkpoint_name,
            uid_window_size=request.uid_window_size,
            duckdb_build_every_batches=request.duckdb_build_every_batches,
            max_batches=request.max_batches,
            duckdb_output_dir=request.duckdb_output_dir,
            append_to_existing_corpus=request.append_to_existing_corpus,
            bm25_search_query=request.bm25_search_query,
            bm25_search_limit=request.bm25_search_limit,
        )

    @router.post("/api/complaint-workspace/search-email-duckdb")
    async def search_email_duckdb_route(request: EmailDuckdbSearchRequest) -> Dict[str, Any]:
        return workspace.search_email_duckdb_corpus(
            index_path=request.index_path,
            query=request.query,
            limit=request.limit,
            ranking=request.ranking,
            bm25_k1=request.bm25_k1,
            bm25_b=request.bm25_b,
        )

    @router.post("/api/complaint-workspace/review")
    async def review_case(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.call_mcp_tool("complaint.review_case", request)

    @router.post("/api/complaint-workspace/generate")
    async def generate_complaint(request: GenerateRequest) -> Dict[str, Any]:
        return workspace.generate_complaint(
            request.user_id,
            requested_relief=request.requested_relief or None,
            title_override=request.title_override,
            use_llm=request.use_llm,
            provider=request.provider,
            model=request.model,
            config_path=request.config_path,
            backend_id=request.backend_id,
        )

    @router.post("/api/complaint-workspace/update-draft")
    async def update_draft(request: DraftUpdateRequest) -> Dict[str, Any]:
        return workspace.update_draft(
            request.user_id,
            title=request.title,
            body=request.body,
            requested_relief=request.requested_relief,
        )

    @router.post("/api/complaint-workspace/update-synopsis")
    async def update_case_synopsis(request: SynopsisUpdateRequest) -> Dict[str, Any]:
        return workspace.update_case_synopsis(request.user_id, request.synopsis)

    @router.post("/api/complaint-workspace/reset")
    async def reset_session(request: Dict[str, Any]) -> Dict[str, Any]:
        return workspace.reset_session(request.get("user_id"))

    @router.get("/api/complaint-workspace/export/download")
    async def download_complaint_packet(
        user_id: Optional[str] = Query(default=None),
        output_format: str = Query(default="json"),
    ) -> Response:
        artifact = workspace.build_export_artifact(user_id, output_format=output_format)
        return Response(
            content=artifact["body"],
            media_type=str(artifact["media_type"]),
            headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
        )

    @router.get("/api/complaint-workspace/mcp/tools")
    async def list_mcp_tools() -> Dict[str, Any]:
        return tool_list_payload(workspace)

    @router.post("/api/complaint-workspace/mcp/call")
    async def call_mcp_tool(request: McpCallRequest) -> Dict[str, Any]:
        return workspace.call_mcp_tool(request.tool_name, request.arguments)

    @router.post("/api/complaint-workspace/mcp/rpc")
    async def call_jsonrpc(request: JsonRpcRequest) -> Dict[str, Any]:
        response = handle_jsonrpc_message(workspace, request.model_dump())
        return response or {"jsonrpc": "2.0", "id": request.id, "result": None}

    return router


def attach_complaint_workspace_routes(
    app: FastAPI,
    service: Optional[ComplaintWorkspaceService] = None,
) -> FastAPI:
    app.include_router(create_complaint_workspace_router(service))
    return app
