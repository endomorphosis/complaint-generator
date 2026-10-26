"""Shared case shell for the owner and an assigned reviewer.

The browser is the pinned Chromium. HTTP is the same-origin pipe into the
composed ASGI app. The shell reads the live session, case catalog, and
assignments. It does not invent a second interview record.
"""
from __future__ import annotations

import pytest

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

DESKTOP = {"width": 1440, "height": 1000}
TASKS = ["Overview", "Mediator", "Evidence", "Facts and timeline", "Legal requirements", "Draft", "Team/messages"]


def _open(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux04-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size(DESKTOP)
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _sign_in(page, credential):
    page.fill("#case-credential", credential)
    page.click("#case-login button[type=submit]")
    page.wait_for_function("() => document.getElementById('case-auth-status').textContent.includes('Signed in')")


def _shell(page):
    page.wait_for_function("() => window.complaintCaseShell && document.getElementById('complaint-case-shell-next')")
    return page.evaluate("() => window.complaintCaseShell.snapshot()")


def test_owner_and_reviewer_share_the_case_shell(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        signed_out = _shell(page)
        assert signed_out["case"] == "No case selected"
        assert signed_out["actor"] == "Not signed in"
        assert signed_out["next"] == "Sign in"
        assert signed_out["nextCount"] == 1

        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'
                && document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'"""
        )
        owner = _shell(page)
        assert owner["case"] == "owner-lawyer-journey"
        assert owner["caseId"] == world.case.case_id
        assert owner["actor"] == "Owner"
        assert owner["principalId"] == world.owner.principal_id
        assert owner["privacy"] == "Local private is the default"
        assert owner["stage"]
        assert owner["nextCount"] == 1
        nav = page.eval_on_selector_all(
            "#complaint-case-shell-nav button",
            "nodes => nodes.map(node => node.textContent.trim())",
        )
        assert nav == TASKS
        for label in TASKS:
            page.get_by_role("button", name=label, exact=True).click()
            slug = {
                "Overview": "overview",
                "Mediator": "mediator",
                "Evidence": "evidence",
                "Facts and timeline": "facts",
                "Legal requirements": "legal",
                "Draft": "draft",
                "Team/messages": "team",
            }[label]
            visible = page.evaluate(
                """name => {
                    const panels = Array.from(document.querySelectorAll('[data-case-panel]'));
                    return panels.filter(panel => !panel.hidden).map(panel => panel.getAttribute('data-case-panel'));
                }""",
                slug,
            )
            assert visible == [slug]

        page.fill("#assignment-expires", str(world.now["t"] + 3600))
        page.click("#invite-lawyer button[type=submit]")
        page.wait_for_selector("#assignment-list [data-state='pending']")

        workspace = page.goto(
            browser.SAME_ORIGIN + "/workspace?user_id=" + world.case.tenant_id,
            wait_until="domcontentloaded",
        )
        assert workspace.status == 200
        page.wait_for_function("['ready','partial','denied','error'].includes(document.body.dataset.workspaceHydrated)")
        page.evaluate(
            """payload => window.workspaceClient.setCaseContext(payload)""",
            {
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "revision": world.case.revision,
            },
        )
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-case').dataset.caseId
                && document.getElementById('complaint-case-shell-stage').textContent !== 'Sign-in required'"""
        )
        owner_workspace = _shell(page)
        assert owner_workspace["case"] == owner["case"]
        assert owner_workspace["caseId"] == owner["caseId"]
        assert owner_workspace["actor"] == owner["actor"]
        assert owner_workspace["principalId"] == owner["principalId"]
        assert owner_workspace["privacy"] == owner["privacy"]
        assert owner_workspace["stage"] == owner["stage"]
        assert owner_workspace["next"] == owner["next"]
        assert page.locator("#workspace-case-context-value").inner_text().strip() == owner["case"]
        assert page.locator("[data-tab-target='integrations']").is_visible() is False
        tools = page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/mcp/tools', {credentials: 'same-origin'});
                return {status: response.status, type: response.headers.get('content-type') || ''};
            }"""
        )
        assert tools["status"] != 404
        assert "json" in tools["type"] or tools["status"] in {401, 403}

        page.evaluate("() => { document.getElementById('workspace-locked-state').hidden = false; }")
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-stage').textContent === 'Locked'")
        locked = _shell(page)
        assert locked["privacy"] == "Locked until the private key is available"
        assert locked["next"] == "Unlock the case"
        assert locked["caseId"] == world.case.case_id

        page.goto(browser.SAME_ORIGIN + "/workspace?shell_mode=operator", wait_until="domcontentloaded")
        page.wait_for_function("() => document.body.dataset.caseTaskFlow === 'operator'")
        assert page.locator("[data-tab-target='integrations']").is_visible() is True

        page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        _sign_in(page, "synthetic-lawyer-credential")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'reviewer'
                && document.getElementById('complaint-case-shell-stage').textContent === 'Assignment pending'"""
        )
        reviewer = _shell(page)
        assert reviewer["caseId"] == world.case.case_id
        assert reviewer["actor"] == "Assigned reviewer"
        assert reviewer["principalId"] == world.lawyer.principal_id
        assert reviewer["case"] == "Assigned case"
        assert "grant" not in reviewer["case"].lower()
        assert reviewer["next"] == "Accept the assignment"
        assert reviewer["privacy"].startswith("Locked")
        page.click("#complaint-case-shell-next")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-stage').textContent === 'Assigned review'")
        accepted = _shell(page)
        assert accepted["caseId"] == world.case.case_id
        assert accepted["actor"] == "Assigned reviewer"
        assert accepted["principalId"] == world.lawyer.principal_id
        assert accepted["next"] == "Open the assigned review"
        assert accepted["nextCount"] == 1

        _sign_in(page, "synthetic-stranger-credential")
        page.wait_for_function(
            """() => document.getElementById('complaint-case-shell-actor').textContent.trim() === 'Signed in'"""
        )
        stranger = _shell(page)
        assert stranger["case"] == "No case selected"
        assert stranger["caseId"] == ""
        assert stranger["principalId"] == world.stranger.principal_id
        assert "owner-lawyer-journey" not in page.locator("#complaint-case-shell").inner_text()
        denied = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert denied.status == 200
        page.evaluate(
            """payload => window.workspaceClient.setCaseContext(payload)""",
            {
                "tenant_id": world.case.tenant_id,
                "case_id": world.case.case_id,
                "resource_id": world.case.resource_id,
                "revision": world.case.revision,
            },
        )
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-case-shell-actor').dataset.principalId")
        spoofed = _shell(page)
        assert spoofed["case"] == "No case selected"
        assert spoofed["caseId"] == ""
        assert spoofed["principalId"] == world.stranger.principal_id
        assert page.locator("#workspace-case-context-value").inner_text().strip() != "owner-lawyer-journey"
    finally:
        _close(playwright, context, node, profile, observed)


def test_shell_refuses_a_case_label_from_the_address_bar(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(
            browser.SAME_ORIGIN + "/cases?case_id=" + world.case.case_id + "&label=owner-lawyer-journey",
            wait_until="domcontentloaded",
        )
        assert opened.status == 200
        snapshot = _shell(page)
        assert snapshot["case"] == "No case selected"
        assert snapshot["actor"] == "Not signed in"
        assert world.case.case_id not in page.locator("#complaint-case-shell-case").inner_text()
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)
