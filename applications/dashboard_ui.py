from copy import deepcopy
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from .fastapi_compat import attach_router_routes


@dataclass(frozen=True)
class DashboardEntry:
    slug: str
    title: str
    template_name: str
    summary: str
    category: str


@dataclass(frozen=True)
class DashboardFixtures:
    complaint_links: tuple[tuple[str, str], ...]
    ipfs_entries: tuple[DashboardEntry, ...]
    ipfs_entry_map: dict[str, DashboardEntry]
    layperson_hub_advanced_dashboard_slugs: frozenset[str]
    capability_cards: tuple[dict[str, Any], ...]
    journey_detail_panels: tuple[dict[str, Any], ...]
    package_capability_matrix: tuple[dict[str, Any], ...]
    improvement_plan_items: tuple[tuple[str, str], ...]
    entry_path_cards: tuple[dict[str, Any], ...]
    dashboard_subsection_index: tuple[dict[str, Any], ...]


def _first_present(candidates: tuple[Path, ...]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


_COMPLAINT_REPO_ROOT = Path(__file__).resolve().parent.parent
_IPFS_DATASETS_REPO = _first_present(
    (
        _COMPLAINT_REPO_ROOT / "external" / "ipfs_datasets_py",
        _COMPLAINT_REPO_ROOT / "ipfs_datasets_py",
    )
)
_IPFS_DATASETS_TEMPLATES_DIR = _IPFS_DATASETS_REPO / "ipfs_datasets_py" / "templates"
_IPFS_DATASETS_STATIC_DIR = _IPFS_DATASETS_REPO / "ipfs_datasets_py" / "static"

_COMPLAINT_DASHBOARD_LINKS = [
    ("Start", "/"),
    ("Account", "/home"),
    ("Guided questions", "/chat"),
    ("Profile", "/profile"),
    ("Results", "/results"),
    ("Saved work", "/workspace"),
    ("Proof review", "/claim-support-review"),
    ("Build draft", "/document"),
    ("Edit document", "/wysiwyg"),
    ("Draft history", "/document/optimization-trace"),
    ("All dashboards", "/dashboards"),
]

_IPFS_DASHBOARD_ENTRIES = [
    DashboardEntry("mcp", "IPFS Datasets MCP Dashboard", "mcp_dashboard.html", "Primary MCP datasets console.", "IPFS Datasets"),
    DashboardEntry("mcp-clean", "IPFS Datasets MCP Dashboard Clean", "mcp_dashboard_clean.html", "Clean MCP datasets management surface.", "IPFS Datasets"),
    DashboardEntry("mcp-final", "IPFS Datasets MCP Dashboard Final", "mcp_dashboard_final.html", "Final MCP dashboard variant.", "IPFS Datasets"),
    DashboardEntry("software-mcp", "Software Engineering Dashboard", "software_dashboard_mcp.html", "Software workflow and theorem dashboard.", "IPFS Datasets"),
    DashboardEntry("investigation", "Unified Investigation Dashboard", "unified_investigation_dashboard.html", "Investigation dashboard template.", "IPFS Datasets"),
    DashboardEntry("investigation-mcp", "Unified Investigation Dashboard MCP", "unified_investigation_dashboard_mcp.html", "Investigation dashboard with MCP integration.", "IPFS Datasets"),
    DashboardEntry("news-analysis", "News Analysis Dashboard", "news_analysis_dashboard.html", "Original news analysis dashboard.", "IPFS Datasets"),
    DashboardEntry("news-analysis-improved", "News Analysis Dashboard Improved", "news_analysis_dashboard_improved.html", "Enhanced news analysis dashboard.", "IPFS Datasets"),
    DashboardEntry("admin-index", "Admin Dashboard Home", "admin/index.html", "Administrative dashboard landing page.", "Admin Dashboards"),
    DashboardEntry("admin-login", "Admin Dashboard Login", "admin/login.html", "Administrative authentication surface.", "Admin Dashboards"),
    DashboardEntry("admin-error", "Admin Dashboard Error", "admin/error.html", "Administrative error surface.", "Admin Dashboards"),
    DashboardEntry("admin-analytics", "Analytics Dashboard", "admin/analytics_dashboard.html", "Analytics dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-rag-query", "RAG Query Dashboard", "admin/rag_query_dashboard.html", "RAG query dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-investigation", "Admin Investigation Dashboard", "admin/investigation_dashboard.html", "Administrative investigation dashboard.", "Admin Dashboards"),
    DashboardEntry("admin-caselaw", "Caselaw Dashboard", "admin/caselaw_dashboard.html", "Caselaw dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-caselaw-mcp", "Caselaw MCP Dashboard", "admin/caselaw_dashboard_mcp.html", "Caselaw dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-finance-mcp", "Finance MCP Dashboard", "admin/finance_dashboard_mcp.html", "Finance dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-finance-workflow", "Finance Workflow Dashboard", "admin/finance_workflow_dashboard.html", "Finance workflow dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-medicine-mcp", "Medicine MCP Dashboard", "admin/medicine_dashboard_mcp.html", "Medicine dashboard with MCP integration.", "Admin Dashboards"),
    DashboardEntry("admin-patent", "Patent Dashboard", "admin/patent_dashboard.html", "Patent dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-discord", "Discord Dashboard", "admin/discord_dashboard.html", "Discord workflow dashboard.", "Admin Dashboards"),
    DashboardEntry("admin-graphrag", "GraphRAG Dashboard", "admin/graphrag_dashboard.html", "GraphRAG dashboard entry point.", "Admin Dashboards"),
    DashboardEntry("admin-mcp", "Admin MCP Dashboard", "admin/mcp_dashboard.html", "Administrative MCP dashboard.", "Admin Dashboards"),
]

_LAYPERSON_HUB_ADVANCED_DASHBOARD_SLUGS = {
    "mcp",
    "software-mcp",
    "investigation",
    "admin-index",
    "admin-analytics",
    "admin-rag-query",
    "admin-investigation",
    "admin-caselaw",
    "admin-caselaw-mcp",
    "admin-finance-mcp",
    "admin-finance-workflow",
    "admin-medicine-mcp",
    "admin-patent",
    "admin-discord",
    "admin-graphrag",
    "admin-mcp",
}

_CAPABILITY_CARDS = [
    {
        "anchor": "journey-intake-chat",
        "title": "Intake Chat and Guided Advice",
        "summary": "Start with the conversational intake surface when you need help turning a narrative into claims, facts, proof leads, and next questions.",
        "primary": ("Open Intake Chat", "/chat"),
        "secondary": ("Review Claim Support", "/claim-support-review"),
        "features": [
            "Guided intake prompts",
            "Claim-support review",
            "Follow-up question queue",
            "Formal complaint handoff",
        ],
        "subsections": [
            ("Workspace snapshot", "#dashboard-workspace-snapshot"),
            ("Heads-up display", "#heads-up-display-dashboard"),
            ("Document builder", "/document"),
        ],
    },
    {
        "anchor": "journey-workspace-evidence",
        "title": "Resume a Complaint and Marshal Evidence, Law, and Caselaw",
        "summary": "Resume an existing workspace, upload files, import local/Gmail evidence, annotate dataset documents, and package evidence, legal authority, and caselaw into workspace datasets.",
        "primary": ("Open Workspace", "/workspace"),
        "secondary": ("Upload Evidence", "#chat-upload-dashboard"),
        "features": [
            "Workspace session continuity",
            "Evidence, law, and caselaw marshalling",
            "Workspace dataset parquet review",
            "MCP tool calls through the browser SDK",
        ],
        "subsections": [
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Law and caselaw filters", "#workspace-law-caselaw-tools"),
            ("Document annotation", "#dataset-document-annotation-dashboard"),
            ("MCP tools", "/api/complaint-workspace/mcp/tools"),
        ],
    },
    {
        "anchor": "journey-docket-dataset",
        "title": "Inspect Dockets and Existing Complaints",
        "summary": "Load packaged dockets or docket dataset parquet files, search filings, extract calendar events, and inspect graph connections.",
        "primary": ("Open Docket Dataset", "#docket-dataset-parquet-dashboard"),
        "secondary": ("Packaged Docket", "#packaged-docket-dashboard"),
        "features": [
            "Packaged docket dashboards",
            "BM25 or vector dataset search",
            "Case calendar extraction",
            "Docket knowledge graph view",
        ],
        "subsections": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket parquet", "#docket-dataset-parquet-dashboard"),
            ("Operator queue", "#heads-up-display-dashboard"),
        ],
    },
    {
        "anchor": "journey-profile",
        "title": "Profile, Identity and Personal Context",
        "summary": "Manage personal/profile context, cookies, decentralized workspace identity, and the session data used to resume work safely.",
        "primary": ("Open Profile", "/profile"),
        "secondary": ("View Cookies", "/cookies"),
        "features": [
            "Profile and cookie surfaces",
            "Decentralized workspace IDs",
            "Reusable user/session query params",
            "Cross-tab MCP sync events",
        ],
        "subsections": [
            ("Workspace session", "#dashboard-workspace-snapshot"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
            ("MCP dashboard", "/mcp"),
        ],
    },
]

_JOURNEY_DETAIL_PANELS = [
    {
        "anchor": "intake-chat-workflow-panel",
        "eyebrow": "Intake advice path",
        "title": "From story to reviewable claim theory",
        "description": "Use the intake chat when the user needs advice, fact gathering, claim disambiguation, and a clean handoff into evidence review or drafting.",
        "steps": [
            ("Start intake", "Open the chat surface and capture the narrative, parties, timeline, harms, and remedies."),
            ("Review support", "Move into claim-support review to identify missing elements, unresolved questions, and evidence tasks."),
            ("Draft handoff", "Send supported facts and remaining caveats to the document builder when the workspace is ready."),
        ],
        "links": [
            ("Open intake chat", "/chat"),
            ("Claim-support review", "/claim-support-review"),
            ("Complaint builder", "/document"),
            ("Heads-up display", "#heads-up-display-dashboard"),
        ],
    },
    {
        "anchor": "workspace-evidence-workflow-panel",
        "eyebrow": "Workspace evidence path",
        "title": "Resume a complaint and marshal evidence, law, and caselaw",
        "description": "Use the workspace path when the user has an existing session, files, notes, mail exports, legal authority, caselaw, or dataset documents that need to become structured workspace records.",
        "steps": [
            ("Load session", "Recover the workspace by user ID and show the current intake, evidence, draft, and readiness state."),
            ("Add records", "Upload files or annotate loaded dataset documents into the complaint workspace evidence and authority record."),
            ("Filter by legal role", "Separate factual evidence, legal authority, caselaw, and claim-support records before graph or drafting handoff."),
            ("Inspect dataset", "Search workspace parquet, graph links, vector documents, logic statements, proof artifacts, and ZK certificates."),
        ],
        "links": [
            ("Workspace snapshot", "#dashboard-workspace-snapshot"),
            ("Upload evidence", "#chat-upload-dashboard"),
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Law and caselaw filters", "#workspace-law-caselaw-tools"),
            ("Document annotation", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "docket-complaint-workflow-panel",
        "eyebrow": "Docket review path",
        "title": "Inspect an existing docket or complaint dataset",
        "description": "Use the docket path when the user wants to examine filings, packaged docket manifests, search results, hearing dates, deadlines, and graph projections.",
        "steps": [
            ("Load docket", "Open a packaged docket manifest or a docket dataset parquet file."),
            ("Search filings", "Query filings, motions, deadlines, orders, hearings, or due-process events from the dataset view."),
            ("Promote findings", "Use annotation and workspace handoffs to connect useful docket facts back to the active complaint."),
        ],
        "links": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket dataset", "#docket-dataset-parquet-dashboard"),
            ("Case calendar", "#dashboard-docket-calendar-list"),
            ("Annotate document", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "profile-identity-workflow-panel",
        "eyebrow": "Profile and identity path",
        "title": "Manage personal context and session continuity",
        "description": "Use the profile path when the user needs profile data, cookies, decentralized workspace IDs, SDK sync context, or a stable way to resume prior work.",
        "steps": [
            ("Check profile", "Open profile and cookie surfaces to confirm the user context that follows dashboard links."),
            ("Carry context", "Use the context bar and query-param links to keep user ID, claim type, and workspace state aligned."),
            ("Use MCP tools", "Inspect MCP tools, SDK playground behavior, and legacy IPFS dashboards from the same server shell."),
        ],
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("MCP dashboard", "/mcp"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
        ],
    },
]

_PACKAGE_CAPABILITY_MATRIX = [
    {
        "title": "Intake and Advice",
        "description": "Conversation, claim disambiguation, follow-up questions, readiness checks, and drafting handoff.",
        "links": [
            ("Chat", "/chat"),
            ("Review", "/claim-support-review"),
            ("Build draft", "/document"),
            ("Readiness API", "/api/complaint-workspace/session"),
        ],
    },
    {
        "title": "Workspace Evidence and Authority",
        "description": "Session recovery, uploads, Gmail/DuckDB imports, evidence annotations, legal authority DB paths, and workspace parquet search.",
        "links": [
            ("Workspace", "/workspace"),
            ("Upload", "#chat-upload-dashboard"),
            ("Workspace dataset", "#workspace-dataset-parquet-dashboard"),
            ("Annotation graph", "/api/complaint-workspace/document-annotations/graph"),
        ],
    },
    {
        "title": "Law, Caselaw, and Legal Graph",
        "description": "Legal authority/caselaw review, claim-to-law matching, graph analysis gates, deontic modalities, and authority-focused drafting blockers.",
        "links": [
            ("Caselaw dashboard", "/dashboards/ipfs-datasets/admin-caselaw"),
            ("Caselaw MCP", "/dashboards/ipfs-datasets/admin-caselaw-mcp"),
            ("Legal graph filters", "#workspace-knowledge-graph-tools"),
            ("Deontic analyzer", "#workspace-deontic-logic-tools"),
        ],
    },
    {
        "title": "Dockets and Existing Complaints",
        "description": "Packaged docket manifests, docket parquet search, case-calendar extraction, graph projection, and document annotation into a complaint workspace.",
        "links": [
            ("Packaged docket", "#packaged-docket-dashboard"),
            ("Docket dataset", "#docket-dataset-parquet-dashboard"),
            ("Docket graph API", "/api/complaint-workspace/docket-dataset/graph"),
            ("Calendar preview", "#dashboard-docket-calendar-list"),
        ],
    },
    {
        "title": "Profile, Identity, and MCP Operations",
        "description": "Profile data, cookies, decentralized workspace IDs, MCP tools, JSON-RPC calls, SDK playground, and legacy IPFS dashboards.",
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("MCP dashboard", "/mcp"),
            ("SDK playground", "/ipfs-datasets/sdk-playground"),
        ],
    },
]

_IMPROVEMENT_PLAN_ITEMS = [
    (
        "Unify entry navigation",
        "Keep the dashboard organized by user journey first, then by lower-level data surfaces: intake, workspace evidence, law/caselaw, docket review, profile, graph/logic, and legacy IPFS dashboards.",
    ),
    (
        "Promote real package capabilities",
        "Expose existing APIs for intake chat, workspace uploads, Gmail/DuckDB ingestion, legal authority database paths, parquet dataset review, graph exploration, deontic analysis, caselaw dashboards, and formal complaint generation as visible actions.",
    ),
    (
        "Tie dashboards together with context",
        "Carry user_id, manifest_path, docket dataset path, and workspace dataset path through links so users can move between chat, workspace, review, builder, and dashboard cards without losing state.",
    ),
    (
        "Make graph and logic inspectable",
        "Split connections, duties, proof artifacts, and certificate counts into clear dashboard subsections with filters already backed by the workspace dataset graph endpoint.",
    ),
    (
        "Separate evidence, law, and caselaw lanes",
        "Add source/document-type presets so users can quickly inspect factual evidence, legal authority, caselaw, claim-support records, and graph/deontic consequences from the workspace dataset.",
    ),
    (
        "Keep legacy dashboards discoverable",
        "Mount every ipfs_datasets_py dashboard in the hub, but frame them as advanced/legacy package consoles instead of making users guess which template matters for a complaint workflow.",
    ),
]


_ENTRY_PATH_CARDS = [
    {
        "anchor": "entry-path-intake",
        "stage": "Path 1",
        "title": "Start your complaint",
        "description": "Answer guided questions, describe what happened, and turn your story into a clear timeline, people involved, harms, and possible claims.",
        "primary": ("Start with guided questions", "/chat"),
        "links": [
            ("Check what still needs proof", "/claim-support-review"),
            ("See next recommended step", "#heads-up-display-dashboard"),
            ("Build a draft later", "/document"),
        ],
    },
    {
        "anchor": "entry-path-workspace",
        "stage": "Path 2",
        "title": "Continue your complaint",
        "description": "Return to a saved complaint, add documents or messages, organize evidence, add laws and court cases, and keep everything together for review.",
        "primary": ("Continue saved complaint", "#dashboard-workspace-snapshot"),
        "links": [
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Add review notes", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "anchor": "entry-path-docket",
        "stage": "Path 3",
        "title": "Review a court docket or response",
        "description": "Look through filings, deadlines, hearing dates, orders, or an existing complaint/response and bring useful facts back into your workspace.",
        "primary": ("Review docket or filing", "#docket-dataset-parquet-dashboard"),
        "links": [
            ("Load docket package", "#packaged-docket-dashboard"),
            ("Find hearing dates", "#dashboard-docket-calendar-list"),
            ("Map docket connections", "/api/complaint-workspace/docket-dataset/graph"),
        ],
    },
    {
        "anchor": "entry-path-profile",
        "stage": "Path 4",
        "title": "Manage your profile",
        "description": "Review the personal and session information used to resume your work. Technical tools stay separate so they do not interrupt the complaint path.",
        "primary": ("Open profile", "/profile"),
        "links": [
            ("Cookies", "/cookies"),
            ("Session tools", "/mcp"),
            ("Technical tools", "#dashboard-advanced-tools"),
        ],
    },
]

_DASHBOARD_SUBSECTION_INDEX = [
    {
        "title": "Start and Review",
        "description": "Guided questions, proof checks, next recommended action, and draft handoff.",
        "links": [
            ("Start guided questions", "/chat"),
            ("Check proof gaps", "/claim-support-review"),
            ("See next step", "#heads-up-display-dashboard"),
            ("Build draft", "/document"),
        ],
    },
    {
        "title": "Evidence, Laws, and Court Cases",
        "description": "Resume a complaint, upload files, organize source materials, find connections, and check duties or conflicts.",
        "links": [
            ("Saved complaint", "#dashboard-workspace-snapshot"),
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Find connections", "#workspace-knowledge-graph-tools"),
            ("Check duties/conflicts", "#workspace-deontic-logic-tools"),
        ],
    },
    {
        "title": "Court Dockets and Responses",
        "description": "Load docket records, search filings, preview calendar events, and save useful notes.",
        "links": [
            ("Load docket package", "#packaged-docket-dashboard"),
            ("Search docket", "#docket-dataset-parquet-dashboard"),
            ("Find dates", "#dashboard-docket-calendar-list"),
            ("Add notes", "#dataset-document-annotation-dashboard"),
        ],
    },
    {
        "title": "Profile and Technical Tools",
        "description": "Profile, cookies, session tools, and optional technical package consoles.",
        "links": [
            ("Profile", "/profile"),
            ("Cookies", "/cookies"),
            ("Technical tools", "/api/complaint-workspace/mcp/tools"),
            ("Package consoles", "#legacy-ipfs-dashboard-shells"),
        ],
    },
]


def build_complaint_dashboard_links_fixture() -> tuple[tuple[str, str], ...]:
    return tuple(_COMPLAINT_DASHBOARD_LINKS)


def build_ipfs_dashboard_entries_fixture() -> tuple[DashboardEntry, ...]:
    return tuple(_IPFS_DASHBOARD_ENTRIES)


def build_layperson_dashboard_hub_fixture() -> dict[str, Any]:
    return {
        "advanced_dashboard_slugs": frozenset(
            _LAYPERSON_HUB_ADVANCED_DASHBOARD_SLUGS
        ),
        "capability_cards": tuple(deepcopy(_CAPABILITY_CARDS)),
        "journey_detail_panels": tuple(deepcopy(_JOURNEY_DETAIL_PANELS)),
        "package_capability_matrix": tuple(deepcopy(_PACKAGE_CAPABILITY_MATRIX)),
        "improvement_plan_items": tuple(_IMPROVEMENT_PLAN_ITEMS),
        "entry_path_cards": tuple(deepcopy(_ENTRY_PATH_CARDS)),
        "dashboard_subsection_index": tuple(deepcopy(_DASHBOARD_SUBSECTION_INDEX)),
    }


def build_dashboard_fixture_data() -> DashboardFixtures:
    """Return the reusable fixture catalog used by dashboard routes and tests."""
    ipfs_entries = build_ipfs_dashboard_entries_fixture()
    hub_fixture = build_layperson_dashboard_hub_fixture()
    return DashboardFixtures(
        complaint_links=build_complaint_dashboard_links_fixture(),
        ipfs_entries=ipfs_entries,
        ipfs_entry_map={entry.slug: entry for entry in ipfs_entries},
        layperson_hub_advanced_dashboard_slugs=hub_fixture[
            "advanced_dashboard_slugs"
        ],
        capability_cards=hub_fixture["capability_cards"],
        journey_detail_panels=hub_fixture["journey_detail_panels"],
        package_capability_matrix=hub_fixture["package_capability_matrix"],
        improvement_plan_items=hub_fixture["improvement_plan_items"],
        entry_path_cards=hub_fixture["entry_path_cards"],
        dashboard_subsection_index=hub_fixture["dashboard_subsection_index"],
    )


_DASHBOARD_FIXTURES = build_dashboard_fixture_data()


def get_dashboard_fixtures() -> DashboardFixtures:
    """Return the process-wide fixture catalog used by the live dashboard routes."""
    return _DASHBOARD_FIXTURES


def _resolve_dashboard_fixtures(
    fixtures: DashboardFixtures | None,
) -> DashboardFixtures:
    return fixtures if fixtures is not None else get_dashboard_fixtures()


def get_ipfs_dashboard_entry(
    slug: str,
    *,
    fixtures: DashboardFixtures | None = None,
) -> DashboardEntry | None:
    return _resolve_dashboard_fixtures(fixtures).ipfs_entry_map.get(str(slug or ""))


def get_default_ipfs_dashboard_entry(
    *,
    fixtures: DashboardFixtures | None = None,
) -> DashboardEntry:
    resolved_fixtures = _resolve_dashboard_fixtures(fixtures)
    default_entry = resolved_fixtures.ipfs_entry_map.get("mcp")
    if default_entry is not None:
        return default_entry
    if resolved_fixtures.ipfs_entries:
        return resolved_fixtures.ipfs_entries[0]
    raise ValueError("Dashboard fixtures must define at least one IPFS dashboard entry")


def _render_feature_chips(features: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(feature)}</span>' for feature in features)


def _render_link_row(links: list[tuple[str, str]]) -> str:
    return "".join(
        f'<a class="jump-link" href="{escape(href)}">{escape(label)}</a>'
        for label, href in links
    )


def _render_subsection_nav(label: str, links: list[tuple[str, str]]) -> str:
    return f"""
    <nav class="dashboard-subsection-nav" aria-label="{escape(label)}">
        <span>{escape(label)}</span>
        <div class="section-jump-row">{_render_link_row(links)}</div>
    </nav>
    """


def _render_entry_path_cards(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.entry_path_cards:
        primary_label, primary_href = item["primary"]
        cards.append(
            f"""
            <article class="entry-path-card" id="{escape(item["anchor"])}">
                <div class="entry-path-stage">{escape(item["stage"])}</div>
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <a class="primary-action" href="{escape(primary_href)}">{escape(primary_label)}</a>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_dashboard_subsection_index(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.dashboard_subsection_index:
        cards.append(
            f"""
            <article class="subsection-index-card">
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_capability_cards(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.capability_cards:
        primary_label, primary_href = item["primary"]
        secondary_label, secondary_href = item["secondary"]
        cards.append(
            f"""
            <article class="capability-card" id="{escape(item["anchor"])}">
                <div class="capability-card-body">
                    <h3>{escape(item["title"])}</h3>
                    <p>{escape(item["summary"])}</p>
                    <div class="chip-row">{_render_feature_chips(list(item["features"]))}</div>
                </div>
                <div class="capability-actions">
                    <a class="primary-action" href="{escape(primary_href)}">{escape(primary_label)}</a>
                    <a class="secondary-action" href="{escape(secondary_href)}">{escape(secondary_label)}</a>
                </div>
                <div class="section-jump-row">{_render_link_row(list(item["subsections"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_improvement_plan(fixtures: DashboardFixtures) -> str:
    return "".join(
        f"""
        <li>
            <strong>{escape(title)}</strong>
            <span>{escape(description)}</span>
        </li>
        """
        for title, description in fixtures.improvement_plan_items
    )


def _render_journey_detail_panels(fixtures: DashboardFixtures) -> str:
    panels = []
    for panel in fixtures.journey_detail_panels:
        steps = "".join(
            f"""
            <li>
                <strong>{escape(title)}</strong>
                <span>{escape(description)}</span>
            </li>
            """
            for title, description in panel["steps"]
        )
        panels.append(
            f"""
            <article class="journey-detail-card" id="{escape(panel["anchor"])}">
                <div>
                    <div class="eyebrow" style="color: var(--accent);">{escape(panel["eyebrow"])}</div>
                    <h3>{escape(panel["title"])}</h3>
                    <p>{escape(panel["description"])}</p>
                </div>
                <ol>{steps}</ol>
                <div class="section-jump-row">{_render_link_row(list(panel["links"]))}</div>
            </article>
            """
        )
    return "\n".join(panels)


def _render_package_capability_matrix(fixtures: DashboardFixtures) -> str:
    cards = []
    for item in fixtures.package_capability_matrix:
        cards.append(
            f"""
            <article class="package-map-card">
                <h3>{escape(item["title"])}</h3>
                <p>{escape(item["description"])}</p>
                <div class="section-jump-row">{_render_link_row(list(item["links"]))}</div>
            </article>
            """
        )
    return "\n".join(cards)


def _render_dashboard_section_nav() -> str:
    return _render_link_row(
        [
            ("Start", "#dashboard-start-here"),
            ("Add evidence", "#chat-upload-dashboard"),
            ("Organize materials", "#workspace-dataset-parquet-dashboard"),
            ("Review proof", "/claim-support-review"),
            ("Build draft", "/document"),
            ("More tools", "#dashboard-subsection-index"),
            ("Saved complaint", "#dashboard-workspace-snapshot"),
            ("Review docket", "#docket-dataset-parquet-dashboard"),
            ("Find connections", "#workspace-knowledge-graph-tools"),
            ("Check duties", "#workspace-deontic-logic-tools"),
            ("Notes", "#dataset-document-annotation-dashboard"),
            ("Profile", "#profile-and-identity-dashboard"),
            ("Technical tools", "#dashboard-advanced-tools"),
        ]
    )


class _DashboardUndefined(ChainableUndefined):
    def __call__(self, *args: Any, **kwargs: Any) -> "_DashboardUndefined":
        return self

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def items(self):
        return ()

    def keys(self):
        return ()

    def values(self):
        return ()


class _DashboardMetrics:
    def __init__(self) -> None:
        self.total_websites_processed = 27
        self.success_rate = 96.4
        self.total_rag_queries = 43
        self.average_query_time = 1.28
        self._custom_metrics = {
            "pipeline_runs": [
                {
                    "type": "counter",
                    "value": 14,
                    "labels": {"surface": "complaint-generator"},
                    "timestamp": "2026-03-22T12:00:00+00:00",
                }
            ]
        }

    def items(self):
        return self._custom_metrics.items()

    def keys(self):
        return self._custom_metrics.keys()

    def values(self):
        return self._custom_metrics.values()


_IPFS_DASHBOARD_ENV = Environment(
    loader=FileSystemLoader(str(_IPFS_DATASETS_TEMPLATES_DIR)),
    autoescape=select_autoescape(("html", "xml")),
    undefined=_DashboardUndefined,
)


def _static_url_for(endpoint: str, filename: str = "", **_: Any) -> str:
    if endpoint != "static":
        return "#"
    normalized_filename = str(filename or "").lstrip("/")
    return f"/ipfs-datasets-static/{quote(normalized_filename)}"


_IPFS_DASHBOARD_ENV.globals["url_for"] = _static_url_for


def _build_ipfs_dashboard_context(entry: DashboardEntry) -> dict[str, Any]:
    return {
        "title": entry.title,
        "dashboard_title": entry.title,
        "refresh_interval": 60,
        "last_updated": "2026-03-22T12:00:00+00:00",
        "uptime": "2 days, 4 hours",
        "base_url": "/api/ipfs-datasets",
        "api_key": "",
        "user_type": "general",
        "default_start_date": "2026-01-01",
        "default_end_date": "2026-03-22",
        "node_info": {
            "hostname": "complaint-generator-local",
            "platform": "linux",
            "python_version": "3.11",
            "ipfs_datasets_version": "preview",
            "start_time": "2026-03-20T08:00:00+00:00",
        },
        "system_stats": {
            "cpu_percent": 18,
            "memory_used": "1.2 GB",
            "memory_total": "8.0 GB",
            "memory_percent": 15,
            "disk_used": "12 GB",
            "disk_total": "128 GB",
            "disk_percent": 9,
        },
        "metrics": _DashboardMetrics(),
        "logs": [
            {
                "timestamp": "2026-03-22T12:00:00+00:00",
                "level": "INFO",
                "name": "dashboard_ui",
                "message": "Compatibility dashboard preview mounted successfully.",
            }
        ],
        "nodes": [
            {
                "id": "local-node",
                "status": "online",
                "address": "127.0.0.1",
                "last_seen": "2026-03-22T12:00:00+00:00",
            }
        ],
        "operations": [
            {
                "operation_id": "preview-1",
                "operation_type": "dashboard-preview",
                "status": "success",
                "start_time": "2026-03-22T12:00:00+00:00",
                "duration_ms": 12.5,
            }
        ],
        "dashboard_config": {
            "mode": "compatibility-preview",
            "template": entry.template_name,
            "slug": entry.slug,
        },
        "monitoring_config": {
            "refresh_interval_seconds": 60,
            "alerts_enabled": False,
        },
        "stats": {
            "articles_processed": 12,
            "articles_today": 2,
            "entities_extracted": 48,
            "entity_types": 6,
            "active_workflows": 3,
            "completed_workflows": 9,
            "sources_analyzed": 5,
            "reliability_avg": 92,
            "documents_processed": 16,
            "documents_today": 3,
            "relationships_mapped": 21,
            "strong_relationships": 7,
        },
        "system_status": {
            "system_ready": True,
            "last_updated": "2026-03-22T12:00:00+00:00",
            "available_tools": ["create_dataset", "search_graph", "run_dashboard_query"],
            "theorem_count": 3,
            "domains": ["legal", "news", "software"],
            "jurisdictions": ["federal", "state"],
        },
        "processing_stats": {
            "total_sessions": 4,
            "active_sessions": 1,
            "success_rate": 100.0,
            "average_processing_time": 1.2,
        },
    }


def _render_ipfs_dashboard(entry: DashboardEntry) -> str:
    try:
        template = _IPFS_DASHBOARD_ENV.get_template(entry.template_name)
        return template.render(**_build_ipfs_dashboard_context(entry))
    except Exception as exc:
        return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{escape(entry.title)} | Dashboard Preview</title>
    <style>
        body {{ font-family: 'Public Sans', Arial, sans-serif; margin: 0; background: #f7f7f4; color: #122033; }}
        main {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; }}
        h1 {{ margin-top: 0; }}
        pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f3f5f7; padding: 16px; border-radius: 12px; }}
        a {{ color: #0a4f66; font-weight: 600; }}
    </style>
</head>
<body>
    <main>
        <section>
            <h1>{escape(entry.title)}</h1>
            <p>{escape(entry.summary)}</p>
            <p>The optional ipfs_datasets dashboard template <code>{escape(entry.template_name)}</code> is not installed in this checkout, so the complaint-generator dashboard hub is serving a stable fallback page.</p>
            <p><a href=\"/dashboards\">Back to dashboard hub</a></p>
            <pre>{escape(str(exc))}</pre>
        </section>
    </main>
</body>
</html>
"""


def _render_shell_page(
    entry: DashboardEntry,
    fixtures: DashboardFixtures | None = None,
) -> str:
    fixtures = _resolve_dashboard_fixtures(fixtures)
    shell_links = "".join(
        f'<a class="shell-link{' is-active' if item.slug == entry.slug else ''}" href="/dashboards/ipfs-datasets/{escape(item.slug)}">{escape(item.title)}</a>'
        for item in fixtures.ipfs_entries
    )
    top_links = "".join(
        f'<a class="surface-link" href="{escape(path)}">{escape(label)}</a>'
        for label, path in fixtures.complaint_links
    )
    iframe_src = f"/dashboards/raw/ipfs-datasets/{quote(entry.slug)}"
    raw_src = iframe_src
    return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>{escape(entry.title)} | Complaint Generator Dashboard Shell</title>
    <style>
        body {{ font-family: 'Public Sans', Arial, sans-serif; margin: 0; background: #f6f4ef; color: #122033; }}
        header {{ background: linear-gradient(135deg, #14324a, #204f6d); color: white; padding: 18px 24px; }}
        .surface-nav, .shell-nav {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .surface-nav {{ margin-top: 12px; }}
        .surface-link, .shell-link {{ text-decoration: none; border-radius: 999px; padding: 8px 14px; font-size: 14px; }}
        .surface-link {{ background: rgba(255,255,255,0.14); color: white; }}
        .shell-link {{ background: white; color: #14324a; border: 1px solid #c9d4df; }}
        .shell-link.is-active {{ background: #14324a; color: white; border-color: #14324a; }}
        main {{ display: grid; gap: 18px; padding: 20px 24px 28px; }}
        .shell-card {{ background: white; border-radius: 18px; padding: 18px; box-shadow: 0 12px 32px rgba(17, 34, 51, 0.08); }}
        .shell-card h1 {{ margin: 0 0 10px; font-size: 28px; }}
        .shell-card p {{ margin: 0; color: #425466; }}
        iframe {{ width: 100%; min-height: 1200px; border: 0; border-radius: 18px; background: white; box-shadow: 0 12px 32px rgba(17, 34, 51, 0.08); }}
        .raw-link {{ color: #14324a; font-weight: 600; }}
    </style>
</head>
<body>
    <header>
        <div><strong>Complaint Generator Unified Dashboards</strong></div>
        <div class=\"surface-nav\">{top_links}</div>
    </header>
    <main>
        <section class=\"shell-card\">
            <h1>{escape(entry.title)}</h1>
            <p>{escape(entry.summary)} This shell keeps the dashboard inside the complaint-generator site while sourcing the underlying HTML from ipfs_datasets_py.</p>
            <p style=\"margin-top: 10px;\"><a class=\"raw-link\" href=\"{escape(raw_src)}\" target=\"_blank\" rel=\"noopener\">Open raw dashboard</a></p>
        </section>
        <section class=\"shell-card\">
            <div class=\"shell-nav\">{shell_links}</div>
        </section>
        <iframe src=\"{escape(iframe_src)}\" title=\"{escape(entry.title)}\"></iframe>
    </main>
</body>
</html>
"""




def create_dashboard_ui_router(
    *,
    fixtures: DashboardFixtures | None = None,
) -> APIRouter:
    """Create dashboard routes bound to one explicit fixture catalog.

    The default catalog is resolved when the router is created. Tests and preview
    servers can inject a freshly built catalog without mutating live module state.
    """
    route_fixtures = _resolve_dashboard_fixtures(fixtures)
    router = APIRouter()

    @router.get("/mcp", response_class=HTMLResponse)
    async def legacy_mcp_dashboard_root() -> str:
        return _render_shell_page(
            get_default_ipfs_dashboard_entry(fixtures=route_fixtures),
            route_fixtures,
        )

    @router.get("/api/mcp/analytics/history")
    async def mcp_analytics_history() -> dict[str, Any]:
        return {
            "history": [
                {
                    "last_updated": "2026-03-22T09:00:00+00:00",
                    "success_rate": 91.2,
                    "average_query_time": 1.42,
                },
                {
                    "last_updated": "2026-03-22T10:00:00+00:00",
                    "success_rate": 94.8,
                    "average_query_time": 1.35,
                },
                {
                    "last_updated": "2026-03-22T11:00:00+00:00",
                    "success_rate": 96.4,
                    "average_query_time": 1.28,
                },
            ]
        }

    @router.get("/dashboards", response_class=HTMLResponse)
    async def dashboard_hub(
        user_id: str = "",
        manifest_path: str = "",
        docket_dataset_path: str = "",
        workspace_dataset_path: str = "",
    ) -> str:
        return _render_dashboard_hub(
            default_user_id=str(user_id or "").strip(),
            default_manifest_path=str(manifest_path or "").strip(),
            default_docket_dataset_path=str(docket_dataset_path or "").strip(),
            default_workspace_dataset_path=str(workspace_dataset_path or "").strip(),
            fixtures=route_fixtures,
        )

    @router.get("/dashboards/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_shell(slug: str) -> str:
        entry = get_ipfs_dashboard_entry(slug, fixtures=route_fixtures)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_shell_page(entry, route_fixtures)

    @router.get("/dashboards/raw/ipfs-datasets/{slug}", response_class=HTMLResponse)
    async def ipfs_datasets_dashboard_raw(slug: str) -> str:
        entry = get_ipfs_dashboard_entry(slug, fixtures=route_fixtures)
        if entry is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return _render_ipfs_dashboard(entry)

    return router


def attach_dashboard_ui_routes(
    app: FastAPI,
    *,
    fixtures: DashboardFixtures | None = None,
) -> FastAPI:
    if not any(
        getattr(route, "path", None) == "/ipfs-datasets-static" for route in app.routes
    ):
        app.mount(
            "/ipfs-datasets-static",
            StaticFiles(directory=str(_IPFS_DATASETS_STATIC_DIR), check_dir=False),
            name="ipfs-datasets-static",
        )
    return attach_router_routes(
        app,
        create_dashboard_ui_router(fixtures=fixtures),
    )

from .dashboard_hub import _render_dashboard_hub
