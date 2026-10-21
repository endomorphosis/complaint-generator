from __future__ import annotations

import argparse
from functools import wraps
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import typer
except ModuleNotFoundError:
    class _MiniTyperApp:
        def __init__(self, help: str | None = None) -> None:
            self.help = help or ""
            self._commands: dict[str, object] = {}

        def command(self, name: str):
            def _decorator(func):
                self._commands[name] = func
                return func

            return _decorator

        def __call__(self) -> None:
            argv = sys.argv[1:]
            if not argv:
                raise SystemExit(self.help or "No command provided.")
            command_name = argv[0]
            func = self._commands.get(command_name)
            if func is None:
                raise SystemExit(f"Unknown command: {command_name}")
            signature = inspect.signature(func)
            parsed: dict[str, object] = {}
            list_defaults = {
                name: list(param.default)
                for name, param in signature.parameters.items()
                if isinstance(param.default, list)
            }
            index = 1
            while index < len(argv):
                token = argv[index]
                if not token.startswith("--"):
                    index += 1
                    continue
                key = token[2:].replace("-", "_")
                parameter = signature.parameters.get(key)
                if parameter is None:
                    index += 1
                    continue
                default = parameter.default
                if isinstance(default, bool):
                    parsed[key] = True
                    index += 1
                    continue
                if index + 1 >= len(argv):
                    raise SystemExit(f"Missing value for --{token[2:]}")
                value = argv[index + 1]
                if isinstance(default, list):
                    list_defaults.setdefault(key, []).append(value)
                else:
                    parsed[key] = value
                index += 2
            for key, values in list_defaults.items():
                parsed[key] = values
            func(**parsed)

    class _MiniTyperModule:
        Typer = _MiniTyperApp

        @staticmethod
        def Option(default=None, *args, **kwargs):
            return default

        @staticmethod
        def Argument(default=None, *args, **kwargs):
            return default

        @staticmethod
        def echo(value) -> None:
            print(value)

    typer = _MiniTyperModule()

from complaint_generator.legacy_session_migration import migrate_legacy_session
from integrations.ipfs_datasets.loader import import_attr_optional, import_failure_message

from .complaint_workspace import ComplaintWorkspaceService, WorkspaceAuthorizationDenied, WorkspacePersistenceError, _state_case_id


DEFAULT_UI_UX_SCREENSHOT_TARGET = "playwright/tests/complaint-flow.spec.js"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90


app = typer.Typer(help="Unified complaint workspace CLI.")
class TerminalComplaintWorkspaceService(ComplaintWorkspaceService):
    """Keep the canonical interview and its encrypted transaction, with a traced backend.

    The superclass still owns admission, graph/cache construction and transitions.
    Trace receipts are attached to the state already being saved by that request;
    diagnostics never reload and overwrite a concurrently changed session.
    """

    def _mediator_for_shared_interview(self, user_id: str, case_id: str):
        mediator = super()._mediator_for_shared_interview(user_id, case_id)
        from backends.llm_router_backend import load_terminal_router_backend
        if not hasattr(mediator, "_terminal_router_backend"):
            backend = load_terminal_router_backend(str(Path(__file__).resolve().parents[1] / "config.llm_router.json"))
            mediator.backends = [backend]
            mediator._terminal_router_backend = backend
        return mediator

    def apply_shared_interview(self, state, **kwargs):
        receipt = super().apply_shared_interview(state, **kwargs)
        user_id = str(state.get("user_id") or "")
        mediator = self._interview_mediators.get((user_id, _state_case_id(state, user_id)))
        backend = getattr(mediator, "_terminal_router_backend", None)
        if backend is not None:
            from copy import deepcopy
            projection = state.get("shared_interview") or {}
            previous = state.get("router_trace") or {}
            stored = list(previous.get("receipts") or [])
            known = {(item.get("router_receipt") or {}).get("request_id") for item in stored}
            # Only real calls/errors enter history. Cold resume preserves the
            # original invocation association rather than inventing a dispatch.
            for item in backend.task_receipts:
                if item.get("request_id") and item["request_id"] in known:
                    continue
                if item in [entry.get("router_receipt") for entry in stored]:
                    continue
                entry = {"router_receipt": deepcopy(item),
                         "interview_session_id": projection.get("session_id"),
                         "interview_revision": projection.get("session_revision")}
                stored.append(entry)
                if item.get("request_id"):
                    known.add(item["request_id"])
            if backend.task_receipts:
                state["router_trace"] = {"diagnostics": backend.sanitized_session_diagnostics(),
                                         "receipts": stored[-32:]}
            elif not previous:
                state["router_trace"] = {"diagnostics": backend.sanitized_session_diagnostics(), "receipts": []}
            receipt["router_diagnostics"] = deepcopy((state.get("router_trace") or {}).get("diagnostics") or {})
        return receipt


service = TerminalComplaintWorkspaceService()


def _emit_workspace_failure(error: Exception) -> None:
    """Close the terminal exception boundary without exposing callback locals."""

    codes = {
        "unlock_needed", "authentication_failed", "corrupt_session", "read_error",
        "binding_missing", "owner_mismatch", "overwrite_blocked", "key_unavailable",
        "private_persistence_unavailable", "migration_required",
    }
    status, code = "unavailable", "workspace_operation_failed"
    if isinstance(error, WorkspacePersistenceError):
        if error.public_status in {"unlock_needed", "recoverable", "unavailable"}:
            status = error.public_status
        if isinstance(error.code, str) and error.code in codes:
            code = error.code
    elif isinstance(error, WorkspaceAuthorizationDenied):
        code = "authorization_denied"
    typer.echo(json.dumps({
        "status": status,
        "code": code,
        "message": "The private workspace operation could not continue. Unlock or recover the selected case, then retry.",
        "actions": ["unlock_selected_case", "recover_selected_case", "retry"],
        "awaiting_user": True,
        "persistence_outcome": "unverified",
        "privacy_bypassed": False,
        "unlock_is_remote_consent": False,
    }, sort_keys=True))
    raise SystemExit(2) from None


def _workspace_command_boundary(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except EOFError:
            # EOF/pause semantics are a separate terminal-controls contract.
            raise
        except Exception as error:
            # Typer/Rich may otherwise render private answer and storage locals.
            # SystemExit and KeyboardInterrupt keep their existing semantics.
            _emit_workspace_failure(error)

    return invoke


def _require_readable_session(payload: dict[str, Any]) -> None:
    state = payload.get("session") if isinstance(payload.get("session"), dict) else payload
    if state.get("session_readable") is False or state.get("existing_unreadable") is True:
        status = state.get("status")
        code = state.get("code")
        raise WorkspacePersistenceError(
            "Private session is not readable",
            code=code if isinstance(code, str) else "private_persistence_unavailable",
            public_status=status if isinstance(status, str) else "unavailable",
        )


def run_ui_review_workflow(*args, **kwargs):
    """Load screenshot/model review dependencies only for UI review requests."""

    from applications.ui_review import run_ui_review_workflow as workflow

    return workflow(*args, **kwargs)


def _require_ipfs_attr(module_name: str, attr_name: str) -> Any:
    """Resolve an optional provider attribute through the integration boundary."""

    value, error = import_attr_optional(module_name, attr_name)
    if value is not None and error is None:
        return value
    message = import_failure_message(error) or f"missing attribute {attr_name}"
    raise ImportError(f"Unable to import {module_name}.{attr_name}: {message}")


def _print(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _split_multiline_values(raw_value: Optional[str]) -> Optional[list[str]]:
    if not raw_value:
        return None
    values = [line.strip() for line in raw_value.splitlines() if line.strip()]
    return values or None


def _parse_json_option(raw_value: Optional[str], *, option_name: str, expected_json_type: type):
    if raw_value is None:
        return None
    candidate = str(raw_value).strip()
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        preview = candidate[:100]
        if len(candidate) > 100:
            preview += "..."
        raise SystemExit(f"{option_name} must be valid JSON: {error.msg}. Input: {preview}") from error
    if not isinstance(parsed, expected_json_type):
        expected_labels = {list: "array", dict: "object"}
        expected_label = expected_labels.get(expected_json_type, expected_json_type.__name__)
        raise SystemExit(f"{option_name} must decode to a JSON {expected_label}.")
    return parsed


@app.command("session")
def session(user_id: str = "demo-user") -> None:
    _print(service.get_session(user_id))


@app.command("identity")
def identity() -> None:
    _print(service.call_mcp_tool("complaint.create_identity", {}))


@app.command("questions")
def questions() -> None:
    _print(service.list_intake_questions())


@app.command("claim-elements")
def claim_elements() -> None:
    _print(service.list_claim_elements())


@app.command("tools")
def tools() -> None:
    _print(service.list_mcp_tools())


@app.command("answer")
def answer(user_id: str = "demo-user", question_id: str = "", answer_text: str = "") -> None:
    _print(service.submit_intake_answers(user_id, {question_id: answer_text}))


@app.command("chat-turn")
@_workspace_command_boundary
def chat_turn(
    user_id: str = "demo-user",
    message: Optional[str] = None,
    question_id: Optional[str] = None,
) -> None:
    _print(
        service.run_intake_chat_turn(
            user_id,
            message=message,
            question_id=question_id,
        )
    )


def _read_narrative_file(path_text: str) -> str:
    """Read a narrative file by literal path. The path is never passed to a shell."""

    literal = str(path_text or "").strip()
    if not literal or "\x00" in literal:
        raise ValueError("narrative file path is empty")
    path = Path(literal)
    try:
        if not path.is_file():
            raise ValueError("narrative file is not readable")
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("narrative file is not readable") from exc


def read_original_complaint_input(stream=None, *, interactive: Optional[bool] = None) -> str:
    """Read a complaint narrative from the terminal, a pipe, or an ``@path`` file.

    A single interactive line is one narrative. End a line with ``\\`` to
    continue, or on a pipe finish the narrative with a blank line or a line
    that is only ``.``. ``@path`` reads that file directly and does not run
    the path as a command. Structured answers do not use this reader.
    """

    source = sys.stdin if stream is None else stream
    if interactive is None:
        isatty = getattr(source, "isatty", None)
        interactive = bool(isatty()) if callable(isatty) else False

    def read_line() -> Optional[str]:
        if interactive and source is sys.stdin:
            try:
                return input("> ")
            except EOFError:
                return None
        line = source.readline()
        if line == "":
            return None
        return line.rstrip("\n")

    first = read_line()
    if first is None:
        raise EOFError
    stripped = first.strip()
    if stripped.startswith("@") and stripped[1:].strip():
        return _read_narrative_file(stripped[1:])

    chunks: list[str] = []
    pending = first
    while True:
        if pending.endswith("\\"):
            chunks.append(pending[:-1])
            nxt = read_line()
            if nxt is None:
                break
            pending = nxt
            continue
        if pending.strip() == ".":
            break
        chunks.append(pending)
        if interactive:
            break
        nxt = read_line()
        if nxt is None or nxt.strip() in {"", "."}:
            break
        pending = nxt
    text = "\n".join(chunks).strip()
    if text == "":
        raise EOFError
    return text


def _read_chat_answer(inquiry: dict) -> str:
    if str(inquiry.get("question_id") or "") == "original_complaint":
        return read_original_complaint_input()
    answer_text = input("> ")
    return answer_text.strip()


@app.command("chat")
@_workspace_command_boundary
def chat(user_id: str = "demo-user", max_turns: int = 0) -> None:
    payload = service.run_intake_chat_turn(user_id)
    accepted_turns = 0

    while True:
        _require_readable_session(payload)
        trace = (payload.get("session") or {}).get("router_trace") or {}
        if trace.get("diagnostics"):
            typer.echo("Router diagnostics: " + json.dumps(trace["diagnostics"], sort_keys=True))
        typer.echo(str(payload.get("message") or "").strip())
        inquiry = dict(payload.get("inquiry") or {})
        if not inquiry:
            break
        if max_turns > 0 and accepted_turns >= max_turns:
            typer.echo("Chat paused. Resume with the same user ID to continue the saved intake.")
            break
        try:
            answer_text = _read_chat_answer(inquiry)
        except EOFError:
            raise
        if not answer_text:
            typer.echo("Please enter a response or stop the command and resume later with the same user ID.")
            continue
        payload = service.run_intake_chat_turn(
            user_id,
            message=answer_text,
            question_id=str(inquiry.get("question_id") or "") or None,
        )
        accepted_turns += 1

    typer.echo(f"Current synopsis: {str(payload.get('case_synopsis') or '').strip() or 'No synopsis recorded yet.'}")


@app.command("add-evidence")
def add_evidence(
    user_id: str = "demo-user",
    kind: str = "testimony",
    claim_element_id: str = "causation",
    title: str = "Untitled evidence",
    content: str = "",
    source: Optional[str] = None,
    attachment_names: Optional[str] = None,
) -> None:
    _print(
        service.save_evidence(
            user_id,
            kind=kind,
            claim_element_id=claim_element_id,
            title=title,
            content=content,
            source=source,
            attachment_names=[item.strip() for item in str(attachment_names or "").split("|") if item.strip()],
        )
    )


@app.command("import-gmail-evidence")
def import_gmail_evidence_command(
    user_id: str = "demo-user",
    address: list[str] = typer.Option([], "--address", help="Target address to match in From/To/Cc headers. Repeat for multiple addresses."),
    collect_all_messages: bool = typer.Option(False, "--collect-all-messages", help="Import the whole mailbox slice instead of requiring address matches."),
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    folders: list[str] = typer.Option([], "--scan-folder", help="Additional Gmail IMAP folder to scan. Repeat to broaden collection across INBOX, Sent, or All Mail."),
    limit: Optional[int] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    years_back: Optional[int] = typer.Option(None, "--years-back", help="Convenience window for broad collection, e.g. --years-back 2 to scan the last two years when --date-after is omitted."),
    complaint_query: Optional[str] = None,
    complaint_keyword: list[str] = typer.Option([], "--complaint-keyword", help="Complaint-specific keyword or phrase to improve relevance filtering. Repeat for multiple terms."),
    min_relevance_score: float = 0.0,
    use_uid_checkpoint: bool = typer.Option(False, "--use-uid-checkpoint", help="Resume large Gmail imports by IMAP UID checkpoint instead of rescanning the same mailbox slice."),
    checkpoint_name: Optional[str] = typer.Option(None, "--checkpoint-name", help="Optional checkpoint name when managing multiple Gmail import cursors."),
    uid_window_size: Optional[int] = typer.Option(None, "--uid-window-size", help="Maximum number of newly discovered UID messages to import in this run."),
    build_duckdb_index: bool = typer.Option(False, "--build-duckdb-index", help="Build or update a DuckDB/parquet email corpus from the generated import manifest."),
    duckdb_output_dir: Optional[str] = typer.Option(None, "--duckdb-output-dir", help="Directory for DuckDB/parquet email index artifacts."),
    append_duckdb_index: bool = typer.Option(False, "--append-duckdb-index", help="Append the import manifest into an existing DuckDB corpus instead of rebuilding it."),
    bm25_search_query: Optional[str] = typer.Option(None, "--bm25-search-query", help="Optional keyword query to run against the DuckDB BM25 index after building it."),
    bm25_search_limit: int = typer.Option(20, "--bm25-search-limit", help="Maximum number of BM25 hits to return."),
    evidence_root: Optional[str] = None,
    gmail_user: Optional[str] = typer.Option(os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), "--gmail-user"),
    gmail_app_password: Optional[str] = typer.Option(os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), "--gmail-app-password"),
    use_gmail_oauth: bool = typer.Option(False, "--use-gmail-oauth"),
    gmail_oauth_client_secrets: Optional[str] = typer.Option(os.environ.get("GMAIL_OAUTH_CLIENT_SECRETS"), "--gmail-oauth-client-secrets"),
    gmail_oauth_token_cache: Optional[str] = typer.Option(os.environ.get("GMAIL_OAUTH_TOKEN_CACHE"), "--gmail-oauth-token-cache"),
    gmail_oauth_open_browser: bool = typer.Option(True, "--gmail-oauth-open-browser/--no-gmail-oauth-browser"),
    prompt_for_credentials: bool = typer.Option(False, "--prompt-for-credentials"),
    use_keyring: bool = typer.Option(False, "--use-keyring"),
    save_to_keyring: bool = typer.Option(False, "--save-to-keyring"),
    use_ipfs_secrets_vault: bool = typer.Option(False, "--use-ipfs-secrets-vault"),
    save_to_ipfs_secrets_vault: bool = typer.Option(False, "--save-to-ipfs-secrets-vault"),
) -> None:
    import anyio

    from integrations.ipfs_datasets.legal_data import load_legal_symbol

    resolve_gmail_credentials = load_legal_symbol("resolve_gmail_credentials", module="email_auth")
    build_email_duckdb_artifacts = load_legal_symbol("build_email_duckdb_artifacts", module="email_corpus")
    search_email_graphrag_duckdb = load_legal_symbol("search_email_graphrag_duckdb", module="email_corpus")
    import_gmail_evidence = load_legal_symbol("import_gmail_evidence", module="email_import")

    parser = argparse.ArgumentParser(prog="complaint-workspace import-gmail-evidence")
    if not collect_all_messages and not list(address or []):
        parser.error("Provide at least one --address or use --collect-all-messages.")
    if use_gmail_oauth:
        resolved_gmail_user = str(gmail_user or "").strip()
        resolved_gmail_app_password = None
        if not resolved_gmail_user:
            parser.error("--gmail-user is required when --use-gmail-oauth is enabled.")
        if not gmail_oauth_client_secrets:
            parser.error("--gmail-oauth-client-secrets is required when --use-gmail-oauth is enabled.")
    else:
        resolved_gmail_user, resolved_gmail_app_password = resolve_gmail_credentials(
            gmail_user=str(gmail_user or ""),
            gmail_app_password=str(gmail_app_password or ""),
            prompt_for_credentials=prompt_for_credentials,
            use_keyring=use_keyring,
            save_to_keyring_flag=save_to_keyring,
            use_ipfs_secrets_vault=use_ipfs_secrets_vault,
            save_to_ipfs_secrets_vault_flag=save_to_ipfs_secrets_vault,
            parser=parser,
        )

    async def _run_import() -> dict[str, object]:
        return await import_gmail_evidence(
            addresses=address,
            collect_all_messages=collect_all_messages,
            user_id=user_id,
            claim_element_id=claim_element_id,
            workspace_root=service._session_dir,
            evidence_root=Path(evidence_root) if evidence_root else None,
            folder=folder,
            folders=folders,
            limit=limit,
            date_after=date_after,
            date_before=date_before,
            years_back=years_back,
            complaint_query=complaint_query,
            complaint_keywords=complaint_keyword,
            min_relevance_score=min_relevance_score,
            use_gmail_oauth=use_gmail_oauth,
            gmail_oauth_client_secrets=gmail_oauth_client_secrets,
            gmail_oauth_token_cache=gmail_oauth_token_cache,
            gmail_oauth_open_browser=gmail_oauth_open_browser,
            use_uid_checkpoint=use_uid_checkpoint,
            checkpoint_name=checkpoint_name,
            uid_window_size=uid_window_size,
            gmail_user=resolved_gmail_user,
            gmail_app_password=resolved_gmail_app_password,
            service=service,
        )

    payload = anyio.run(_run_import)
    if build_duckdb_index and payload.get("manifest_path"):
        payload["duckdb_index"] = build_email_duckdb_artifacts(
            manifest_path=payload["manifest_path"],
            output_dir=duckdb_output_dir,
            append=bool(append_duckdb_index),
        )
        if bm25_search_query and payload["duckdb_index"].get("duckdb_path"):
            payload["bm25_search"] = search_email_graphrag_duckdb(
                index_path=payload["duckdb_index"]["duckdb_path"],
                query=bm25_search_query,
                limit=int(bm25_search_limit or 20),
                ranking="bm25",
            )
    _print(payload)


@app.command("import-local-evidence")
def import_local_evidence_command(
    user_id: str = "demo-user",
    path: list[str] = typer.Option(..., "--path", help="Local file or directory path to import. Repeat to collect multiple artifacts."),
    claim_element_id: str = "causation",
    kind: str = "document",
    evidence_root: Optional[str] = None,
) -> None:
    payload = service.import_local_evidence(
        user_id,
        paths=path,
        claim_element_id=claim_element_id,
        kind=kind,
        evidence_root=evidence_root,
    )
    _print(payload)


@app.command("migrate-legacy-session")
def migrate_legacy_session_command(
    statefile: str = str(Path("/home/barberb/HACC/complaint-generator/statefiles/temporary-cli-session-latest.json")),
    workspace_root: str = str(Path("/home/barberb/HACC/workspace")),
    user_id: str = "did:key:legacy-temporary-session",
) -> None:
    _print(
        migrate_legacy_session(
            statefile=Path(statefile),
            workspace_root=Path(workspace_root),
            user_id=user_id,
        )
    )


@app.command("run-gmail-duckdb-pipeline")
def run_gmail_duckdb_pipeline_command(
    user_id: str = "demo-user",
    address: list[str] = typer.Option([], "--address", help="Target address to match in From/To/Cc headers. Repeat for multiple addresses."),
    collect_all_messages: bool = typer.Option(False, "--collect-all-messages", help="Import the whole mailbox slice instead of requiring address matches."),
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    folders: list[str] = typer.Option([], "--scan-folder", help="Additional Gmail IMAP folder to scan."),
    years_back: Optional[int] = typer.Option(2, "--years-back", help="Convenience window for broad collection when --date-after is omitted."),
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    complaint_query: Optional[str] = None,
    complaint_keyword: list[str] = typer.Option([], "--complaint-keyword", help="Complaint-specific keyword or phrase."),
    min_relevance_score: float = 0.0,
    checkpoint_name: str = "gmail-duckdb-pipeline",
    uid_window_size: int = 500,
    duckdb_build_every_batches: int = 10,
    max_batches: int = 20,
    duckdb_output_dir: Optional[str] = None,
    append_to_existing_corpus: bool = False,
    bm25_search_query: Optional[str] = None,
    bm25_search_limit: int = 20,
    evidence_root: Optional[str] = None,
    gmail_user: Optional[str] = typer.Option(os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER"), "--gmail-user"),
    gmail_app_password: Optional[str] = typer.Option(os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASS"), "--gmail-app-password"),
    use_gmail_oauth: bool = typer.Option(False, "--use-gmail-oauth"),
    gmail_oauth_client_secrets: Optional[str] = typer.Option(os.environ.get("GMAIL_OAUTH_CLIENT_SECRETS"), "--gmail-oauth-client-secrets"),
    gmail_oauth_token_cache: Optional[str] = typer.Option(os.environ.get("GMAIL_OAUTH_TOKEN_CACHE"), "--gmail-oauth-token-cache"),
    gmail_oauth_open_browser: bool = typer.Option(True, "--gmail-oauth-open-browser/--no-gmail-oauth-browser"),
    prompt_for_credentials: bool = typer.Option(False, "--prompt-for-credentials"),
    use_keyring: bool = typer.Option(False, "--use-keyring"),
    save_to_keyring: bool = typer.Option(False, "--save-to-keyring"),
    use_ipfs_secrets_vault: bool = typer.Option(False, "--use-ipfs-secrets-vault"),
    save_to_ipfs_secrets_vault: bool = typer.Option(False, "--save-to-ipfs-secrets-vault"),
) -> None:
    import anyio

    from integrations.ipfs_datasets.legal_data import load_legal_symbol

    resolve_gmail_credentials = load_legal_symbol("resolve_gmail_credentials", module="email_auth")
    run_gmail_duckdb_pipeline = load_legal_symbol("run_gmail_duckdb_pipeline", module="email_pipeline")

    parser = argparse.ArgumentParser(prog="complaint-workspace run-gmail-duckdb-pipeline")
    if not collect_all_messages and not list(address or []):
        parser.error("Provide at least one --address or use --collect-all-messages.")
    if use_gmail_oauth:
        resolved_gmail_user = str(gmail_user or "").strip()
        resolved_gmail_app_password = None
        if not resolved_gmail_user:
            parser.error("--gmail-user is required when --use-gmail-oauth is enabled.")
        if not gmail_oauth_client_secrets:
            parser.error("--gmail-oauth-client-secrets is required when --use-gmail-oauth is enabled.")
    else:
        resolved_gmail_user, resolved_gmail_app_password = resolve_gmail_credentials(
            gmail_user=str(gmail_user or ""),
            gmail_app_password=str(gmail_app_password or ""),
            prompt_for_credentials=prompt_for_credentials,
            use_keyring=use_keyring,
            save_to_keyring_flag=save_to_keyring,
            use_ipfs_secrets_vault=use_ipfs_secrets_vault,
            save_to_ipfs_secrets_vault_flag=save_to_ipfs_secrets_vault,
            parser=parser,
        )

    async def _run_pipeline() -> dict[str, object]:
        return await run_gmail_duckdb_pipeline(
            user_id=user_id,
            addresses=address,
            collect_all_messages=collect_all_messages,
            claim_element_id=claim_element_id,
            folder=folder,
            folders=folders,
            years_back=years_back,
            date_after=date_after,
            date_before=date_before,
            complaint_query=complaint_query,
            complaint_keywords=complaint_keyword,
            min_relevance_score=min_relevance_score,
            workspace_root=service._session_dir,
            evidence_root=Path(evidence_root) if evidence_root else None,
            gmail_user=resolved_gmail_user,
            gmail_app_password=resolved_gmail_app_password,
            use_gmail_oauth=use_gmail_oauth,
            gmail_oauth_client_secrets=gmail_oauth_client_secrets,
            gmail_oauth_token_cache=gmail_oauth_token_cache,
            gmail_oauth_open_browser=gmail_oauth_open_browser,
            checkpoint_name=checkpoint_name,
            uid_window_size=uid_window_size,
            duckdb_build_every_batches=duckdb_build_every_batches,
            max_batches=max_batches,
            duckdb_output_dir=duckdb_output_dir,
            append_to_existing_corpus=append_to_existing_corpus,
            bm25_search_query=bm25_search_query,
            bm25_search_limit=bm25_search_limit,
        )

    _print(anyio.run(_run_pipeline))


@app.command("search-email-duckdb")
def search_email_duckdb_command(
    index_path: str = typer.Option(..., "--index-path"),
    query: str = typer.Option(..., "--query"),
    limit: int = 20,
    ranking: str = typer.Option("bm25", "--ranking"),
    bm25_k1: float = typer.Option(1.2, "--bm25-k1"),
    bm25_b: float = typer.Option(0.75, "--bm25-b"),
) -> None:
    from integrations.ipfs_datasets.legal_data import load_legal_symbol

    search_email_duckdb_corpus = load_legal_symbol("search_email_duckdb_corpus", module="email_pipeline")

    _print(
        search_email_duckdb_corpus(
            index_path=index_path,
            query=query,
            limit=limit,
            ranking=ranking,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b,
        )
    )


@app.command("review")
def review(user_id: str = "demo-user") -> None:
    _print(service.call_mcp_tool("complaint.review_case", {"user_id": user_id}))


@app.command("mediator-prompt")
def mediator_prompt(user_id: str = "demo-user") -> None:
    _print(service.build_mediator_prompt(user_id))


@app.command("complaint-readiness")
def complaint_readiness(user_id: str = "demo-user") -> None:
    _print(service.get_complaint_readiness(user_id))


@app.command("ui-readiness")
def ui_readiness(user_id: str = "demo-user") -> None:
    _print(service.get_ui_readiness(user_id))


@app.command("client-release-gate")
def client_release_gate(user_id: str = "demo-user") -> None:
    _print(service.get_client_release_gate(user_id))


@app.command("capabilities")
def capabilities(user_id: str = "demo-user") -> None:
    _print(service.get_workflow_capabilities(user_id))


@app.command("tooling-contract")
def tooling_contract(user_id: str = "demo-user") -> None:
    _print(service.get_tooling_contract(user_id))


@app.command("workspace-data-schema")
def workspace_data_schema(
    user_id: str = "demo-user",
    manifest_path: Optional[str] = None,
    statefile_path: Optional[str] = None,
    evidence_db_path: Optional[str] = None,
    legal_authority_db_path: Optional[str] = None,
    claim_support_db_path: Optional[str] = None,
) -> None:
    _print(
        service.get_workspace_data_schema(
            user_id,
            manifest_path=manifest_path,
            statefile_path=statefile_path,
            evidence_db_path=evidence_db_path,
            legal_authority_db_path=legal_authority_db_path,
            claim_support_db_path=claim_support_db_path,
        )
    )


@app.command("migrate-legacy-workspace-data")
def migrate_legacy_workspace_data_command(
    user_id: str = "demo-user",
    output_dir: Optional[str] = None,
    statefile_path: Optional[str] = None,
    evidence_db_path: Optional[str] = None,
    legal_authority_db_path: Optional[str] = None,
    claim_support_db_path: Optional[str] = None,
    package_name: Optional[str] = None,
    include_car: bool = True,
) -> None:
    _print(
        service.migrate_legacy_workspace_data(
            user_id,
            output_dir=output_dir,
            statefile_path=statefile_path,
            evidence_db_path=evidence_db_path,
            legal_authority_db_path=legal_authority_db_path,
            claim_support_db_path=claim_support_db_path,
            package_name=package_name,
            include_car=include_car,
        )
    )


@app.command("search-workspace-data")
def search_workspace_data(
    input_path: str,
    query: str,
    input_type: str = "packaged",
    search_backend: str = "bm25",
    top_k: int = 10,
    vector_dimension: int = 32,
    collection_id: Optional[str] = None,
    document_type: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    source_type: Optional[str] = None,
) -> None:
    _print(
        service.search_workspace_dataset(
            input_path,
            input_type=input_type,
            query=query,
            search_backend=search_backend,
            top_k=top_k,
            vector_dimension=vector_dimension,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
    )


@app.command("view-workspace-data")
def view_workspace_data(
    input_path: str,
    input_type: str = "packaged",
    include_document_text: bool = False,
    document_limit: int = 25,
    collection_id: Optional[str] = None,
    document_type: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    source_type: Optional[str] = None,
) -> None:
    _print(
        service.view_workspace_dataset(
            input_path,
            input_type=input_type,
            include_document_text=include_document_text,
            document_limit=document_limit,
            collection_id=collection_id,
            document_type=document_type,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            source_type=source_type,
        )
    )


@app.command("generate")
def generate(
    user_id: str = "demo-user",
    requested_relief: str = "",
    title_override: Optional[str] = None,
    use_llm: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
) -> None:
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    _print(
        service.generate_complaint(
            user_id,
            requested_relief=relief_items or None,
            title_override=title_override,
            use_llm=use_llm,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )
    )


@app.command("update-draft")
def update_draft(
    user_id: str = "demo-user",
    title: Optional[str] = None,
    body: Optional[str] = None,
    requested_relief: str = "",
) -> None:
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    _print(service.update_draft(user_id, title=title, body=body, requested_relief=relief_items or None))


@app.command("build-mike-handoff")
def build_mike_handoff(
    user_id: str = "demo-user",
    mike_base_url: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    generate_draft_if_missing: bool = True,
) -> None:
    _print(
        service.build_mike_handoff(
            user_id,
            mike_base_url=mike_base_url,
            project_id=project_id,
            workspace_id=workspace_id,
            generate_draft_if_missing=generate_draft_if_missing,
        )
    )


@app.command("mike-status")
def mike_status(user_id: str = "demo-user") -> None:
    _print(service.get_mike_integration_status(user_id))


@app.command("sync-mike-draft")
def sync_mike_draft(
    user_id: str = "demo-user",
    body: Optional[str] = typer.Option(None, "--body"),
    title: Optional[str] = None,
    requested_relief: str = "",
    handoff_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    mike_document_id: Optional[str] = None,
    citation_links_json: Optional[str] = typer.Option(None, "--citation-links-json"),
    structured_deltas_json: Optional[str] = typer.Option(None, "--structured-deltas-json"),
    editor_metadata_json: Optional[str] = typer.Option(None, "--editor-metadata-json"),
    redline_summary: Optional[str] = None,
    source_updated_at: Optional[str] = None,
) -> None:
    raw_body = str(body or "")
    if not raw_body.strip():
        raise SystemExit(
            "--body is required and cannot be empty or contain only whitespace. "
            "Intentional leading/trailing whitespace in non-empty bodies is preserved."
        )
    relief_items = [line.strip() for line in requested_relief.split("|") if line.strip()]
    citation_links = _parse_json_option(citation_links_json, option_name="--citation-links-json", expected_json_type=list)
    structured_deltas = _parse_json_option(structured_deltas_json, option_name="--structured-deltas-json", expected_json_type=list)
    editor_metadata = _parse_json_option(editor_metadata_json, option_name="--editor-metadata-json", expected_json_type=dict)
    _print(
        service.sync_mike_final_draft(
            user_id,
            body=raw_body,
            title=title,
            requested_relief=relief_items or None,
            handoff_id=handoff_id,
            project_id=project_id,
            workspace_id=workspace_id,
            mike_document_id=mike_document_id,
            citation_links=citation_links,
            redline_summary=redline_summary,
            source_updated_at=source_updated_at,
            structured_deltas=structured_deltas,
            editor_metadata=editor_metadata,
        )
    )


@app.command("get-draft-proof-report")
@app.command("draft-proof-report")
def draft_proof_report(
    user_id: str = "demo-user",
    state_code: Optional[str] = None,
    allow_live_scrape_fallback: bool = False,
) -> None:
    _print(service.get_draft_proof_report(
        user_id,
        state_code=state_code,
        allow_live_scrape_fallback=allow_live_scrape_fallback,
    ))


@app.command("render-draft-proof-report")
def render_draft_proof_report(
    user_id: str = "demo-user",
    state_code: Optional[str] = None,
    claim_id: str = "",
) -> None:
    _print(service.render_draft_proof_report(
        user_id, state_code=state_code, claim_id=claim_id,
    ))


@app.command("pin-draft-proof-report")
def pin_draft_proof_report(
    user_id: str = "demo-user",
    state_code: Optional[str] = None,
    claim_id: str = "",
) -> None:
    _print(service.pin_draft_proof_report(
        user_id, state_code=state_code, claim_id=claim_id,
    ))


@app.command("score-draft-quality")
def score_draft_quality(
    user_id: str = "demo-user",
    state_code: Optional[str] = None,
    persist: bool = True,
) -> None:
    _print(service.score_draft_quality(user_id, state_code=state_code, persist=persist))


@app.command("improve-draft")
def improve_draft(
    user_id: str = "demo-user",
    state_code: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
    max_suggestions: int = 3,
) -> None:
    _print(service.improve_draft(
        user_id,
        state_code=state_code,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        max_suggestions=max_suggestions,
    ))


@app.command("proof-history")
def proof_history(user_id: str = "demo-user") -> None:
    _print(service.get_proof_history(user_id))


@app.command("export-packet")
def export_packet(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_packet(user_id))


@app.command("export-markdown")
def export_markdown(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_markdown(user_id))


@app.command("export-docx")
def export_docx(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_docx(user_id))


@app.command("export-pdf")
def export_pdf(user_id: str = "demo-user") -> None:
    _print(service.export_complaint_pdf(user_id))


@app.command("analyze-output")
def analyze_output(user_id: str = "demo-user") -> None:
    _print(service.analyze_complaint_output(user_id))


@app.command("formal-diagnostics")
def formal_diagnostics(user_id: str = "demo-user") -> None:
    _print(service.get_formal_diagnostics(user_id))


@app.command("filing-provenance")
def filing_provenance(user_id: str = "demo-user") -> None:
    _print(service.get_filing_provenance(user_id))


@app.command("provider-diagnostics")
def provider_diagnostics(user_id: str = "demo-user") -> None:
    _print(service.get_provider_diagnostics(user_id))


@app.command("router-session-diagnostics")
@_workspace_command_boundary
def router_session_diagnostics(user_id: str = "demo-user") -> None:
    """Read the actual case's encrypted diagnostics without probing a provider."""
    session = service.get_session(user_id)["session"]
    _print((session.get("router_trace") or {}).get("diagnostics") or {"status": "not_dispatched", "prompt_logged": False})


@app.command("router-task-receipt")
@_workspace_command_boundary
def router_task_receipt(user_id: str = "demo-user") -> None:
    session = service.get_session(user_id)["session"]
    _print({"session_retained": True, "receipts": (session.get("router_trace") or {}).get("receipts") or []})


@app.command("router-live-canary")
@_workspace_command_boundary
def router_live_canary(config_path: str = "config.llm_router.json", backend_id: str = "llm-router-grok-4.7", confirm_live: bool = False) -> None:
    """Opt-in synthetic canary. It does not read or send complaint sessions."""

    from backends.llm_router_backend import load_terminal_router_backend

    backend = load_terminal_router_backend(config_path, backend_id)
    _print(backend.run_synthetic_live_canary(confirm_live=confirm_live))


@app.command("docket-view")
def docket_view(
    input_path: str,
    input_type: str = "packaged",
    include_document_text: bool = False,
    document_limit: int = 25,
) -> None:
    _print(
        service.view_docket_dataset(
            input_path,
            input_type=input_type,
            include_document_text=include_document_text,
            document_limit=document_limit,
        )
    )


@app.command("docket-search")
def docket_search(
    input_path: str,
    query: str,
    input_type: str = "packaged",
    search_backend: str = "bm25",
    top_k: int = 10,
    vector_dimension: int = 32,
) -> None:
    _print(
        service.search_docket_dataset(
            input_path,
            input_type=input_type,
            query=query,
            search_backend=search_backend,
            top_k=top_k,
            vector_dimension=vector_dimension,
        )
    )


@app.command("docket-metadata")
def docket_metadata(input_path: str, input_type: str = "packaged") -> None:
    _print(service.get_docket_dataset_metadata(input_path, input_type=input_type))


@app.command("docket-graph")
def docket_graph(input_path: str, input_type: str = "packaged") -> None:
    _print(service.get_docket_dataset_graph(input_path, input_type=input_type))


@app.command("review-exports")
def review_exports(
    user_id: str = "demo-user",
    artifact_path: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    notes: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: Optional[str] = None,
    backend_id: Optional[str] = None,
) -> None:
    _print(
        service.review_generated_exports(
            user_id,
            artifact_path=artifact_path,
            artifact_dir=artifact_dir,
            notes=notes,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
        )
    )


@app.command("set-claim-type")
def set_claim_type(user_id: str = "demo-user", claim_type: str = "retaliation") -> None:
    _print(service.update_claim_type(user_id, claim_type))


@app.command("update-synopsis")
def update_synopsis(user_id: str = "demo-user", synopsis: str = "") -> None:
    _print(service.update_case_synopsis(user_id, synopsis))


@app.command("reset")
def reset(user_id: str = "demo-user") -> None:
    _print(service.reset_session(user_id))


@app.command("review-ui")
def review_ui(
    screenshot_dir: str,
    user_id: str = "demo-user",
    artifact_path: str = "artifacts/ui_review/latest.json",
    iterations: int = 0,
    notes: Optional[str] = None,
    goals: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: str = "config.llm_router.json",
    backend_id: Optional[str] = None,
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
    reuse_existing_screenshots: bool = False,
) -> None:
    goal_items = _split_multiline_values(goals)
    if iterations > 0:
        from complaint_generator.ui_ux_workflow import run_iterative_ui_ux_workflow

        supplemental_artifacts = (
            service._build_complaint_output_review_artifacts(user_id)
            + service._build_cached_ui_readiness_artifacts(user_id)
        )
        result = run_iterative_ui_ux_workflow(
            screenshot_dir=screenshot_dir,
            output_dir=str(Path(artifact_path).expanduser().resolve().parent),
            iterations=iterations,
            provider=provider,
            model=model,
            pytest_target=pytest_target,
            notes=notes,
            goals=goal_items,
            supplemental_artifacts=supplemental_artifacts,
            reuse_existing_screenshots=reuse_existing_screenshots,
        )
        service._persist_ui_readiness(user_id, result)
        _print(result)
        return
    result = run_ui_review_workflow(
        screenshot_dir,
        notes=notes,
        goals=goal_items,
        provider=provider,
        model=model,
        config_path=config_path,
        backend_id=backend_id,
        output_path=artifact_path,
    )
    service._persist_ui_readiness(user_id, result)
    _print(result)


@app.command("optimize-ui")
def optimize_ui(
    screenshot_dir: str,
    user_id: str = "demo-user",
    output_path: str = "artifacts/ui_review/closed-loop",
    max_rounds: int = 2,
    iterations: int = 1,
    notes: Optional[str] = None,
    goals: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    method: str = DEFAULT_UI_UX_OPTIMIZER_METHOD,
    priority: int = DEFAULT_UI_UX_OPTIMIZER_PRIORITY,
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
    reuse_existing_screenshots: bool = False,
) -> None:
    from complaint_generator.ui_ux_workflow import run_closed_loop_ui_ux_improvement

    goal_items = _split_multiline_values(goals)
    supplemental_artifacts = (
        service._build_complaint_output_review_artifacts(user_id)
        + service._build_cached_ui_readiness_artifacts(user_id)
    )
    result = run_closed_loop_ui_ux_improvement(
        screenshot_dir=screenshot_dir,
        output_dir=output_path,
        pytest_target=pytest_target,
        max_rounds=max_rounds,
        review_iterations=iterations,
        provider=provider,
        model=model,
        method=method,
        priority=priority,
        notes=notes,
        goals=goal_items,
        supplemental_artifacts=supplemental_artifacts,
        reuse_existing_screenshots=reuse_existing_screenshots,
    )
    service._persist_ui_readiness(user_id, result)
    _print(result)


@app.command("browser-audit")
def browser_audit(
    screenshot_dir: str = typer.Argument("artifacts/ui-audit/browser-audit"),
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
) -> None:
    from complaint_generator.ui_ux_workflow import run_end_to_end_complaint_browser_audit

    _print(
        run_end_to_end_complaint_browser_audit(
            screenshot_dir=screenshot_dir,
            pytest_target=pytest_target,
        )
    )


@app.command("ui-optimizer-start")
def ui_optimizer_start(
    user_id: str = "demo-user",
    workspace_root: Optional[str] = None,
    artifact_root: Optional[str] = None,
    pytest_target: str = DEFAULT_UI_UX_SCREENSHOT_TARGET,
    max_rounds: int = 2,
    iterations: int = 1,
    notes: Optional[str] = None,
    goals: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    config_path: str = "config.llm_router.json",
    backend_id: Optional[str] = None,
    method: str = DEFAULT_UI_UX_OPTIMIZER_METHOD,
    priority: int = DEFAULT_UI_UX_OPTIMIZER_PRIORITY,
    use_llm_draft: bool = True,
    poll_seconds: float = 1800.0,
    retry_seconds: float = 300.0,
    max_consecutive_errors: int = 0,
    max_cycles: int = 0,
    pid_file: Optional[str] = None,
    status_file: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    from complaint_generator.ui_optimizer_daemon import _start_daemon

    goal_items = _split_multiline_values(goals)
    payload = _start_daemon(
        argparse.Namespace(
            command="start",
            user_id=user_id,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            pytest_target=pytest_target,
            max_rounds=max_rounds,
            iterations=iterations,
            notes=notes,
            goals=goal_items,
            provider=provider,
            model=model,
            config_path=config_path,
            backend_id=backend_id,
            method=method,
            priority=priority,
            use_llm_draft=use_llm_draft,
            poll_seconds=poll_seconds,
            retry_seconds=retry_seconds,
            max_consecutive_errors=max_consecutive_errors,
            max_cycles=max_cycles,
            pid_file=pid_file,
            status_file=status_file,
            log_file=log_file,
            json=True,
        )
    )
    _print(payload)


@app.command("ui-optimizer-status")
def ui_optimizer_status(
    user_id: str = "demo-user",
    workspace_root: Optional[str] = None,
    artifact_root: Optional[str] = None,
    pid_file: Optional[str] = None,
    status_file: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    from complaint_generator.ui_optimizer_daemon import _status_payload

    payload = _status_payload(
        argparse.Namespace(
            command="status",
            user_id=user_id,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            pid_file=pid_file,
            status_file=status_file,
            log_file=log_file,
            json=True,
        )
    )
    _print(payload)


@app.command("ui-optimizer-stop")
def ui_optimizer_stop(
    user_id: str = "demo-user",
    workspace_root: Optional[str] = None,
    artifact_root: Optional[str] = None,
    pid_file: Optional[str] = None,
    status_file: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    from complaint_generator.ui_optimizer_daemon import _stop_daemon

    payload = _stop_daemon(
        argparse.Namespace(
            command="stop",
            user_id=user_id,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            pid_file=pid_file,
            status_file=status_file,
            log_file=log_file,
            json=True,
        )
    )
    _print(payload)


@_workspace_command_boundary
def main() -> None:
    app()


if __name__ == "__main__":
    main()
