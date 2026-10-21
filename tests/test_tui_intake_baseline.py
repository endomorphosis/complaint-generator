"""Bounded offline characterization of the existing terminal intake.

This module is a baseline smoke, not product acceptance. A passing PTY run
only shows that two synthetic answers pause and resume. Known intake gaps stay
classified as gaps in the baseline receipt.

Diagnostics redact synthetic answer text so the same helper does not print
session payloads if the harness is later pointed at a real session.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = REPO_ROOT / "docs" / "task_boards" / "complaint_tui_baseline_receipt.json"
DEADLINE_SECONDS = 15.0
PAUSE_MESSAGE = "Chat paused. Resume with the same user ID to continue the saved intake."
SMOKE_USER_ID = "pty-synthetic-cimp-tui-01"
EOF_USER_ID = "pty-synthetic-eof"
NARRATIVE_USER_ID = "pty-synthetic-narrative"
UNKNOWN_USER_ID = "pty-synthetic-unknown"
PARTY_ANSWER = "Jordan Example"
OPPOSING_ANSWER = "Acme Company"
NARRATIVE = "My landlord evicted me after my accommodation request."
UNKNOWN_ANSWER = "unknown"
REDACTED = "[redacted]"
_SENSITIVE_JSON_KEYS = (
    "answer",
    "party_name",
    "opposing_party",
    "protected_activity",
    "adverse_action",
    "timeline",
    "harm",
    "court_header",
    "content",
    "case_synopsis",
    "message",
    "placeholder",
    "prompt",
)

CHILD_SCRIPT = r"""
import importlib
import json
import os
import sys
from pathlib import Path

def _install_guards():
    net = importlib.import_module("socket")
    process = importlib.import_module("subprocess")

    class _GuardedSocket(net.socket):
        def connect(self, address):
            raise RuntimeError("network connect blocked")

        def connect_ex(self, address):
            raise RuntimeError("network connect blocked")

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("provider process blocked")

    net.socket = _GuardedSocket
    net.create_connection = _blocked
    process.Popen = _blocked
    process.call = _blocked
    process.check_call = _blocked
    process.check_output = _blocked
    process.run = _blocked
    os.system = _blocked
    for name in (
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
    ):
        if hasattr(os, name):
            setattr(os, name, _blocked)
    return net, process, _GuardedSocket, _blocked

net, process, _GuardedSocket, _blocked = _install_guards()
repo_root = os.environ["TUI_BASELINE_REPO_ROOT"]
if repo_root not in sys.path:
    sys.path.insert(1, repo_root)

session_dir = Path(os.environ["TUI_BASELINE_SESSION_DIR"])
user_id = os.environ["TUI_BASELINE_USER_ID"]
max_turns = 2
if not isinstance(max_turns, int):
    raise SystemExit("max_turns must be a real integer")

import applications.complaint_workspace as workspace

workspace._SESSION_DIR = session_dir
import applications.complaint_cli as cli

cli.service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
proof = {
    "entrypoint": "applications.complaint_cli.chat",
    "max_turns": max_turns,
    "max_turns_is_int": True,
    "user_id": user_id,
    "network_guard_active": net.socket is _GuardedSocket,
    "process_guard_active": process.Popen is _blocked,
}
proof_path = Path(os.environ["TUI_BASELINE_PROOF"])
with proof_path.open("w", encoding="utf-8") as handle:
    json.dump(proof, handle)
    handle.flush()
    os.fsync(handle.fileno())

cli.chat(user_id=user_id, max_turns=max_turns)
"""


@dataclass
class _PtyResult:
    returncode: int
    transcript: str
    elapsed_seconds: float
    proof: dict


def _payloads() -> tuple[str, ...]:
    return (PARTY_ANSWER, OPPOSING_ANSWER, NARRATIVE, UNKNOWN_ANSWER, PAUSE_MESSAGE)


_JSON_PAYLOAD = re.compile(
    r'("(?:'
    + "|".join(re.escape(key) for key in _SENSITIVE_JSON_KEYS)
    + r')"\s*:\s*")(?:\\.|[^"\\])*(")'
)


def _redact(text: str) -> str:
    """Remove synthetic and session-shaped payloads from diagnostic text."""

    redacted = str(text)
    for payload in sorted(_payloads(), key=len, reverse=True):
        if payload:
            redacted = redacted.replace(payload, REDACTED)
    redacted_lines = []
    for line in redacted.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            redacted_lines.append("> " + REDACTED)
            continue
        redacted_lines.append(line)
    redacted = "\n".join(redacted_lines)
    return _JSON_PAYLOAD.sub(lambda match: match.group(1) + REDACTED + match.group(2), redacted)


def _fail(message: str, transcript: str = "") -> None:
    detail = message
    if transcript:
        detail = f"{message}\nredacted_transcript:\n{_redact(transcript)[-1500:]}"
    raise AssertionError(_redact(detail))


def _require_same(label: str, actual: object, expected: object) -> None:
    if actual != expected:
        _fail(f"{label} mismatch; synthetic payload redacted")


def _child_env(home: Path, session_dir: Path, proof_path: Path, user_id: str) -> dict[str, str]:
    env = os.environ.copy()
    prior = env.get("PYTHONPATH", "")
    repo = str(REPO_ROOT)
    parts = [repo]
    if prior:
        parts.extend(entry for entry in prior.split(os.pathsep) if entry and entry != repo)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["HOME"] = str(home)
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_STATE_HOME"] = str(home / ".local" / "state")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TUI_BASELINE_REPO_ROOT"] = repo
    env["TUI_BASELINE_SESSION_DIR"] = str(session_dir)
    env["TUI_BASELINE_PROOF"] = str(proof_path)
    env["TUI_BASELINE_USER_ID"] = user_id
    for name in (
        "COMPLAINT_USE_IPFS_LLM_ROUTER_STATUS",
        "COMPLAINT_USE_IPFS_LEGAL_STATUS",
        "COMPLAINT_LLM_PROVIDER",
        "COMPLAINT_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROK_API_KEY",
        "XAI_API_KEY",
        "HUGGING_FACE_HUB_TOKEN",
        "HF_TOKEN",
    ):
        env.pop(name, None)
    return env


def _install_parent_guards(monkeypatch: pytest.MonkeyPatch, script_path: Path) -> None:
    """Block provider processes and network connects; allow one PTY child argv."""

    net = importlib.import_module("socket")
    allowed = [sys.executable, str(script_path)]
    real_popen = subprocess.Popen

    class _GuardedSocket(net.socket):
        def connect(self, address):
            raise RuntimeError("network connect blocked")

        def connect_ex(self, address):
            raise RuntimeError("network connect blocked")

    def _blocked_connection(*_args, **_kwargs):
        raise RuntimeError("network connect blocked")

    def _guarded_popen(cmd, *args, **kwargs):
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
        if argv != allowed:
            raise RuntimeError("provider process blocked: " + _redact(repr(argv)))
        return real_popen(cmd, *args, **kwargs)

    def _blocked_system(*_args, **_kwargs):
        raise RuntimeError("provider process blocked")

    monkeypatch.setattr(net, "socket", _GuardedSocket)
    monkeypatch.setattr(net, "create_connection", _blocked_connection)
    monkeypatch.setattr(subprocess, "Popen", _guarded_popen)
    monkeypatch.setattr(os, "system", _blocked_system)


def _import_workspace(monkeypatch: pytest.MonkeyPatch, session_dir: Path):
    workspace = importlib.import_module("applications.complaint_workspace")
    monkeypatch.setattr(workspace, "_SESSION_DIR", session_dir)
    cli = sys.modules.get("applications.complaint_cli")
    if cli is not None and hasattr(cli, "service"):
        monkeypatch.setattr(
            cli,
            "service",
            workspace.ComplaintWorkspaceService(root_dir=session_dir),
        )
    return workspace


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _run_pty(
    *,
    script_path: Path,
    home: Path,
    session_dir: Path,
    user_id: str,
    answers: tuple[bytes, ...] = (),
    eof_after_prompt: bool = False,
) -> _PtyResult:
    proof_path = session_dir.parent / f"{user_id}-proof.json"
    env = _child_env(home, session_dir, proof_path, user_id)
    master, slave = os.openpty()
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=str(home),
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)
    flags = fcntl.fcntl(master, fcntl.F_GETFL)
    fcntl.fcntl(master, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    transcript = bytearray()
    sent = 0
    master_open = True
    returncode = 1
    try:
        while True:
            elapsed = time.monotonic() - started
            if elapsed > DEADLINE_SECONDS:
                _fail(
                    f"PTY child exceeded the {DEADLINE_SECONDS:.0f}s deadline",
                    transcript.decode("utf-8", errors="replace"),
                )
            if master_open:
                remaining = max(0.0, DEADLINE_SECONDS - elapsed)
                ready, _, _ = select.select([master], [], [], min(0.1, remaining))
                if ready:
                    try:
                        chunk = os.read(master, 8192)
                    except BlockingIOError:
                        chunk = b""
                    except OSError:
                        chunk = b""
                    if chunk:
                        transcript += chunk
            text = bytes(transcript)
            if eof_after_prompt and master_open and b"bringing the complaint" in text:
                os.close(master)
                master_open = False
            elif not eof_after_prompt and master_open:
                if sent == 0 and b"bringing the complaint" in text:
                    _write_all(master, answers[0] + b"\n")
                    sent += 1
                elif sent == 1 and b"filing against" in text:
                    _write_all(master, answers[1] + b"\n")
                    sent += 1
            if not master_open:
                time.sleep(0.05)
            if proc.poll() is not None:
                if master_open:
                    while True:
                        try:
                            chunk = os.read(master, 8192)
                        except (BlockingIOError, OSError):
                            break
                        if not chunk:
                            break
                        transcript += chunk
                returncode = 1 if proc.returncode is None else int(proc.returncode)
                break
        if proc.poll() is None:
            proc.wait(timeout=max(0.1, DEADLINE_SECONDS - (time.monotonic() - started)))
        returncode = 1 if proc.returncode is None else int(proc.returncode)
    finally:
        if master_open:
            os.close(master)
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=2)
            returncode = 1 if proc.returncode is None else int(proc.returncode)
    elapsed = time.monotonic() - started
    proof: dict = {}
    if proof_path.exists():
        try:
            loaded = json.loads(proof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            proof = loaded
    return _PtyResult(
        returncode=returncode,
        transcript=bytes(transcript).decode("utf-8", errors="replace"),
        elapsed_seconds=elapsed,
        proof=proof,
    )


def _session_path(session_dir: Path, user_id: str) -> Path:
    from applications.complaint_workspace import namespace_filename

    return session_dir / namespace_filename(user_id)


def _load_session(path: Path) -> dict:
    if not path.is_file():
        _fail("persisted session file is absent")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("persisted session is not plaintext JSON")
    if not isinstance(payload, dict):
        _fail("persisted session JSON is not an object")
    return payload


def test_diagnostics_redact_synthetic_session_payloads() -> None:
    sample = "\n".join(
        (
            "> " + PARTY_ANSWER,
            json.dumps(
                {
                    "party_name": PARTY_ANSWER,
                    "opposing_party": OPPOSING_ANSWER,
                    "message": NARRATIVE,
                    "answer": UNKNOWN_ANSWER,
                }
            ),
        )
    )
    redacted = _redact(sample)
    for payload in (PARTY_ANSWER, OPPOSING_ANSWER, NARRATIVE, UNKNOWN_ANSWER):
        if payload in redacted:
            _fail("diagnostic redaction left a synthetic payload in expanded session text")
    if "> " + REDACTED not in redacted:
        _fail("diagnostic redaction did not replace echoed terminal input")


def test_pty_smoke_pauses_and_fresh_service_resumes_same_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real PTY child, two answers, max_turns=2, then a new workspace service."""

    with tempfile.TemporaryDirectory(prefix="tui-baseline-") as raw:
        root = Path(raw)
        session_dir = root / "sessions"
        home = root / "home"
        session_dir.mkdir()
        home.mkdir()
        script_path = root / "_pty_child.py"
        script_path.write_text(CHILD_SCRIPT, encoding="utf-8")
        _install_parent_guards(monkeypatch, script_path)
        workspace = _import_workspace(monkeypatch, session_dir)
        result = _run_pty(
            script_path=script_path,
            home=home,
            session_dir=session_dir,
            user_id=SMOKE_USER_ID,
            answers=(PARTY_ANSWER.encode("utf-8"), OPPOSING_ANSWER.encode("utf-8")),
        )
        if result.returncode != 0:
            _fail(f"PTY chat exited {result.returncode}", result.transcript)
        if result.elapsed_seconds > DEADLINE_SECONDS:
            _fail(f"PTY chat took {result.elapsed_seconds:.3f}s", result.transcript)
        if PAUSE_MESSAGE not in result.transcript:
            _fail("pause/resume message was not displayed", result.transcript)
        if result.proof.get("entrypoint") != "applications.complaint_cli.chat":
            _fail("PTY child did not call applications.complaint_cli.chat", result.transcript)
        if result.proof.get("max_turns_is_int") is not True or result.proof.get("max_turns") != 2:
            _fail("PTY child did not pass integer max_turns=2", result.transcript)
        if result.proof.get("network_guard_active") is not True or result.proof.get("process_guard_active") is not True:
            _fail("PTY child did not install provider and network guards before chat", result.transcript)
        _require_same("proof user id", result.proof.get("user_id"), SMOKE_USER_ID)

        saved = _load_session(_session_path(session_dir, SMOKE_USER_ID))
        answers = saved.get("intake_answers") or {}
        _require_same("user id", saved.get("user_id"), SMOKE_USER_ID)
        _require_same("party answer", answers.get("party_name"), PARTY_ANSWER)
        _require_same("opposing answer", answers.get("opposing_party"), OPPOSING_ANSWER)
        if answers.get("protected_activity"):
            _fail("third intake answer was stored before resume")
        if len(saved.get("intake_history") or []) != 2:
            _fail("persisted intake history did not contain the two synthetic answers")

        fresh = workspace.ComplaintWorkspaceService(root_dir=session_dir)
        again = workspace.ComplaintWorkspaceService(root_dir=session_dir)
        if fresh is again:
            _fail("resume did not construct a fresh workspace service")
        resumed = again.get_session(SMOKE_USER_ID)
        resumed_session = resumed.get("session") or {}
        resumed_answers = resumed_session.get("intake_answers") or {}
        _require_same("resumed user id", resumed_session.get("user_id"), SMOKE_USER_ID)
        _require_same("resumed party answer", resumed_answers.get("party_name"), PARTY_ANSWER)
        _require_same("resumed opposing answer", resumed_answers.get("opposing_party"), OPPOSING_ANSWER)
        next_question = resumed.get("next_question") or {}
        if next_question.get("id") != "protected_activity":
            _fail("fresh service did not resume the same id at the next unanswered question")
        if (resumed_session.get("conversation_state") or {}).get("is_complete") is True:
            _fail("paused session was reported complete")


def _assert_receipt_separates_defects_from_smoke(receipt: dict) -> None:
    if receipt.get("schema_version") != "complaint-generator.tui-baseline-receipt.v1":
        _fail("baseline receipt schema is missing")
    if receipt.get("task_id") != "CIMP-TUI-01":
        _fail("baseline receipt task id is missing")
    if receipt.get("product_acceptance") is not False:
        _fail("baseline receipt marks product acceptance")
    if receipt.get("defect_classification_independent_of_smoke") is not True:
        _fail("baseline receipt does not keep defect classification independent of smoke")
    smoke = receipt.get("baseline_smoke") or {}
    if smoke.get("result") != "pass" or smoke.get("product_acceptance") is not False:
        _fail("baseline smoke result is not recorded separately from product acceptance")
    observations = receipt.get("observations")
    if not isinstance(observations, list):
        _fail("baseline receipt observations are missing")
    by_id = {item.get("id"): item for item in observations if isinstance(item, dict)}
    expected = {
        "TUI-BASE-PTY": "passed_baseline",
        "TUI-BASE-RESUME": "passed_baseline",
        "TUI-GAP-NARRATIVE": "reproduced_gap",
        "TUI-GAP-UNKNOWN": "reproduced_gap",
        "TUI-GAP-GRAPHS": "reproduced_gap",
        "TUI-GAP-EOF": "reproduced_gap",
        "TUI-GAP-PRIVACY": "reproduced_gap",
    }
    for observation_id, classification in expected.items():
        item = by_id.get(observation_id)
        if item is None:
            _fail(f"baseline receipt is missing {observation_id}")
        if item.get("classification") != classification:
            _fail(f"{observation_id} classification does not match the characterization")
        if item.get("product_acceptance") is not False:
            _fail(f"{observation_id} is marked as product acceptance")
        observation = str(item.get("observation") or "")
        if not observation.strip():
            _fail(f"{observation_id} has an empty observation")
        if classification == "reproduced_gap" and item.get("counts_as_smoke_pass") is not False:
            _fail(f"{observation_id} is folded into the baseline smoke pass")
        if classification == "passed_baseline" and item.get("counts_as_smoke_pass") is not True:
            _fail(f"{observation_id} is not part of the baseline smoke")
    narrative = str(by_id["TUI-GAP-NARRATIVE"].get("observation") or "")
    unknown = str(by_id["TUI-GAP-UNKNOWN"].get("observation") or "")
    graphs = str(by_id["TUI-GAP-GRAPHS"].get("observation") or "")
    eof = str(by_id["TUI-GAP-EOF"].get("observation") or "")
    privacy = str(by_id["TUI-GAP-PRIVACY"].get("observation") or "")
    if "party_name" not in narrative:
        _fail("narrative gap observation does not record initial narrative stored as party_name")
    if "Intake complete" not in unknown and "is_complete" not in unknown:
        _fail("unknown-answer gap observation does not record all-unknown completion")
    if "annotation_knowledge_graph" not in graphs or "dependency" not in graphs:
        _fail("graph gap observation does not record the absent factual/dependency graph")
    if "1" not in eof:
        _fail("EOF gap observation does not record exit 1")
    if "plaintext" not in privacy.lower():
        _fail("privacy gap observation does not record plaintext storage")


def test_receipt_records_gaps_independently_of_baseline_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduce current defects as observations. Do not treat them as acceptance."""

    if not RECEIPT_PATH.is_file():
        _fail("baseline receipt file is absent")
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        _fail("baseline receipt is not a JSON object")
    _assert_receipt_separates_defects_from_smoke(receipt)

    with tempfile.TemporaryDirectory(prefix="tui-baseline-gaps-") as raw:
        root = Path(raw)
        session_dir = root / "sessions"
        home = root / "home"
        session_dir.mkdir()
        home.mkdir()
        script_path = root / "_pty_child.py"
        script_path.write_text(CHILD_SCRIPT, encoding="utf-8")
        _install_parent_guards(monkeypatch, script_path)
        workspace = _import_workspace(monkeypatch, session_dir)

        narrative_service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
        narrative_turn = narrative_service.run_intake_chat_turn(NARRATIVE_USER_ID, message=NARRATIVE)
        accepted = narrative_turn.get("accepted_answer") or {}
        if accepted.get("question_id") != "party_name":
            _fail("initial narrative was not stored on the party_name question")
        narrative_state = _load_session(_session_path(session_dir, NARRATIVE_USER_ID))
        _require_same(
            "narrative stored as party_name",
            (narrative_state.get("intake_answers") or {}).get("party_name"),
            NARRATIVE,
        )

        unknown_service = workspace.ComplaintWorkspaceService(root_dir=session_dir)
        questions = list((unknown_service.list_intake_questions().get("questions") or []))
        if len(questions) != 7:
            _fail("intake question count changed; all-unknown characterization needs the seven-field flow")
        for question in questions:
            unknown_service.run_intake_chat_turn(
                UNKNOWN_USER_ID,
                message=UNKNOWN_ANSWER,
                question_id=str(question.get("id") or ""),
            )
        completed = unknown_service.run_intake_chat_turn(UNKNOWN_USER_ID)
        conversation = completed.get("conversation_state") or {}
        if conversation.get("is_complete") is not True:
            _fail("seven unknown answers did not mark conversation_state.is_complete")
        if not str(completed.get("message") or "").startswith("Intake complete"):
            _fail("seven unknown answers did not produce the Intake complete message")
        unknown_state = _load_session(_session_path(session_dir, UNKNOWN_USER_ID))
        unknown_answers = unknown_state.get("intake_answers") or {}
        if len(unknown_answers) != 7:
            _fail("seven unknown answers were not persisted")
        for question in questions:
            _require_same(
                "unknown answer",
                unknown_answers.get(question.get("id")),
                UNKNOWN_ANSWER,
            )
        graph_keys = sorted(key for key in unknown_state if "graph" in str(key))
        if graph_keys != ["annotation_knowledge_graph"]:
            _fail("completed intake session graph keys were not limited to annotation_knowledge_graph")
        if "factual_knowledge_graph" in unknown_state or "dependency_graph" in unknown_state:
            _fail("completed intake session unexpectedly persisted a factual or dependency graph")
        annotation_graph = unknown_state.get("annotation_knowledge_graph") or {}
        if annotation_graph.get("entities") or annotation_graph.get("relationships"):
            _fail("all-unknown completion populated the annotation graph from unresolved answers")

        session_path = _session_path(session_dir, UNKNOWN_USER_ID)
        raw_text = session_path.read_text(encoding="utf-8")
        if not raw_text.startswith("{"):
            _fail("session storage is not plaintext JSON")
        session_mode = session_path.stat().st_mode & 0o777
        # The historical baseline receipt describes its original umask writer.
        # PRIV002 now restricts access while encryption remains a separate gap.
        if session_mode != 0o600:
            _fail("session file permissions are not owner-only 0600")
        if "ciphertext" in raw_text.lower() or "encrypted_payload" in raw_text:
            _fail("session file unexpectedly used an encryption envelope")

        eof = _run_pty(
            script_path=script_path,
            home=home,
            session_dir=session_dir,
            user_id=EOF_USER_ID,
            eof_after_prompt=True,
        )
        if eof.returncode != 1:
            _fail(f"EOF chat exited {eof.returncode} instead of 1", eof.transcript)
        if PAUSE_MESSAGE in eof.transcript:
            _fail("EOF chat produced the pause/resume outcome", eof.transcript)
        if eof.proof.get("network_guard_active") is not True or eof.proof.get("process_guard_active") is not True:
            _fail("EOF child did not install provider and network guards", eof.transcript)
