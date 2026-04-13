from types import SimpleNamespace
from unittest.mock import Mock

from mediator.complaint import Complaint


def test_complaint_generate_includes_support_context_in_prompt():
    mediator = Mock()
    mediator.state = SimpleNamespace(
        inquiries=[
            {
                'question': 'What happened?',
                'answer': 'I was terminated after reporting discrimination.',
            }
        ],
        complaint=None,
    )
    mediator.build_drafting_support_context = Mock(return_value='Support Context:\nStatutes Support:\n- Title VII: Employment discrimination statute')
    mediator.query_backend = Mock(return_value='Generated complaint summary')

    complaint = Complaint(mediator)
    complaint.generate()

    prompt = mediator.query_backend.call_args.args[0]
    assert 'Support Context:' in prompt
    assert 'Title VII' in prompt
    assert mediator.state.complaint == 'Generated complaint summary'


def test_complaint_generate_filters_low_signal_and_deduplicates_long_answers():
    repeated_long_answer = (
        'In October 2025 I requested bifurcation, then in January 2026 I was removed from '
        'the lease and later restored after escalating to county counsel. '
    ) * 4
    mediator = Mock()
    mediator.state = SimpleNamespace(
        inquiries=[
            {'question': 'Timeline?', 'answer': repeated_long_answer},
            {'question': 'Chronology details?', 'answer': repeated_long_answer},
            {'question': 'Who witnessed this?', 'answer': 'defer for later'},
            {'question': 'Documents?', 'answer': 'check the emails'},
            {'question': 'Any appeal?', 'answer': 'yes'},
        ],
        complaint=None,
    )
    mediator.query_backend = Mock(return_value='Generated complaint summary')

    complaint = Complaint(mediator)
    complaint._collect_workspace_evidence_context = Mock(return_value='Workspace Evidence Snapshot:\n- hacc_research: 3 files')
    complaint.generate()

    prompt = mediator.query_backend.call_args.args[0]
    assert 'Lawyer: Timeline?' in prompt
    assert 'Lawyer: Chronology details?' not in prompt
    assert 'defer for later' not in prompt
    assert 'check the emails' not in prompt
    assert '\nPlaintiff: yes' not in prompt


def test_complaint_generate_appends_workspace_snapshot_to_support_context():
    mediator = Mock()
    mediator.state = SimpleNamespace(
        inquiries=[
            {
                'question': 'What happened?',
                'answer': 'Voucher request was delayed and accommodation was denied.',
            }
        ],
        complaint=None,
    )
    mediator.build_drafting_support_context = Mock(return_value='Support Context:\n- Local legal references available')
    mediator.query_backend = Mock(return_value='Generated complaint summary')

    complaint = Complaint(mediator)
    complaint._collect_workspace_evidence_context = Mock(
        return_value='Workspace Evidence Snapshot:\n- hacc_research: 3 files (examples: hacc_research/engine.py)'
    )
    complaint.generate()

    prompt = mediator.query_backend.call_args.args[0]
    assert 'Support Context:' in prompt
    assert 'Workspace Evidence Snapshot:' in prompt
    assert 'hacc_research/engine.py' in prompt