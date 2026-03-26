import json
import imaplib
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import anyio

from complaint_generator.email_import import _imap_mailbox_name, _message_artifact_dir, import_gmail_evidence
from complaint_generator.workspace import ComplaintWorkspaceService


def _build_email_bytes(*, subject: str, sender: str, recipient: str, body: str, attachment_name: str | None = None, attachment_content: bytes | None = None) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message["Date"] = "Tue, 23 Mar 2026 10:00:00 +0000"
    message["Message-ID"] = f"<{subject.replace(' ', '.')}@example.test>"
    message.set_content(body)
    if attachment_name and attachment_content is not None:
        message.add_attachment(
            attachment_content,
            maintype="application",
            subtype="octet-stream",
            filename=attachment_name,
        )
    return message.as_bytes()


class _FakeConnection:
    def __init__(self, messages: list[bytes] | dict[str, list[bytes]], *, fail_large_uid_search_span: int | None = None) -> None:
        if isinstance(messages, dict):
            self._messages_by_folder = messages
        else:
            self._messages_by_folder = {"INBOX": messages}
        self._selected_folder = "INBOX"
        self._fail_large_uid_search_span = fail_large_uid_search_span
        self._uids_by_folder = {
            folder_name: [str(101 + index).encode("ascii") for index in range(len(folder_messages))]
            for folder_name, folder_messages in self._messages_by_folder.items()
        }

    def select(self, folder: str, readonly: bool = True):
        self._selected_folder = str(folder or "").strip('"')
        messages = self._messages_by_folder.get(self._selected_folder, [])
        return "OK", [str(len(messages)).encode("ascii")]

    def search(self, charset, *criteria):
        messages = self._messages_by_folder.get(self._selected_folder, [])
        message_ids = b" ".join(str(index + 1).encode("ascii") for index in range(len(messages)))
        return "OK", [message_ids]

    def status(self, folder: str, query: str):
        selected_folder = str(folder or "").strip('"')
        uids = self._uids_by_folder.get(selected_folder, [])
        uidnext = (max((int(uid.decode("ascii")) for uid in uids), default=100) + 1)
        return "OK", [f'{selected_folder} (UIDNEXT {uidnext})'.encode("utf-8")]

    def fetch(self, message_id: bytes, query: str):
        index = int(message_id.decode("ascii")) - 1
        messages = self._messages_by_folder.get(self._selected_folder, [])
        return "OK", [(b"RFC822", messages[index])]

    def uid(self, command: str, *args):
        command_name = str(command or "").lower()
        if command_name == "search":
            messages = self._messages_by_folder.get(self._selected_folder, [])
            uids = list(self._uids_by_folder.get(self._selected_folder, []))
            criteria = [str(item.decode("ascii") if isinstance(item, bytes) else item) for item in args[1:]]
            if "UID" in criteria:
                uid_index = criteria.index("UID")
                if uid_index + 1 < len(criteria):
                    range_text = str(criteria[uid_index + 1] or "")
                    start_text, end_text = (range_text.split(":", 1) + ["*"])[:2]
                    start_uid = int(start_text or "1")
                    end_uid = None if end_text == "*" else int(end_text or "0")
                    if (
                        self._fail_large_uid_search_span is not None
                        and end_uid is not None
                        and (end_uid - start_uid + 1) > int(self._fail_large_uid_search_span)
                    ):
                        raise imaplib.IMAP4.error("command SEARCH illegal in state SELECTED: got more than 1000000 bytes")
                    filtered_pairs = [
                        (uid, message)
                        for uid, message in zip(uids, messages)
                        if int(uid.decode("ascii")) >= start_uid
                        and (end_uid is None or int(uid.decode("ascii")) <= end_uid)
                    ]
                    uids = [item[0] for item in filtered_pairs]
            return "OK", [b" ".join(uids)]
        if command_name == "fetch":
            uid = args[0]
            uids = self._uids_by_folder.get(self._selected_folder, [])
            index = uids.index(uid)
            messages = self._messages_by_folder.get(self._selected_folder, [])
            return "OK", [(b"RFC822", messages[index])]
        raise AssertionError(f"Unsupported IMAP UID command: {command}")

    def logout(self):
        return "BYE", [b""]


class _FakeProcessor:
    def __init__(self, messages: list[bytes] | dict[str, list[bytes]], *, fail_large_uid_search_span: int | None = None) -> None:
        self.connection = _FakeConnection(messages, fail_large_uid_search_span=fail_large_uid_search_span)
        self.connected = False

    async def connect(self):
        self.connected = True
        return {"status": "success"}

    async def disconnect(self):
        self.connected = False
        return {"status": "success"}


def test_imap_mailbox_name_quotes_gmail_folders_with_spaces():
    assert _imap_mailbox_name("INBOX") == "INBOX"
    assert _imap_mailbox_name("[Gmail]/All Mail") == '"[Gmail]/All Mail"'
    assert _imap_mailbox_name('"[Gmail]/All Mail"') == '"[Gmail]/All Mail"'


def test_message_artifact_dir_uses_uid_sharded_paths(tmp_path):
    path = _message_artifact_dir(
        tmp_path,
        imap_uid=12345,
        message_id_header="<abc@example.test>",
        fallback_index=1,
        date_fragment="20260326",
        subject="Termination email",
    )
    assert path.parent.name == "0012000-0012999"
    assert "uid_0000012345_20260326_Termination-email" in str(path)


def test_import_gmail_evidence_saves_matching_emails_and_attachments(tmp_path, monkeypatch):
    matching_message = _build_email_bytes(
        subject="Termination email",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="Your employment is terminated effective immediately.",
        attachment_name="termination.pdf",
        attachment_content=b"fake-pdf-bytes",
    )
    unrelated_message = _build_email_bytes(
        subject="Newsletter",
        sender="news@example.com",
        recipient="someone@example.com",
        body="This message should be skipped.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([matching_message, unrelated_message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            limit=20,
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["status"] == "success"
    assert payload["searched_message_count"] == 2
    assert payload["imported_count"] == 1
    manifest_path = Path(payload["manifest_path"])
    assert manifest_path.exists()
    imported = payload["imported"][0]

    message_dir = Path(imported["artifact_dir"])
    assert (message_dir / "message.eml").exists()
    assert (message_dir / "message.json").exists()
    assert (message_dir / "attachments" / "termination.pdf").read_bytes() == b"fake-pdf-bytes"

    metadata = json.loads((message_dir / "message.json").read_text())
    assert metadata["subject"] == "Termination email"
    assert metadata["matched_addresses"] == ["hr@example.com", "employee@example.com"]
    assert metadata["raw_size_bytes"] > 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["matched_email_count"] == 1
    assert manifest["raw_email_total_bytes"] == payload["raw_email_total_bytes"]
    assert manifest["emails"][0]["bundle_dir"] == imported["artifact_dir"]
    assert manifest["emails"][0]["email_path"] == imported["eml_path"]

    session = service.get_session("case-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "Email import: Termination email"
    assert "message.eml" in documents[0]["attachment_names"]
    assert "termination.pdf" in documents[0]["attachment_names"]
    assert "message.json" in documents[0]["attachment_names"]


def test_import_gmail_evidence_can_collect_all_messages_without_address_filter(tmp_path, monkeypatch):
    first_message = _build_email_bytes(
        subject="Mailbox-wide email 1",
        sender="alerts@example.com",
        recipient="other@example.com",
        body="This should still be imported in collect-all mode.",
    )
    second_message = _build_email_bytes(
        subject="Mailbox-wide email 2",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="This should also be imported.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([first_message, second_message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=[],
            collect_all_messages=True,
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["collect_all_messages"] is True
    assert payload["matched_addresses"] == []
    assert payload["imported_count"] == 2
    assert payload["skipped_count"] == 0
    assert sorted(item["subject"] for item in payload["imported"]) == ["Mailbox-wide email 1", "Mailbox-wide email 2"]


def test_import_gmail_evidence_can_skip_workspace_persistence_for_bulk_collection(tmp_path, monkeypatch):
    message = _build_email_bytes(
        subject="Bulk mailbox email",
        sender="alerts@example.com",
        recipient="other@example.com",
        body="Imported without touching the complaint session evidence store.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=[],
            collect_all_messages=True,
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            persist_to_workspace=False,
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["persist_to_workspace"] is False
    assert payload["imported_count"] == 1
    assert payload["imported"][0]["workspace_evidence_id"] is None
    session = service.get_session("case-user")["session"]
    assert session["evidence"]["documents"] == []


def test_import_gmail_evidence_filters_by_complaint_relevance(tmp_path, monkeypatch):
    relevant_message = _build_email_bytes(
        subject="Termination hearing request",
        sender="manager@example.com",
        recipient="tenant@example.com",
        body="Retaliation and grievance hearing details are below.",
    )
    irrelevant_message = _build_email_bytes(
        subject="Weekly deals",
        sender="store@example.com",
        recipient="tenant@example.com",
        body="This message should be filtered.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([relevant_message, irrelevant_message]),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["tenant@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            limit=20,
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            complaint_query="termination hearing retaliation grievance",
            min_relevance_score=2.0,
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["searched_message_count"] == 2
    assert payload["imported_count"] == 1
    assert payload["relevance_filtered_count"] == 1
    assert Path(payload["manifest_path"]).exists()
    assert payload["imported"][0]["subject"] == "Termination hearing request"
    assert payload["imported"][0]["relevance_score"] >= 2.0


def test_import_gmail_evidence_scans_multiple_folders_without_duplicate_message_ids(tmp_path, monkeypatch):
    shared_message = _build_email_bytes(
        subject="Termination email",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="Termination details attached.",
    )
    sent_only_message = _build_email_bytes(
        subject="Follow-up to counsel",
        sender="employee@example.com",
        recipient="lawyer@example.com",
        body="Forwarding the termination timeline.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor(
            {
                "INBOX": [shared_message],
                "[Gmail]/All Mail": [shared_message, sent_only_message],
            }
        ),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com", "lawyer@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            folders=["INBOX", "[Gmail]/All Mail"],
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["folders"] == ["INBOX", "[Gmail]/All Mail"]
    assert payload["searched_message_count"] == 3
    assert payload["imported_count"] == 2
    assert sorted(item["subject"] for item in payload["imported"]) == ["Follow-up to counsel", "Termination email"]
    assert {item["folder"] for item in payload["imported"]} == {"INBOX", "[Gmail]/All Mail"}
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["folders"] == ["INBOX", "[Gmail]/All Mail"]
    assert manifest["matched_email_count"] == 2


def test_import_gmail_evidence_can_resume_by_uid_checkpoint(tmp_path, monkeypatch):
    matching_messages = [
        _build_email_bytes(
            subject="Termination email 1",
            sender="hr@example.com",
            recipient="employee@example.com",
            body="First message in mailbox.",
        ),
        _build_email_bytes(
            subject="Termination email 2",
            sender="hr@example.com",
            recipient="employee@example.com",
            body="Second message in mailbox.",
        ),
    ]

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor(matching_messages),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            use_uid_checkpoint=True,
            checkpoint_name="gmail-resume",
            uid_window_size=1,
            service=service,
        )

    first_payload = anyio.run(_run_import)
    second_payload = anyio.run(_run_import)

    assert first_payload["imported_count"] == 1
    assert first_payload["imported"][0]["subject"] == "Termination email 2"
    assert first_payload["checkpoint"]["folders"]["INBOX"]["last_processed_uid"] == 102
    assert first_payload["checkpoint"]["folders"]["INBOX"]["next_uid_upper_bound"] == 101
    assert Path(first_payload["checkpoint_path"]).exists()

    assert second_payload["imported_count"] == 1
    assert second_payload["imported"][0]["subject"] == "Termination email 1"
    assert second_payload["checkpoint"]["folders"]["INBOX"]["last_processed_uid"] == 102


def test_import_gmail_evidence_uid_backfill_adapts_when_search_range_is_too_large(tmp_path, monkeypatch):
    matching_messages = [
        _build_email_bytes(
            subject=f"Termination email {index + 1}",
            sender="hr@example.com",
            recipient="employee@example.com",
            body=f"Mailbox message {index + 1}.",
        )
        for index in range(4)
    ]

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor(matching_messages, fail_large_uid_search_span=2),
    )

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            use_uid_checkpoint=True,
            checkpoint_name="gmail-range-split",
            uid_window_size=2,
            uid_range_span=10,
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["imported_count"] == 2
    assert [item["subject"] for item in payload["imported"]] == [
        "Termination email 4",
        "Termination email 3",
    ]
    folder_state = payload["checkpoint"]["folders"]["INBOX"]
    assert folder_state["checkpoint_strategy"] == "historical_uid_range_backfill"
    assert folder_state["uid_range_span"] == 10
    assert folder_state["next_uid_upper_bound"] == 102
    assert folder_state["historical_backfill_complete"] is False


def test_import_gmail_evidence_resolves_years_back_into_date_after(tmp_path, monkeypatch):
    matching_message = _build_email_bytes(
        subject="Timeline follow-up",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="Following up on the protected activity timeline.",
    )

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: _FakeProcessor([matching_message]),
    )

    class _FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 3, 26, 12, 0, 0, tzinfo=UTC)

        @classmethod
        def fromisoformat(cls, value: str):
            return datetime.fromisoformat(value)

    monkeypatch.setattr("complaint_generator.email_import.datetime", _FixedDatetime)

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            years_back=2,
            gmail_user="user@gmail.com",
            gmail_app_password="app-password",
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["status"] == "success"
    assert payload["years_back"] == 2
    assert payload["date_after"] == "2024-03-26"
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["years_back"] == 2
    assert manifest["date_after"] == "2024-03-26"


def test_import_gmail_evidence_can_use_gmail_oauth(tmp_path, monkeypatch):
    matching_message = _build_email_bytes(
        subject="Termination email",
        sender="hr@example.com",
        recipient="employee@example.com",
        body="Your employment is terminated effective immediately.",
    )
    fake_processor = _FakeProcessor([matching_message])
    oauth_calls = {}

    monkeypatch.setattr(
        "complaint_generator.email_import.create_email_processor",
        lambda **kwargs: fake_processor,
    )
    monkeypatch.setattr(
        "complaint_generator.email_import.resolve_gmail_oauth_access_token",
        lambda **kwargs: ("oauth-access-token", {"expires_at": 1234567890, "refresh_token": "refresh-token"}),
    )

    async def fake_connect_processor_with_xoauth2(processor, *, gmail_user, access_token):
        oauth_calls.update({"processor": processor, "gmail_user": gmail_user, "access_token": access_token})
        processor.connected = True
        return {"status": "success", "auth_mode": "gmail_oauth"}

    monkeypatch.setattr("complaint_generator.email_import._connect_processor_with_xoauth2", fake_connect_processor_with_xoauth2)

    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)
    client_secrets = tmp_path / "client-secrets.json"
    client_secrets.write_text('{"installed":{"client_id":"abc","client_secret":"def","redirect_uris":["http://127.0.0.1"]}}', encoding="utf-8")
    token_cache = tmp_path / "gmail-token.json"

    async def _run_import():
        return await import_gmail_evidence(
            addresses=["hr@example.com", "employee@example.com"],
            user_id="case-user",
            claim_element_id="causation",
            workspace_root=workspace_root,
            evidence_root=evidence_root,
            folder="INBOX",
            gmail_user="user@gmail.com",
            use_gmail_oauth=True,
            gmail_oauth_client_secrets=str(client_secrets),
            gmail_oauth_token_cache=str(token_cache),
            gmail_oauth_open_browser=False,
            service=service,
        )

    payload = anyio.run(_run_import)

    assert payload["auth_mode"] == "gmail_oauth"
    assert oauth_calls["gmail_user"] == "user@gmail.com"
    assert oauth_calls["access_token"] == "oauth-access-token"
    assert payload["gmail_oauth"]["has_refresh_token"] is True
