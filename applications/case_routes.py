"""Compose case routes behind verified sessions and server-owned case handlers.

Case identifiers select a resource; they never authenticate its caller. A
BrowserSessionService verifies the received cookie and CSRF token before the
shared CaseActionAuthorizer sees the actor. Case tenants and principal-roster
tenants are distinct namespaces. Legacy captured-mediator chat stays retired.
"""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import parse_qs

from starlette.requests import Request

from .browser_sessions import BrowserSessionError, BrowserSessionService, browser_session_http_status
from .case_access import BOUNDARIES, CaseAccessError, CaseActionAuthorizer
from .case_directory import CaseNamespace

CASE_ROUTE_KINDS = ("case", "graph", "message", "admin")
COMPOSITION_NAME = "compose_case_routes"
PROTECTED_PREFIXES = ("/api/complaint-workspace", "/api/claim-support", "/api/documents", "/api/chat")
RETIRED_EXACT_PATHS = frozenset({"/cookies", "/load_profile", "/create_profile", "/api/chat", "/api/chat/fallback"})
AUTH_PATHS = frozenset("/api/complaint-workspace/auth/" + name for name in ("login", "logout", "rotate", "session"))
_MODULES: List[Tuple[str, Callable[..., None], Tuple[str, ...]]] = []
RouteMount = Callable[[Any, Optional[CaseActionAuthorizer]], None]
_BOUND_HANDLERS: ContextVar[Optional[Callable[[], Tuple[Any, Any, Any]]]] = ContextVar("case_route_handlers", default=None)


class CaseHandlerRegistry:
    """Explicit operator bindings, never a captured mediator shared by all cases."""

    def __init__(self) -> None:
        self._bindings: Dict[Tuple[str, str, str], Tuple[Any, Any, Any, Any]] = {}

    def bind(self, case: CaseNamespace, *, mediator: Any, workspace_service: Any,
             download_root: Optional[Path] = None,
             authorize_delegated: Optional[Callable[[Any], bool]] = None) -> None:
        if not isinstance(case, CaseNamespace) or mediator is None or workspace_service is None:
            raise CaseAccessError("case_handler_binding")
        key = (case.tenant_id, case.case_id, case.resource_id)
        if key in self._bindings:
            raise CaseAccessError("case_handler_already_bound")
        root = Path(download_root).resolve(strict=True) if download_root is not None else None
        if root is not None and not root.is_dir():
            raise CaseAccessError("case_download_root")
        for bound_mediator, bound_workspace, bound_root, _grant_check in self._bindings.values():
            if mediator is bound_mediator or workspace_service is bound_workspace:
                raise CaseAccessError("case_handler_reused")
            if root is not None and bound_root is not None and (root.is_relative_to(bound_root) or bound_root.is_relative_to(root)):
                raise CaseAccessError("case_download_root_overlap")
        self._bindings[key] = (mediator, workspace_service, root, authorize_delegated)

    def resolve(self, decision: Any) -> Tuple[Any, Any, Any]:
        key = (decision.tenant_id, decision.case_id, decision.resource_id)
        try:
            mediator, workspace, root, grant_check = self._bindings[key]
        except KeyError:
            raise CaseAccessError("case_handler_unavailable") from None
        if decision.membership != "owner":
            # Policy membership alone does not grant decryption. The later
            # private-grant owner can supply a live checker; absent grants deny.
            try:
                granted = callable(grant_check) and grant_check(decision) is True
            except Exception:
                granted = False
            if not granted:
                raise CaseAccessError("case_key_grant_required")
        return mediator, workspace, root


def case_download_root() -> Path:
    resolver = _BOUND_HANDLERS.get()
    if resolver is None:
        raise CaseAccessError("case_handler_unavailable")
    handlers = resolver()
    if handlers[2] is None:
        raise CaseAccessError("case_handler_unavailable")
    return handlers[2]


class _RequestCaseTarget:
    def __init__(self, index: int) -> None:
        self._index = index

    def __getattr__(self, name: str) -> Any:
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise CaseAccessError("case_handler_unavailable")
        return getattr(resolver()[self._index], name)


def _credential_request(scope: Dict[str, Any]) -> Request:
    """Pass actual wire credentials to Task05 without resource identity claims.

    The case tenant is not the authentication roster tenant. Resource and
    actor claims are separately checked below, not relabeled as credentials.
    Actual method/cookie/CSRF values remain unchanged; no identity is injected.
    """
    credential_scope = dict(scope)
    credential_scope["headers"] = [(key, value) for key, value in scope.get("headers", [])
                                   if key.lower() in {b"cookie", b"x-csrf-token"}]
    credential_scope["query_string"] = b""
    credential_scope["state"] = {}
    return Request(credential_scope)


class _WorkspaceSessions:
    """Reuse Task05 verification for the mounted workspace dependency too."""

    def __init__(self, service: BrowserSessionService) -> None:
        self._service = service

    async def bind_http(self, request: Request, *, allow_anonymous: bool):
        if _path_of(request.scope) in AUTH_PATHS:
            return await self._service.bind_http(request, allow_anonymous=allow_anonymous)
        return await self._service.bind_http(_credential_request(request.scope), allow_anonymous=False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)


def register_case_route_module(kind: str, mount: RouteMount, *, protected_prefixes: Sequence[str]) -> None:
    if kind not in CASE_ROUTE_KINDS or not callable(mount):
        raise ValueError("case route module must declare an approved kind and callable")
    prefixes = tuple(str(prefix) for prefix in protected_prefixes if str(prefix).strip())
    if not prefixes or any(not prefix.startswith("/api/") for prefix in prefixes):
        raise ValueError("case route module must declare protected API prefixes")
    _MODULES.append((kind, mount, prefixes))


def unregister_case_route_module(mount: RouteMount) -> None:
    _MODULES[:] = [item for item in _MODULES if item[1] is not mount]


def compose_case_routes(app: Any, *, authorizer: Optional[CaseActionAuthorizer], mediator: Any = None,
                        include_workspace: bool = True, include_review: bool = True,
                        include_document: bool = True, workspace_service: Any = None,
                        browser_sessions: Optional[BrowserSessionService] = None,
                        case_handlers: Optional[CaseHandlerRegistry] = None) -> Any:
    """Mount the same fail-closed boundary in every production app variant.

    Historical mediator/workspace arguments grant no ambient case access.
    Operators bind each case explicitly in case_handlers. Missing session or
    handler configuration stays unavailable, without a trusted-local fallback.
    """
    if authorizer is not None and not isinstance(authorizer, CaseActionAuthorizer):
        raise CaseAccessError("authority_owners")
    if browser_sessions is not None and not isinstance(browser_sessions, BrowserSessionService):
        raise CaseAccessError("authentication_configuration")
    if case_handlers is not None and not isinstance(case_handlers, CaseHandlerRegistry):
        raise CaseAccessError("case_handler_binding")
    sessions = browser_sessions if browser_sessions is not None else BrowserSessionService.unavailable()
    from .complaint_workspace_api import create_complaint_workspace_router
    from .fastapi_compat import attach_router_routes
    router = create_complaint_workspace_router(_RequestCaseTarget(1), browser_sessions=_WorkspaceSessions(sessions))
    if not include_workspace:
        router.routes[:] = [route for route in router.routes if getattr(route, "path", None) in AUTH_PATHS]
    attach_router_routes(app, router)
    if include_review:
        from .review_api import attach_claim_support_review_routes
        attach_claim_support_review_routes(app, _RequestCaseTarget(0))
    if include_document:
        from .document_api import attach_document_routes
        attach_document_routes(app, _RequestCaseTarget(0))
    modules = tuple(_MODULES)
    extensions = tuple((kind, prefix) for kind, _mount, prefixes in modules for prefix in prefixes)
    for _kind, mount, _prefixes in modules:
        mount(app, authorizer)
    app.state.case_authorizer = authorizer
    app.state.browser_sessions = sessions
    app.state.case_handlers = case_handlers
    app.state.case_route_composition = COMPOSITION_NAME
    app.state.case_route_extension_kinds = tuple(kind for kind, _mount, _prefixes in modules)
    app.state.case_route_boundaries = BOUNDARIES
    app.add_middleware(CaseRouteAuthorizationMiddleware, authorizer=authorizer, sessions=sessions,
                       case_handlers=case_handlers, extensions=extensions)
    return app


def _path_of(scope: Dict[str, Any]) -> str:
    path = str(scope.get("path") or "")
    return path.rstrip("/") if len(path) > 1 else path


def _within_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def boundary_for_path(path: str) -> str:
    if "/mcp" in path:
        return "mcp"
    if path.startswith("/api/documents"):
        return "download"
    if path.startswith("/api/claim-support"):
        return "review"
    return "http"


def _status_for_denial(code: str) -> int:
    if code in {"unauthenticated", "missing_principal", "authorizer_required", "request_body"}:
        return 401
    if code == "revision_conflict":
        return 409
    if code == "case_handler_unavailable":
        return 503
    return 403


def _material_from_scope(scope: Dict[str, Any], body: bytes) -> Dict[str, Any]:
    query = scope.get("query_string") or b""
    parsed = parse_qs(query.decode("latin1"), keep_blank_values=True)
    material = {key: values[-1] for key, values in parsed.items() if values}
    headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
    fields = {"x-actor-principal-id": "actor_principal_id", "x-tenant-id": "tenant_id",
              "x-case-id": "case_id", "x-resource-id": "resource_id", "x-case-action": "action",
              "x-expected-revision": "expected_revision", "x-expected-membership-revision": "expected_membership_revision",
              "x-owner-principal-id": "owner_principal_id", "x-role": "role"}
    for header, field in fields.items():
        if header in headers:
            material[field] = headers[header]
    if "x-trusted-local" in headers:
        material["trusted_local"] = True
    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            material.update(payload)
    for field in ("expected_revision", "expected_membership_revision"):
        value = material.get(field)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            material[field] = int(value.strip())
    return material


def _check_actor_claims(scope: Dict[str, Any], body: bytes, principal_id: str) -> None:
    query = parse_qs((scope.get("query_string") or b"").decode("latin1"), keep_blank_values=True)
    claims = []
    for key in ("actor_principal_id", "principal_id", "user_id"):
        if any(value != principal_id for value in query.get(key, [])):
            raise CaseAccessError("actor_mismatch")
    headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
    for key in ("x-actor-principal-id", "x-user-id", "x-principal-id"):
        if key in headers and headers[key] != principal_id:
            raise CaseAccessError("actor_mismatch")
    if body:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            claims.append(payload)
            for container in (payload.get("arguments"), payload.get("params")):
                if isinstance(container, dict):
                    claims.append(container)
                    if isinstance(container.get("arguments"), dict):
                        claims.append(container["arguments"])
    for claim in claims:
        for key in ("actor_principal_id", "principal_id", "user_id"):
            if key in claim and claim[key] != principal_id:
                raise CaseAccessError("actor_mismatch")


def _required_action(path: str, method: str, material: Mapping[str, Any], extensions) -> str:
    if path.startswith("/api/documents"):
        return "case.download" if method in {"GET", "HEAD"} else "case.update"
    if path.startswith("/api/claim-support"):
        return "case.review" if method in {"GET", "HEAD"} else "case.update"
    if "/mcp" in path:
        params = material.get("params") if isinstance(material.get("params"), dict) else {}
        name = str(material.get("tool_name") or params.get("name") or "")
        rpc_method = str(material.get("method") or "") if path.endswith("/mcp/rpc") else ""
        if path.endswith("/mcp/call"):
            name = str(material.get("tool_name") or "")
        elif path.endswith("/mcp/rpc"):
            name = str(params.get("name") or "") if rpc_method == "tools/call" else ""
        read = method in {"GET", "HEAD"} or rpc_method in {"ping", "initialize", "tools/list"}
        read = read or name.startswith(("complaint.get_", "complaint.list_")) or name in {"complaint.review_case", "complaint.search_corpus"}
        return "case.read" if read else "case.update"
    for kind, prefix in extensions:
        if _within_prefix(path, prefix):
            if kind == "admin":
                return "account.metadata.read" if method in {"GET", "HEAD"} else "role.assign"
            if kind == "message" and method not in {"GET", "HEAD"}:
                return "case.message.send"
    return "case.read" if method in {"GET", "HEAD"} else "case.update"


async def _read_body(receive):
    messages, chunks = [], []
    while True:
        message = await receive()
        messages.append(message)
        if message.get("type") != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    index = 0

    async def replay():
        nonlocal index
        if index < len(messages):
            message = messages[index]
            index += 1
            return message
        return {"type": "http.request", "body": b"", "more_body": False}
    return b"".join(chunks), replay


async def _send_json(send, status, payload):
    data = json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data, "more_body": False})


class CaseRouteAuthorizationMiddleware:
    def __init__(self, app: Any, *, authorizer, sessions, case_handlers, extensions) -> None:
        self.app, self.authorizer, self.sessions = app, authorizer, sessions
        self.case_handlers, self.extensions = case_handlers, extensions
        self.prefixes = PROTECTED_PREFIXES + tuple(prefix for _kind, prefix in extensions)

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        path = _path_of(scope)
        if path in RETIRED_EXACT_PATHS:
            await self._deny(scope, send, 401, "legacy_route_retired")
            return
        if not any(_within_prefix(path, prefix) for prefix in self.prefixes):
            await self.app(scope, receive, send)
            return
        # WS/streaming have no qualified session/revocation adapter yet.
        if scope.get("type") == "websocket":
            await self._deny(scope, send, 401, "transport_unqualified")
            return
        if path in AUTH_PATHS:
            await self.app(scope, receive, send)
            return
        if not isinstance(self.authorizer, CaseActionAuthorizer):
            await self._deny(scope, send, 401, "authorizer_required")
            return
        body, inbound = b"", receive
        if scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
            body, inbound = await _read_body(receive)
        try:
            bound = await self.sessions.bind_http(_credential_request(scope), allow_anonymous=False)
            _check_actor_claims(scope, body, bound.principal_id)
            material = _material_from_scope(scope, body)
            action = _required_action(path, str(scope.get("method") or ""), material, self.extensions)
            if "action" in material and material["action"] != action:
                raise CaseAccessError("action_mismatch")
            material["actor_principal_id"], material["action"] = bound.principal_id, action
            decision = self.authorizer.authorize_request(boundary_for_path(path), material)
            handlers = None
            if decision.permits_case_content:
                if self.case_handlers is None:
                    raise CaseAccessError("case_handler_unavailable")
                self.case_handlers.resolve(decision)
                handlers = lambda: self.case_handlers.resolve(decision)
        except BrowserSessionError as exc:
            status, code = browser_session_http_status(exc)
            await self._deny(scope, send, status, code)
            return
        except CaseAccessError as exc:
            await self._deny(scope, send, _status_for_denial(exc.code), exc.code)
            return
        forwarded = dict(scope)
        state = dict(scope.get("state") or {})
        state.update(case_authorization=decision, browser_principal=bound)
        forwarded["state"] = state
        token = _BOUND_HANDLERS.set(handlers)
        try:
            await self.app(forwarded, inbound, send)
        finally:
            _BOUND_HANDLERS.reset(token)

    async def _deny(self, scope, send, status, code):
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await _send_json(send, status, {"error": code})
