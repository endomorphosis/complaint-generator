from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path

import pytest


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_gmail_evidence.py"
    spec = importlib.util.spec_from_file_location("import_gmail_evidence_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_credentials_can_prompt_securely(monkeypatch):
    module = _load_script_module()
    auth_module = importlib.import_module("ipfs_datasets_py.processors.legal_data.email_auth")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="",
        gmail_app_password="",
        prompt_for_credentials=True,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
    )

    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(module.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(auth_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(auth_module.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "user@gmail.com")
    monkeypatch.setattr(auth_module.getpass, "getpass", lambda prompt="": "app-password")

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "app-password"


def test_resolve_credentials_requires_non_interactive_credentials():
    module = _load_script_module()
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="",
        gmail_app_password="",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
    )

    with pytest.raises(SystemExit):
        module._resolve_credentials(args, parser)


def test_resolve_credentials_can_load_password_from_keyring(monkeypatch):
    module = _load_script_module()
    auth_module = importlib.import_module("ipfs_datasets_py.processors.legal_data.email_auth")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="",
        prompt_for_credentials=False,
        use_keyring=True,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
    )

    monkeypatch.setattr(auth_module, "read_password_from_keyring", lambda user: "stored-app-password")

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "stored-app-password"


def test_resolve_credentials_can_save_password_to_keyring(monkeypatch):
    module = _load_script_module()
    auth_module = importlib.import_module("ipfs_datasets_py.processors.legal_data.email_auth")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="provided-app-password",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=True,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
    )
    captured = {}

    monkeypatch.setattr(auth_module, "save_password_to_keyring", lambda user, password, parser_obj: captured.update({"user": user, "password": password}))

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "provided-app-password"
    assert captured == {"user": "user@gmail.com", "password": "provided-app-password"}


def test_resolve_credentials_can_load_password_from_ipfs_secrets_vault(monkeypatch):
    module = _load_script_module()
    auth_module = importlib.import_module("ipfs_datasets_py.processors.legal_data.email_auth")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=True,
        save_to_ipfs_secrets_vault=False,
    )

    monkeypatch.setattr(
        auth_module,
        "read_password_from_ipfs_secrets_vault",
        lambda user: "stored-vault-password",
    )

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "stored-vault-password"


def test_resolve_credentials_supports_gmail_oauth_without_app_password():
    module = _load_script_module()
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="",
        use_gmail_oauth=True,
        gmail_oauth_client_secrets="/tmp/client-secrets.json",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
    )

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == ""


def test_resolve_credentials_can_save_password_to_ipfs_secrets_vault(monkeypatch):
    module = _load_script_module()
    auth_module = importlib.import_module("ipfs_datasets_py.processors.legal_data.email_auth")
    parser = argparse.ArgumentParser()
    args = argparse.Namespace(
        gmail_user="user@gmail.com",
        gmail_app_password="provided-app-password",
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=True,
    )
    captured = {}

    monkeypatch.setattr(
        auth_module,
        "save_password_to_ipfs_secrets_vault",
        lambda user, password, parser_obj: captured.update({"user": user, "password": password}),
    )

    gmail_user, gmail_password = module._resolve_credentials(args, parser)

    assert gmail_user == "user@gmail.com"
    assert gmail_password == "provided-app-password"
    assert captured == {"user": "user@gmail.com", "password": "provided-app-password"}


def test_build_parser_exposes_years_back_and_duckdb_flags():
    module = _load_script_module()

    help_text = module.build_parser().format_help()

    assert "--years-back" in help_text
    assert "--build-duckdb-index" in help_text
    assert "--duckdb-output-dir" in help_text
    assert "--append-duckdb-index" in help_text
    assert "--bm25-search-query" in help_text
    assert "--bm25-search-limit" in help_text
