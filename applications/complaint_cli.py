from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Optional

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
from applications.ui_review import run_ui_review_workflow

from .complaint_workspace import ComplaintWorkspaceService


DEFAULT_UI_UX_SCREENSHOT_TARGET = "playwright/tests/complaint-flow.spec.js"
DEFAULT_UI_UX_OPTIMIZER_METHOD = "actor_critic"
DEFAULT_UI_UX_OPTIMIZER_PRIORITY = 90


app = typer.Typer(help="Unified complaint workspace CLI.")
service = ComplaintWorkspaceService()


def _print(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def _split_multiline_values(raw_value: Optional[str]) -> Optional[list[str]]:
    if not raw_value:
        return None
    values = [line.strip() for line in raw_value.splitlines() if line.strip()]
    return values or None


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


@app.command("chat")
def chat(user_id: str = "demo-user", max_turns: int = 0) -> None:
    payload = service.run_intake_chat_turn(user_id)
    accepted_turns = 0

    while True:
        typer.echo(str(payload.get("message") or "").strip())
        inquiry = dict(payload.get("inquiry") or {})
        if not inquiry:
            break
        if max_turns > 0 and accepted_turns >= max_turns:
            typer.echo("Chat paused. Resume with the same user ID to continue the saved intake.")
            break
        answer_text = input("> ").strip()
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

    from ipfs_datasets_py.processors.legal_data.email_auth import resolve_gmail_credentials
    from ipfs_datasets_py.processors.legal_data.email_corpus import (
        build_email_duckdb_artifacts,
        search_email_graphrag_duckdb,
    )
    from ipfs_datasets_py.processors.legal_data.email_import import import_gmail_evidence

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

    from ipfs_datasets_py.processors.legal_data.email_auth import resolve_gmail_credentials
    from ipfs_datasets_py.processors.legal_data.email_pipeline import run_gmail_duckdb_pipeline

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
    from ipfs_datasets_py.processors.legal_data.email_pipeline import search_email_duckdb_corpus

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
