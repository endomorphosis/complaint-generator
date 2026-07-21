from scripts import validate_task_boards


def test_supervisor_task_board_and_backlog_docs_are_machine_readable() -> None:
    assert validate_task_boards.main() == 0
