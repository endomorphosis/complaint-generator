"""Retire loaded case data after actual key-owner or authenticated-cookie changes."""
import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_ux_07 import _seed, _open, _close, _sign_in, _workspace, DRAFT_BODY

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.mark.parametrize('boundary', ['key-lock', 'logout', 'actor-change'])
def test_loaded_canonical_case_is_retired_after_actual_access_boundary(tmp_path, monkeypatch, boundary):
    world = owner_lawyer_journey_world(tmp_path / 'world')
    inquiry_id, _revision, _evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        before = page.evaluate("""async () => {
            const read = await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
            return {read: read.continuity, alias: window.complaintCanonicalSession && window.complaintCanonicalSession.session.draft.body};
        }""")
        assert before['read']['inquiry_id'] == inquiry_id and before['read']['draft_body'] == DRAFT_BODY
        assert before['alias'] == DRAFT_BODY

        if boundary == 'key-lock':
            # Trusted local key-owner lifecycle; there is no browser unlock API.
            world.service.lock_private_keys()
            world.owner_keys.lock()
        else:
            changed = page.evaluate("""async (boundary) => {
                if (boundary === 'actor-change') {
                    const response = await fetch('/api/complaint-workspace/auth/login', {method:'POST', credentials:'same-origin',
                        headers:{'content-type':'application/json'}, body:JSON.stringify({credential:'synthetic-stranger-credential'})});
                    return {status:response.status, body:await response.json()};
                }
                const session = await fetch('/api/complaint-workspace/auth/session', {credentials:'same-origin'});
                const auth = await session.json();
                const response = await fetch('/api/complaint-workspace/auth/logout', {method:'POST', credentials:'same-origin',
                    headers:{'x-csrf-token':auth.csrf_token || window.workspaceClient.csrfToken}});
                return {status:response.status, body:await response.json()};
            }""", boundary)
            assert changed['status'] == 200
            if boundary == 'actor-change':
                assert changed['body']['principal_id'] == world.stranger.principal_id

        with page.expect_response(lambda response: response.request.method == 'GET'
                and '/api/complaint-workspace/session?case_id=' in response.url) as refused:
            denial = page.evaluate("""async () => {
                try {
                    await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
                    return {resolved:true};
                } catch (error) {return {resolved:false, status:error.status, code:error.code};}
            }""")
        actual = refused.value
        assert denial['resolved'] is False and denial['status'] == actual.status
        if boundary == 'key-lock':
            assert actual.status == 503 and actual.json()['error'] in {'unlock_needed', 'key_unavailable'}
        else:
            assert actual.status in {401, 403}
        page.evaluate('() => window.complaintCaseShell.refresh()')
        page.wait_for_function("() => document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'")
        assert page.input_value('#draft-body') == ''
        assert DRAFT_BODY not in page.locator('body').inner_text()
        retired = page.evaluate("""() => ({
            aliasRetired: window.complaintCanonicalSession == null,
            aliasText: JSON.stringify(window.complaintCanonicalSession || null),
            entry: document.getElementById('complaint-entry').dataset.entry
        })""")
        assert retired['aliasRetired'] and DRAFT_BODY not in retired['aliasText'], retired
    finally:
        _close(playwright, context, node, profile, observed)
