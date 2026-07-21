from pathlib import Path

from scripts import validate_task_boards


def test_supervisor_task_board_and_backlog_docs_are_machine_readable() -> None:
    assert validate_task_boards.main() == 0


def test_payload_contract_json_fences_are_parseable() -> None:
    fences = list(validate_task_boards._iter_json_fences(validate_task_boards.PAYLOAD_CONTRACTS))

    assert fences
    assert (
        validate_task_boards._validate_json_fences(
            validate_task_boards.PAYLOAD_CONTRACTS,
            require_json_fence=True,
        )
        == []
    )


def test_json_fence_validation_rejects_malformed_payload_example(tmp_path: Path) -> None:
    contract_doc = tmp_path / "PAYLOAD_CONTRACTS.md"
    contract_doc.write_text(
        "# Payload Contracts\n\n```json\n{\"status\": \"ok\",}\n```\n",
        encoding="utf-8",
    )

    errors = validate_task_boards._validate_json_fences(
        contract_doc,
        repo_root=tmp_path,
        require_json_fence=True,
    )

    assert len(errors) == 1
    assert "json fence 1" in errors[0]
    assert "line 3" in errors[0]


def test_board_validation_allows_future_expected_outputs(tmp_path: Path) -> None:
    source_doc = tmp_path / "docs" / "PAYLOAD_CONTRACTS.md"
    source_doc.parent.mkdir()
    source_doc.write_text("# Payload Contracts\n\n```json\n{\"status\": \"ok\"}\n```\n", encoding="utf-8")
    board = {
        "schema_version": "complaint-generator.supervisor_task_board.v1",
        "source_documents": ["docs/PAYLOAD_CONTRACTS.md"],
        "status_values": sorted(validate_task_boards.VALID_STATUSES),
        "priority_values": sorted(validate_task_boards.VALID_PRIORITIES),
        "supervisor": {
            "task_payload_requirements": list(validate_task_boards.REQUIRED_TASK_FIELDS)
        },
        "tasks": [
            {
                "task_id": "CONTRACT-PAYLOADS",
                "title": "Payload contract validation",
                "source_doc": "docs/PAYLOAD_CONTRACTS.md",
                "status": "validation_required",
                "priority": "P0",
                "target_files": ["tests/test_future_contract_output.py"],
                "acceptance_criteria": ["Future output paths are valid task intent."],
                "validation_commands": ["python -m pytest tests/test_future_contract_output.py -q"],
            }
        ],
    }

    assert validate_task_boards._validate_board(board, repo_root=tmp_path) == []


def test_board_validation_rejects_malformed_task_payload(tmp_path: Path) -> None:
    source_doc = tmp_path / "docs" / "PAYLOAD_CONTRACTS.md"
    source_doc.parent.mkdir()
    source_doc.write_text("# Payload Contracts\n\n```json\n{\"status\": \"ok\"}\n```\n", encoding="utf-8")
    board = {
        "schema_version": "complaint-generator.supervisor_task_board.v1",
        "source_documents": ["docs/PAYLOAD_CONTRACTS.md"],
        "status_values": sorted(validate_task_boards.VALID_STATUSES),
        "priority_values": sorted(validate_task_boards.VALID_PRIORITIES),
        "supervisor": {
            "task_payload_requirements": list(validate_task_boards.REQUIRED_TASK_FIELDS)
        },
        "tasks": [
            {
                "task_id": "bad task id",
                "title": "",
                "source_doc": "/tmp/PAYLOAD_CONTRACTS.md",
                "status": "finished",
                "priority": "P9",
                "target_files": ["/tmp/output.py", "../escape.py", ""],
                "acceptance_criteria": [],
                "validation_commands": ["python -m pytest -q", "python -m pytest -q"],
                "depends_on": ["UNKNOWN"],
            }
        ],
    }

    errors = validate_task_boards._validate_board(board, repo_root=tmp_path)

    assert any("task_id must be uppercase hyphen-delimited" in error for error in errors)
    assert any("title must be a non-empty string" in error for error in errors)
    assert any("invalid status" in error for error in errors)
    assert any("invalid priority" in error for error in errors)
    assert any("source_doc must be repo-relative" in error for error in errors)
    assert any("target_files[0] must be a repo-relative path" in error for error in errors)
    assert any("acceptance_criteria must be a non-empty list" in error for error in errors)
    assert any("validation_commands contains duplicate entry" in error for error in errors)
    assert any("unknown dependency UNKNOWN" in error for error in errors)


def test_markdown_projection_rejects_duplicate_outputs(tmp_path: Path) -> None:
    markdown_path = tmp_path / "ipfs_supervisor_task_board.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# IPFS Supervisor Daemon Task Board",
                "",
                "## SUP-CONTRACT-PAYLOADS Payload contract validation",
                "",
                "- Depends on: PAYLOAD-ROOT",
                "- Outputs: docs/PAYLOAD_CONTRACTS.md, docs/PAYLOAD_CONTRACTS.md",
                "- Source doc: docs/PAYLOAD_CONTRACTS.md",
                "- Canonical task id: CONTRACT-PAYLOADS",
                "- Canonical status: validation_required",
                "",
            ]
        ),
        encoding="utf-8",
    )
    board = {
        "tasks": [
            {
                "task_id": "CONTRACT-PAYLOADS",
                "status": "validation_required",
                "source_doc": "docs/PAYLOAD_CONTRACTS.md",
                "depends_on": ["PAYLOAD-ROOT"],
            }
        ]
    }

    errors = validate_task_boards._validate_markdown_projection(
        board,
        markdown_path=markdown_path,
        repo_root=tmp_path,
    )

    assert (
        "ipfs_supervisor_task_board.md: missing line '- Depends on: SUP-PAYLOAD-ROOT' "
        "for SUP-CONTRACT-PAYLOADS"
    ) in errors
    assert (
        "ipfs_supervisor_task_board.md:6: Outputs contains duplicate entry "
        "'docs/PAYLOAD_CONTRACTS.md'"
    ) in errors
