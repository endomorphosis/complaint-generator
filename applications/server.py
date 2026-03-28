import json
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from .complaint_workspace_api import attach_complaint_workspace_routes
from .document_api import attach_document_routes
from .document_ui import load_document_html
from .review_api import attach_claim_support_review_routes
from .review_ui import attach_claim_support_review_ui_routes, attach_static_asset_routes


def _read_template(filename: str) -> str:
    path = os.path.join(os.getcwd(), "templates", filename)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    return ""


class SERVER:
    def __init__(self, mediator: Any):
        self.mediator = mediator
        self.app = self._build_app(mediator)

    @staticmethod
    def build_chat_payload(
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        sender: str = "Bot:",
        hashed_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload_dict = dict(payload or {})
        normalized_message = str(message or payload_dict.get("message") or "")
        response = {
            "sender": str(payload_dict.get("sender") or sender),
            "message": normalized_message,
            "question": str(payload_dict.get("question") or normalized_message),
            "inquiry": dict(payload_dict.get("inquiry") or {}),
            "explanation": dict(payload_dict.get("explanation") or {}),
        }
        normalized_username = str(
            payload_dict.get("hashed_username") or hashed_username or ""
        ).strip()
        if normalized_username:
            response["hashed_username"] = normalized_username
        return response

    @classmethod
    def process_chat_message(
        cls,
        mediator: Any,
        message_text: str,
        *,
        hashed_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        if callable(getattr(mediator, "io_payload", None)):
            payload = mediator.io_payload(message_text)
            return cls.build_chat_payload(
                str((payload or {}).get("message") or ""),
                payload if isinstance(payload, dict) else None,
                sender="Bot:",
                hashed_username=hashed_username,
            )

        if callable(getattr(mediator, "io", None)):
            reply = mediator.io(message_text)
            return cls.build_chat_payload(str(reply or ""), sender="Bot:", hashed_username=hashed_username)

        return cls.build_chat_payload("", sender="Bot:", hashed_username=hashed_username)

    @classmethod
    def _build_initial_chat_payload(
        cls,
        mediator: Any,
        *,
        hashed_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        inquiry_payload: Dict[str, Any] = {}
        if callable(getattr(mediator, "get_current_inquiry_payload", None)):
            try:
                candidate = mediator.get_current_inquiry_payload()
                if isinstance(candidate, dict):
                    inquiry_payload = candidate
            except Exception:
                inquiry_payload = {}
        return cls.build_chat_payload(
            "Please state your legal complaint",
            inquiry_payload,
            sender="Bot:",
            hashed_username=hashed_username,
        )

    def _build_app(self, mediator: Any) -> FastAPI:
        app = FastAPI()
        attach_static_asset_routes(app)
        attach_complaint_workspace_routes(app)
        attach_claim_support_review_routes(app, mediator)
        attach_claim_support_review_ui_routes(app)
        attach_document_routes(app, mediator)

        @app.get("/health")
        async def health() -> Dict[str, str]:
            return {"status": "healthy"}

        @app.get("/", response_class=HTMLResponse)
        @app.get("", response_class=HTMLResponse)
        async def index() -> str:
            return _read_template("index.html")

        @app.get("/home", response_class=HTMLResponse)
        async def home() -> str:
            return _read_template("home.html")

        @app.get("/profile", response_class=HTMLResponse)
        async def profile() -> str:
            return _read_template("profile.html")

        @app.get("/document", response_class=HTMLResponse)
        async def document() -> str:
            return load_document_html()

        @app.get("/results", response_class=HTMLResponse)
        async def results() -> str:
            return _read_template("results.html")

        @app.get("/workspace", response_class=HTMLResponse)
        async def workspace() -> str:
            return _read_template("workspace.html")

        @app.get("/mlwysiwyg", response_class=HTMLResponse)
        async def mlwysiwyg() -> str:
            return _read_template("MLWYSIWYG.html")

        @app.get("/chat", response_class=HTMLResponse)
        async def chat() -> str:
            return _read_template("chat.html")

        @app.get("/cookies")
        async def cookies(request: Request) -> JSONResponse:
            return JSONResponse(dict(request.cookies))

        @app.post("/load_profile")
        async def load_profile(request: Request) -> JSONResponse:
            payload = await request.json()
            request_payload = payload.get("request") if isinstance(payload, dict) else {}
            response_payload = {
                "hashed_username": str(request_payload.get("hashed_username") or request.cookies.get("hashed_username") or ""),
                "hashed_password": str(request_payload.get("hashed_password") or request.cookies.get("hashed_password") or ""),
                "data": json.dumps({}),
            }
            if "username" in request_payload or "password" in request_payload:
                return JSONResponse({"results": response_payload})
            return JSONResponse(response_payload)

        @app.post("/create_profile")
        async def create_profile() -> JSONResponse:
            return JSONResponse(
                {
                    "hashed_username": "",
                    "hashed_password": "",
                    "data": json.dumps({}),
                }
            )

        @app.post("/api/chat")
        async def post_chat(request: Request) -> JSONResponse:
            payload = await request.json()
            message_text = str(payload.get("message") or payload.get("content") or "").strip()
            if not message_text:
                raise HTTPException(status_code=400, detail="message is required")

            hashed_username = str(
                payload.get("hashed_username") or request.cookies.get("hashed_username") or ""
            ).strip()
            hashed_password = str(request.cookies.get("hashed_password") or "").strip()
            if hashed_username and hashed_password and hasattr(mediator, "state"):
                profile_request = {
                    "results": {
                        "hashed_username": hashed_username,
                        "hashed_password": hashed_password,
                    }
                }
                if callable(getattr(mediator.state, "load_profile", None)):
                    mediator.state.load_profile(profile_request)

            response_payload = self.process_chat_message(
                mediator,
                message_text,
                hashed_username=hashed_username or None,
            )
            return JSONResponse(response_payload)

        @app.post("/api/chat/fallback")
        async def chat_fallback(request: Request) -> JSONResponse:
            return await post_chat(request)

        @app.websocket("/api/chat")
        async def websocket_chat(websocket: WebSocket) -> None:
            await websocket.accept()
            hashed_username = str(websocket.cookies.get("hashed_username") or "").strip()
            hashed_password = str(websocket.cookies.get("hashed_password") or "").strip()

            initial_payload = self._build_initial_chat_payload(
                mediator,
                hashed_username=hashed_username or None,
            )
            await websocket.send_json(initial_payload)

            try:
                while True:
                    data = await websocket.receive_json()
                    message_text = str(data.get("message") or data.get("content") or "").strip()
                    if not message_text:
                        continue

                    profile_request = {
                        "results": {
                            "hashed_username": hashed_username,
                            "hashed_password": hashed_password,
                        }
                    }
                    if hashed_username and hashed_password and hasattr(mediator, "state"):
                        if callable(getattr(mediator.state, "load_profile", None)):
                            mediator.state.load_profile(profile_request)

                    user_payload = self.build_chat_payload(
                        message_text,
                        {
                            "sender": hashed_username or "User:",
                            "message": message_text,
                            "question": message_text,
                        },
                        sender=hashed_username or "User:",
                        hashed_username=hashed_username or None,
                    )
                    if hasattr(mediator, "state") and callable(getattr(mediator.state, "message", None)):
                        mediator.state.message(user_payload)
                    await websocket.send_json(user_payload)

                    bot_payload = self.process_chat_message(
                        mediator,
                        message_text,
                        hashed_username=hashed_username or None,
                    )
                    if hasattr(mediator, "state") and callable(getattr(mediator.state, "message", None)):
                        mediator.state.message(bot_payload)
                    await websocket.send_json(bot_payload)

                    if hashed_username and hashed_password and hasattr(mediator, "state"):
                        if callable(getattr(mediator.state, "store_profile", None)):
                            mediator.state.store_profile(profile_request)

            except WebSocketDisconnect:
                return

        return app

    def run(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
    ) -> None:
        import uvicorn

        uvicorn.run(
            self.app,
            host=host or "0.0.0.0",
            port=port or int(os.getenv("COMPLAINT_GENERATOR_PORT", "19030")),
            reload=reload,
        )
