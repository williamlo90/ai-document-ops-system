from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app.agent.contracts import AgentToolName
from app.agent.service import CopilotRequest, CopilotResult
from app.api.dependencies import AppContainer, get_container
from app.backoffice.models import (
    ActionStep,
    ActionStepStatus,
    ApprovalStatus,
    WorkItem,
    WorkType,
)
from app.backoffice.evidence import planning_input_from_evidence
from app.backoffice.services import BackofficeWorkflowError
from app.benchmark.datasets import (
    DatasetValidationError,
    load_evaluation_dataset,
    records_from_dataset,
)
from app.benchmark.guardrails import BenchmarkRunBlocked, safety_info, validate_benchmark_run
from app.benchmark.providers import available_provider_pairs, build_provider_pair
from app.benchmark.report import (
    generate_comparison_json_report,
    generate_comparison_json_report_from_provider_summaries,
)
from app.benchmark.service import run_dataset
from app.core.http_headers import NO_STORE_HEADERS
from app.core.security import SecurityContext, UnauthorizedError, verify_admin_token
from app.core.settings import is_production_like
from app.documents.repositories import NotFoundError
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.extraction.schemas import InvoiceData
from app.providers.storage import StorageError


SESSION_COOKIE = "doc_intel_admin_token"
router = APIRouter(tags=["ui"])


@router.get("/ui", response_class=HTMLResponse)
def dashboard(
    request: Request,
    document_id: UUID | None = None,
    message: str = "",
    error: str = "",
    container: AppContainer = Depends(get_container),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> HTMLResponse:
    context = _context_or_none(token, container)
    if context is None:
        return HTMLResponse(_login_page(error or ""))
    return HTMLResponse(_dashboard_page(container, context, document_id, message, error))


@router.get("/ui/benchmarks", response_class=HTMLResponse)
def benchmark_dashboard(
    request: Request,
    dataset: str = "",
    provider: str = "mock",
    run: bool = False,
    container: AppContainer = Depends(get_container),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> HTMLResponse:
    context = _context_or_none(token, container)
    if context is None:
        return HTMLResponse(_login_page(""))
    return HTMLResponse(_benchmark_page(container, dataset, provider, run))


@router.get("/ui/agentops", response_class=HTMLResponse)
def agentops_dashboard(
    request: Request,
    run_id: UUID | None = None,
    container: AppContainer = Depends(get_container),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> HTMLResponse:
    context = _context_or_none(token, container)
    if context is None:
        return HTMLResponse(_login_page(""))
    return HTMLResponse(_agentops_page(container, context, run_id))


@router.get("/ui/backoffice", response_class=HTMLResponse)
def backoffice_dashboard(
    request: Request,
    work_item_id: UUID | None = None,
    message: str = "",
    error: str = "",
    container: AppContainer = Depends(get_container),
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> HTMLResponse:
    context = _context_or_none(token, container)
    if context is None:
        return HTMLResponse(_login_page(error or ""))
    return HTMLResponse(_backoffice_page(container, context, work_item_id, message, error))


@router.post("/ui/login")
def login(
    admin_token: str = Form(...),
    container: AppContainer = Depends(get_container),
) -> RedirectResponse:
    try:
        context = verify_admin_token(admin_token, container.settings.admin_token)
    except UnauthorizedError:
        return _redirect("/ui?error=Invalid%20admin%20token")
    response = _redirect("/ui?message=Signed%20in")
    response.set_cookie(
        SESSION_COOKIE,
        container_session(container, context),
        httponly=True,
        secure=is_production_like(container.settings),
        samesite="strict",
        max_age=container.settings.session_ttl_seconds,
        path="/",
    )
    return response


@router.post("/ui/logout")
def logout(
    request: Request,
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> RedirectResponse:
    request.app.state.sessions.revoke(token)
    response = _redirect("/ui")
    response.delete_cookie(SESSION_COOKIE)
    return response


def _require_ui_context(
    request: Request,
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> SecurityContext:
    context = _context_or_none(token, get_container(request))
    if context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return context


def _context_or_none(token: str | None, container: AppContainer) -> SecurityContext | None:
    sessions = getattr(container, "_app_sessions", None)
    return sessions.get(token) if sessions is not None else None


def container_session(container: AppContainer, context: SecurityContext) -> str:
    return container._app_sessions.create(context)


@router.post("/ui/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        file.file.seek(0)
        chunks = iter(lambda: file.file.read(1024 * 1024), b"")
        result = container.upload_service.upload_pdf(
            original_filename=file.filename or "upload.pdf",
            content_type=file.content_type or "",
            chunks=chunks,
            context=context,
        )
    except StorageError as exc:
        return _redirect(f"/ui?error={_url(str(exc))}")
    return _redirect(f"/ui?document_id={result.document.id}&message=Uploaded")


@router.post("/ui/documents/{document_id}/process")
def process_document(
    document_id: UUID,
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        document = container.processing_service.process_document(document_id, context)
    except NotFoundError:
        return _redirect("/ui?error=Document%20not%20found")
    except InvalidStatusTransition as exc:
        return _redirect(f"/ui?document_id={document_id}&error={_url(str(exc))}")
    return _redirect(f"/ui?document_id={document.id}&message=Processed")


@router.get("/ui/documents/{document_id}/preview")
def preview_document(
    document_id: UUID,
    container: AppContainer = Depends(get_container),
    _context: SecurityContext = Depends(_require_ui_context),
) -> FileResponse:
    try:
        document = container.documents.get(document_id)
        path = container.storage.open_for_parser(document.storage_key)
    except (NotFoundError, StorageError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.original_filename,
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": f'inline; filename="{_safe_header_filename(document.original_filename)}"',
        },
    )


@router.post("/ui/review/{document_id}/save")
def save_review(
    document_id: UUID,
    notes: str = Form(""),
    vendor_name: str = Form(""),
    invoice_number: str = Form(""),
    invoice_date: str = Form(""),
    due_date: str = Form(""),
    subtotal: str = Form(""),
    tax: str = Form(""),
    total: str = Form(""),
    currency: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        corrected = _invoice_data(
            vendor_name,
            invoice_number,
            invoice_date,
            due_date,
            subtotal,
            tax,
            total,
            currency,
        )
        container.review_service.save_review(document_id, notes, context, corrected)
    except (InvalidOperation, ValueError) as exc:
        return _redirect(f"/ui?document_id={document_id}&error={_url(str(exc))}")
    except NotFoundError:
        return _redirect("/ui?error=Document%20not%20found")
    except InvalidStatusTransition as exc:
        return _redirect(f"/ui?document_id={document_id}&error={_url(str(exc))}")
    return _redirect(f"/ui?document_id={document_id}&message=Review%20saved")


@router.post("/ui/review/{document_id}/approve")
def approve_review(
    document_id: UUID,
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        container.review_service.approve(document_id, context)
    except NotFoundError:
        return _redirect("/ui?error=Document%20not%20found")
    except InvalidStatusTransition as exc:
        return _redirect(f"/ui?document_id={document_id}&error={_url(str(exc))}")
    return _redirect(f"/ui?document_id={document_id}&message=Approved")


@router.post("/ui/review/{document_id}/reject")
def reject_review(
    document_id: UUID,
    notes: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        container.review_service.reject(document_id, notes, context)
    except NotFoundError:
        return _redirect("/ui?error=Document%20not%20found")
    except InvalidStatusTransition as exc:
        return _redirect(f"/ui?document_id={document_id}&error={_url(str(exc))}")
    return _redirect(f"/ui?document_id={document_id}&message=Rejected")


@router.get("/ui/export")
def export_csv(
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> Response:
    csv_text = container.export_service.export_approved_csv(context)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": 'attachment; filename="invoices.csv"',
        },
    )


@router.post("/ui/copilot", response_class=HTMLResponse)
def ui_copilot(
    action: str = Form(...),
    document_id: UUID | None = Form(default=None),
    execute_tool: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> HTMLResponse:
    request = _copilot_request(action, document_id, execute_tool)
    result = container.copilot_service.answer(request, context)
    return HTMLResponse(_dashboard_page(container, context, document_id, "", "", result))


@router.post("/ui/backoffice/work-items")
def ui_backoffice_create_work_item(
    title: str = Form(...),
    work_type: str = Form(""),
    document_id: UUID | None = Form(default=None),
    requested_outcome: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    parsed_work_type = WorkType(work_type) if work_type else None
    business_context = {"requested_outcome": requested_outcome} if requested_outcome.strip() else {}
    work_item = container.backoffice_service.create_work_item(
        title=title,
        context=context,
        work_type=parsed_work_type,
        linked_document_ids=(document_id,) if document_id else (),
        business_context=business_context,
    )
    return _redirect(f"/ui/backoffice?work_item_id={work_item.id}&message=Work%20item%20created")


@router.post("/ui/backoffice/work-items/{work_item_id}/plan")
def ui_backoffice_plan_work_item(
    work_item_id: UUID,
    requested_outcome: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        work_item = container.backoffice_work_items.get(work_item_id)
        if work_item.workspace_id != context.workspace_id:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        result = container.backoffice_service.plan_work_item(
            work_item_id=work_item_id,
            context=context,
            planning_input=planning_input_from_evidence(
                work_item=work_item,
                requested_outcome=requested_outcome or None,
                documents=container.documents,
                extractions=container.extractions,
            ),
        )
    except (NotFoundError, BackofficeWorkflowError, ValueError) as exc:
        return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&error={_url(str(exc))}")
    return _redirect(f"/ui/backoffice?work_item_id={result.work_item.id}&message=Plan%20created")


@router.post("/ui/backoffice/approvals/{approval_id}/approve")
def ui_backoffice_approve(
    approval_id: UUID,
    work_item_id: UUID = Form(...),
    notes: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        container.backoffice_service.approve_request(
            approval_id=approval_id,
            context=context,
            notes=notes or None,
        )
    except NotFoundError:
        return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&error=Approval%20not%20found")
    return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&message=Approval%20approved")


@router.post("/ui/backoffice/approvals/{approval_id}/reject")
def ui_backoffice_reject(
    approval_id: UUID,
    work_item_id: UUID = Form(...),
    notes: str = Form(""),
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    try:
        container.backoffice_service.reject_request(
            approval_id=approval_id,
            context=context,
            notes=notes or None,
        )
    except NotFoundError:
        return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&error=Approval%20not%20found")
    return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&message=Approval%20rejected")


@router.post("/ui/backoffice/work-items/{work_item_id}/steps/{action_step_id}/execute")
def ui_backoffice_execute_step(
    work_item_id: UUID,
    action_step_id: UUID,
    container: AppContainer = Depends(get_container),
    context: SecurityContext = Depends(_require_ui_context),
) -> RedirectResponse:
    response = container.backoffice_service.execute_approved_step(
        work_item_id=work_item_id,
        action_step_id=action_step_id,
        context=context,
    )
    if response.status == "success":
        return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&message=Executed")
    return _redirect(f"/ui/backoffice?work_item_id={work_item_id}&error={_url(response.summary)}")


def _copilot_request(
    action: str,
    document_id: UUID | None,
    execute_tool: str,
) -> CopilotRequest:
    if action == "summarize":
        return CopilotRequest(message="Summarize workflow metrics and cost")
    if action == "explain":
        return CopilotRequest(message="Explain this invoice", document_id=document_id)
    if action == "recommend":
        return CopilotRequest(
            message="What should I do next with this invoice?",
            document_id=document_id,
        )
    if action == "execute" and execute_tool:
        return CopilotRequest(
            message=f"Execute {execute_tool}",
            document_id=document_id,
            execute_tool=AgentToolName(execute_tool),
            confirmed=True,
        )
    return CopilotRequest(message="Summarize workflow metrics and cost")


def _dashboard_page(
    container: AppContainer,
    context: SecurityContext,
    selected_document_id: UUID | None,
    message: str,
    error: str,
    copilot_result: CopilotResult | None = None,
) -> str:
    documents = sorted(
        container.documents.list_all(), key=lambda item: item.created_at, reverse=True
    )
    selected = _selected_document(container, documents, selected_document_id)
    metrics = container.metrics_service.summary(context)
    review_queue = container.review_service.list_queue(context)
    return _layout(
        "Doc Intel",
        f"""
        <header class="topbar">
          <div>
            <p class="eyebrow">Document Intelligence MVP</p>
            <h1>Invoice processing console</h1>
          </div>
          <div class="top-actions">
            <a class="button ghost" href="/ui/backoffice">Backoffice</a>
            <a class="button ghost" href="/ui/agentops">AgentOps</a>
            <a class="button ghost" href="/ui/benchmarks">Benchmarks</a>
            <form method="post" action="/ui/logout">
              <button class="button ghost" type="submit">Sign out</button>
            </form>
          </div>
        </header>
        {_notice(message, "success")}
        {_notice(error, "error")}
        <section class="metrics">
          {_metric("Documents", metrics["documents_total"])}
          {_metric("Jobs", metrics["jobs_total"])}
          {_metric("Audit events", metrics["audit_events_total"])}
          {_metric("Needs review", metrics["by_status"].get("needs_review", 0))}
        </section>
        <main class="workspace">
          <section class="panel sidebar">
            <h2>Upload</h2>
            <form class="stack" method="post" action="/ui/documents/upload" enctype="multipart/form-data">
              <input type="file" name="file" accept="application/pdf" required>
              <button class="button primary" type="submit">Upload PDF</button>
            </form>
            <div class="section-head">
              <h2>Documents</h2>
              <a class="button small" href="/ui/export">Export CSV</a>
            </div>
            <div class="document-list">
              {_document_list(documents, selected)}
            </div>
            <h2>Review queue</h2>
            <div class="document-list compact">
              {_review_queue(review_queue)}
            </div>
            {_copilot_panel(selected, copilot_result)}
          </section>
          <section class="panel detail">
            {_document_detail(container, selected)}
          </section>
        </main>
        """,
    )


def _backoffice_page(
    container: AppContainer,
    context: SecurityContext,
    selected_work_item_id: UUID | None,
    message: str,
    error: str,
) -> str:
    work_items = sorted(
        container.backoffice_work_items.list_by_workspace(context.workspace_id),
        key=lambda item: item.created_at,
        reverse=True,
    )
    selected = _selected_work_item(container, work_items, selected_work_item_id)
    pending = container.backoffice_approvals.list_pending(context.workspace_id)
    return _layout(
        "Backoffice",
        f"""
        <header class="topbar">
          <div>
            <p class="eyebrow">Autonomous Backoffice AI</p>
            <h1>Operator inbox</h1>
          </div>
          <div class="top-actions">
            <a class="button ghost" href="/ui">Console</a>
            <a class="button ghost" href="/ui/agentops">AgentOps</a>
            <form method="post" action="/ui/logout">
              <button class="button ghost" type="submit">Sign out</button>
            </form>
          </div>
        </header>
        {_notice(message, "success")}
        {_notice(error, "error")}
        <section class="metrics">
          {_metric("Work items", len(work_items))}
          {_metric("Pending approvals", len(pending))}
          {_metric("Drafts", _backoffice_draft_count(container, context.workspace_id))}
          {_metric("Policy decisions", _backoffice_decision_count(container, context.workspace_id))}
        </section>
        <main class="backoffice-shell">
          <section class="panel backoffice-sidebar">
            <h2>Create work item</h2>
            {_backoffice_create_form(container, context)}
            <div class="section-head">
              <h2>Work items</h2>
              <span class="status read_only">{len(work_items)}</span>
            </div>
            <div class="document-list">
              {_backoffice_work_item_list(work_items, selected)}
            </div>
            <h2>Pending approvals</h2>
            <div class="document-list compact">
              {_backoffice_pending_list(pending)}
            </div>
          </section>
          <section class="panel backoffice-detail">
            {_backoffice_detail(container, context, selected)}
          </section>
        </main>
        """,
    )


def _selected_work_item(
    container: AppContainer,
    work_items: list[WorkItem],
    work_item_id: UUID | None,
):
    if work_item_id is not None:
        try:
            work_item = container.backoffice_work_items.get(work_item_id)
        except NotFoundError:
            return None
        return work_item if work_item in work_items else None
    return work_items[0] if work_items else None


def _backoffice_create_form(container: AppContainer, context: SecurityContext) -> str:
    documents = sorted(
        container.documents.list_by_workspace(context.workspace_id),
        key=lambda item: item.created_at,
        reverse=True,
    )
    return f"""
    <form class="stack" method="post" action="/ui/backoffice/work-items">
      <label>Title
        <input name="title" value="Review invoice follow-up" required>
      </label>
      <label>Work type
        <select name="work_type">
          <option value="">Auto classify</option>
          {_work_type_options()}
        </select>
      </label>
      <label>Linked document
        <select name="document_id">
          <option value="">No document</option>
          {_document_options(documents)}
        </select>
      </label>
      <label>Requested outcome
        <input name="requested_outcome" placeholder="export invoice, draft vendor follow-up">
      </label>
      <button class="button primary" type="submit">Create</button>
    </form>
    """


def _backoffice_detail(
    container: AppContainer,
    context: SecurityContext,
    work_item: WorkItem | None,
) -> str:
    if work_item is None:
        return """
        <div class="empty-state">
          <h2>No work item selected</h2>
          <p>Create a work item to plan back-office actions.</p>
        </div>
        """
    plans = container.backoffice_plans.list_for_work_item(context.workspace_id, work_item.id)
    plan = (
        container.backoffice_plans.get(work_item.current_plan_id)
        if work_item.current_plan_id
        else None
    )
    drafts = container.backoffice_drafts.list_for_work_item(context.workspace_id, work_item.id)
    approvals = container.backoffice_approvals.list_for_work_item(
        context.workspace_id, work_item.id
    )
    decisions = container.backoffice_policy_decisions.list_for_work_item(
        context.workspace_id, work_item.id
    )
    return f"""
    <div class="detail-head">
      <div>
        <p class="eyebrow">Selected work item</p>
        <h2>{_h(work_item.title)}</h2>
      </div>
      <span class="status {_h(work_item.status.value)}">{_h(work_item.status.value)}</span>
    </div>
    <section class="backoffice-summary">
      <dl>
        <dt>Work type</dt><dd>{_h(work_item.work_type.value if work_item.work_type else "unclassified")}</dd>
        <dt>Priority</dt><dd>{_h(work_item.priority.value)}</dd>
        <dt>Linked documents</dt><dd>{len(work_item.linked_document_ids)}</dd>
        <dt>Plans</dt><dd>{len(plans)}</dd>
      </dl>
    </section>
    {_backoffice_plan_form(work_item)}
    <div class="backoffice-grid">
      <section>
        <h3>Task plan</h3>
        {_backoffice_plan_view(work_item, plan, approvals)}
      </section>
      <section>
        <h3>Drafts</h3>
        {_backoffice_drafts_view(drafts)}
      </section>
      <section>
        <h3>Approvals</h3>
        {_backoffice_approvals_view(approvals, work_item)}
      </section>
    </div>
    <section>
      <h3>Policy decisions</h3>
      {_backoffice_decisions_view(decisions)}
    </section>
    """


def _backoffice_plan_form(work_item: WorkItem) -> str:
    return f"""
    <section class="plan-control">
      <h3>Plan next actions</h3>
      <form class="review-grid" method="post" action="/ui/backoffice/work-items/{work_item.id}/plan">
        <label>Requested outcome
          <input name="requested_outcome" value="{_h(work_item.business_context.get("requested_outcome", ""))}" placeholder="export invoice, draft note">
        </label>
        <p>Evidence, validation issues, and export approval are derived from the linked document.</p>
        <button class="button primary" type="submit">Create plan</button>
      </form>
    </section>
    """


def _backoffice_plan_view(work_item: WorkItem, plan, approvals) -> str:
    if plan is None:
        return '<p class="empty">No task plan yet.</p>'
    rows = []
    for step in plan.steps:
        approval = _approval_for_step(approvals, step.id)
        rows.append(
            f"""
            <div class="step-row">
              <div>
                <strong>{_h(step.action_type.value)}</strong>
                <p>{_h(step.why_this)}</p>
                <small>{_h(step.why_not)}</small>
              </div>
              <div class="step-actions">
                <span class="status {_h(step.status.value)}">{_h(step.status.value)}</span>
                <span class="status {_h(step.risk_level.value)}">{_h(step.risk_level.value)}</span>
                {_backoffice_execute_button(work_item, step, approval)}
              </div>
            </div>
            """
        )
    return f"""
    <div class="plan-meta">
      <span class="status read_only">{_h(plan.planner_version)}</span>
      <span class="status {_h(plan.overall_confidence)}">confidence: {_h(plan.overall_confidence)}</span>
    </div>
    {_notice(plan.escalation_reason or "", "error")}
    <div class="step-list">{''.join(rows)}</div>
    """


def _backoffice_execute_button(work_item: WorkItem, step: ActionStep, approval) -> str:
    if step.status in {ActionStepStatus.EXECUTED, ActionStepStatus.BLOCKED}:
        return ""
    if step.requires_approval and (approval is None or approval.status != ApprovalStatus.APPROVED):
        return ""
    if step.action_type.value not in {"process_document", "export_approved_invoice"}:
        return ""
    return f"""
    <form method="post" action="/ui/backoffice/work-items/{work_item.id}/steps/{step.id}/execute">
      <button class="button small primary" type="submit">Execute</button>
    </form>
    """


def _backoffice_drafts_view(drafts) -> str:
    if not drafts:
        return '<p class="empty">No drafts yet.</p>'
    return "".join(
        f"""
        <article class="copilot-card">
          <small>{_h(draft.draft_type.value)} - {_h(draft.status.value)}</small>
          <strong>{_h(draft.preview_content)}</strong>
        </article>
        """
        for draft in drafts
    )


def _backoffice_approvals_view(approvals, work_item: WorkItem) -> str:
    if not approvals:
        return '<p class="empty">No approval requests.</p>'
    return "".join(_backoffice_approval_card(approval, work_item) for approval in approvals)


def _backoffice_approval_card(approval, work_item: WorkItem) -> str:
    controls = ""
    if approval.status == ApprovalStatus.PENDING:
        controls = f"""
        <div class="approval-actions">
          <form method="post" action="/ui/backoffice/approvals/{approval.id}/approve">
            <input type="hidden" name="work_item_id" value="{work_item.id}">
            <input type="hidden" name="notes" value="Approved from operator inbox">
            <button class="button small primary" type="submit">Approve</button>
          </form>
          <form method="post" action="/ui/backoffice/approvals/{approval.id}/reject">
            <input type="hidden" name="work_item_id" value="{work_item.id}">
            <input type="hidden" name="notes" value="Rejected from operator inbox">
            <button class="button small danger" type="submit">Reject</button>
          </form>
        </div>
        """
    return f"""
    <article class="copilot-card">
      <small>{_h(approval.status.value)} - requested by {_h(approval.requested_by)}</small>
      <strong>Action approval</strong>
      <p>{_h(approval.reviewer_notes or "Awaiting human decision.")}</p>
      {controls}
    </article>
    """


def _backoffice_decisions_view(decisions) -> str:
    if not decisions:
        return '<p class="empty">No policy decisions yet.</p>'
    rows = "".join(
        f"""
        <tr>
          <td>{_h(decision.action_type.value)}</td>
          <td>{_h(decision.autonomy_level.value)}</td>
          <td>{_h("yes" if decision.allowed else "no")}</td>
          <td>{_h(decision.reason)}</td>
        </tr>
        """
        for decision in decisions
    )
    return f"""
    <div class="table-scroll">
      <table class="benchmark-table">
        <thead><tr><th>Action</th><th>Autonomy</th><th>Allowed</th><th>Reason</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """


def _backoffice_work_item_list(work_items: list[WorkItem], selected: WorkItem | None) -> str:
    if not work_items:
        return '<p class="empty">No work items yet.</p>'
    selected_id = selected.id if selected else None
    return "".join(
        f"""
        <a class="doc-row {'active' if item.id == selected_id else ''}" href="/ui/backoffice?work_item_id={item.id}">
          <span>{_h(item.title)}</span>
          <small>{_h(item.status.value)}</small>
        </a>
        """
        for item in work_items
    )


def _backoffice_pending_list(approvals) -> str:
    if not approvals:
        return '<p class="empty">No pending approvals.</p>'
    return "".join(
        f"""
        <a class="doc-row" href="/ui/backoffice?work_item_id={approval.work_item_id}">
          <span>Approval request</span>
          <small>{_h(approval.status.value)}</small>
        </a>
        """
        for approval in approvals
    )


def _work_type_options() -> str:
    return "".join(
        f'<option value="{_h(work_type.value)}">{_h(work_type.value)}</option>'
        for work_type in WorkType
    )


def _document_options(documents) -> str:
    return "".join(
        f'<option value="{document.id}">{_h(document.original_filename)} - {_h(document.status.value)}</option>'
        for document in documents
    )


def _approval_for_step(approvals, step_id: UUID):
    for approval in approvals:
        if approval.action_step_id == step_id:
            return approval
    return None


def _backoffice_draft_count(container: AppContainer, workspace_id: str) -> int:
    return sum(
        len(container.backoffice_drafts.list_for_work_item(workspace_id, item.id))
        for item in container.backoffice_work_items.list_by_workspace(workspace_id)
    )


def _backoffice_decision_count(container: AppContainer, workspace_id: str) -> int:
    return sum(
        len(container.backoffice_policy_decisions.list_for_work_item(workspace_id, item.id))
        for item in container.backoffice_work_items.list_by_workspace(workspace_id)
    )


def _benchmark_page(
    container: AppContainer,
    dataset_name: str,
    provider_key: str,
    should_run: bool,
) -> str:
    datasets = _benchmark_datasets()
    providers = available_provider_pairs(container.settings)
    provider_keys = {item.key for item in providers}
    selected_name = dataset_name if dataset_name in datasets else (next(iter(datasets), ""))
    selected_provider = provider_key if provider_key in provider_keys else "mock"
    report = None
    run_error = ""
    if should_run and selected_name:
        try:
            report = _run_benchmark(container, datasets[selected_name], selected_provider)
        except (BenchmarkRunBlocked, DatasetValidationError, FileNotFoundError, ValueError) as exc:
            run_error = str(exc)
    return _layout(
        "Benchmarks",
        f"""
        <header class="topbar">
          <div>
            <p class="eyebrow">Provider Benchmark</p>
            <h1>Document AI evaluation lab</h1>
          </div>
          <div class="top-actions">
            <a class="button ghost" href="/ui">Console</a>
            <form method="post" action="/ui/logout">
              <button class="button ghost" type="submit">Sign out</button>
            </form>
          </div>
        </header>
        {_notice(run_error, "error")}
        <main class="benchmark-shell">
          <section class="panel benchmark-control">
            <h2>Run benchmark</h2>
            <form class="benchmark-form" method="get" action="/ui/benchmarks">
              <label>Dataset
                <select name="dataset">
                  {_dataset_options(datasets, selected_name)}
                </select>
              </label>
              <label>Provider
                <select name="provider">
                  {_provider_options(providers, selected_provider)}
                </select>
              </label>
              {_provider_safety_notice(providers, selected_provider, container)}
              <input type="hidden" name="run" value="true">
              <button class="button primary" type="submit" {"disabled" if not datasets else ""}>Run benchmark</button>
            </form>
            {_benchmark_history(container)}
          </section>
          {_benchmark_result(report, datasets)}
        </main>
        """,
    )


def _agentops_page(
    container: AppContainer,
    context: SecurityContext,
    selected_run_id: UUID | None,
) -> str:
    runs = container.agent_runs.list_recent(context.workspace_id, limit=50)
    summary = container.agentops_service.summarize(runs)
    selected_run = _selected_run(container, runs, selected_run_id)
    previous_runs = runs[5:10]
    current_runs = runs[:5]
    regression = container.agentops_service.compare_regression(
        container.agentops_service.summarize(previous_runs),
        container.agentops_service.summarize(current_runs),
    )
    return _layout(
        "AgentOps",
        f"""
        <header class="topbar">
          <div>
            <p class="eyebrow">AgentOps Reliability</p>
            <h1>Copilot evaluation dashboard</h1>
          </div>
          <div class="top-actions">
            <a class="button ghost" href="/ui">Console</a>
            <a class="button ghost" href="/ui/backoffice">Backoffice</a>
            <a class="button ghost" href="/ui/benchmarks">Benchmarks</a>
            <form method="post" action="/ui/logout">
              <button class="button ghost" type="submit">Sign out</button>
            </form>
          </div>
        </header>
        <section class="metrics agentops-metrics">
          {_metric("Tool accuracy", _pct_or_na(summary.tool_selection_accuracy))}
          {_metric("Completion", _pct_or_na(summary.successful_completion_rate))}
          {_metric("Escalation", _pct_or_na(summary.escalation_rate))}
          {_metric("Cost / run", _money_value(summary.estimated_cost_per_run))}
          {_metric("Unsafe prevention", _pct_or_na(summary.unsafe_action_prevention_rate))}
          {_metric("Avg confidence", _number_or_na(summary.average_confidence))}
          {_metric("Avg tool calls", _number_or_na(summary.average_tool_calls_per_task))}
          {_metric("Runs evaluated", summary.evaluated_runs)}
        </section>
        <main class="agentops-shell">
          <section class="panel agentops-main">
            <div class="section-head">
              <div>
                <p class="eyebrow">Recent runs</p>
                <h2>Run timeline</h2>
              </div>
              <span class="status read_only">{_h(summary.total_runs)} runs</span>
            </div>
            {_agentops_runs_table(container, runs, selected_run)}
            <div class="agentops-grid">
              {_agentops_failure_panel(summary)}
              {_agentops_prompt_panel(summary)}
              {_agentops_regression_panel(regression)}
            </div>
          </section>
          <section class="panel agentops-detail">
            {_agentops_run_detail(container, selected_run)}
          </section>
        </main>
        """,
    )


def _selected_run(container: AppContainer, runs, run_id: UUID | None):
    if run_id is not None:
        try:
            run = container.agent_runs.get(run_id)
        except NotFoundError:
            return None
        return run if run in runs else None
    return runs[0] if runs else None


def _agentops_runs_table(container: AppContainer, runs, selected_run) -> str:
    if not runs:
        return '<p class="empty">No copilot runs yet. Use Ask Copilot from the console to create traces.</p>'
    selected_id = selected_run.id if selected_run else None
    rows = []
    for run in runs[:20]:
        evaluation = container.agentops_service.evaluate_run(run)
        active = " active" if run.id == selected_id else ""
        correctness = _tool_correctness(evaluation.tool_selection_correct)
        rows.append(
            f"""
            <tr class="{active}">
              <td><a href="/ui/agentops?run_id={run.id}">{_h(run.intent)}</a></td>
              <td>{_h(evaluation.expected_tool.value if evaluation.expected_tool else "unevaluated")}</td>
              <td>{_h(evaluation.selected_tool.value if evaluation.selected_tool else "-")}</td>
              <td>{correctness}</td>
              <td>{_h(evaluation.confidence.value)}</td>
              <td>{_h(evaluation.failure_type.value if evaluation.failure_type else "-")}</td>
            </tr>
            """
        )
    return f"""
    <div class="table-scroll">
      <table class="benchmark-table">
        <thead>
          <tr>
            <th>Intent</th>
            <th>Expected tool</th>
            <th>Selected tool</th>
            <th>Correct</th>
            <th>Confidence</th>
            <th>Failure</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def _agentops_failure_panel(summary) -> str:
    counts = summary.failure_trend or []
    if not counts:
        content = '<p class="empty">No failures in recent runs.</p>'
    else:
        content = "".join(
            f"""
            <div class="history-row">
              <span>{_h(item.failure_type.value)}</span>
              <small>{_h(item.count)} recent occurrence(s)</small>
            </div>
            """
            for item in counts
        )
    return f"""
    <div class="provider-card">
      <h4>Failure trend</h4>
      <div class="history-list">{content}</div>
    </div>
    """


def _agentops_prompt_panel(summary) -> str:
    if not summary.prompt_versions:
        return """
        <div class="provider-card">
          <h4>Prompt comparison</h4>
          <p class="empty">No prompt version data.</p>
        </div>
        """
    rows = "".join(
        f"""
        <tr>
          <td>{_h(item.prompt_version)}</td>
          <td>{_pct_or_na(item.tool_selection_accuracy)}</td>
          <td>{_pct_or_na(item.escalation_rate)}</td>
          <td>{_number_or_na(item.average_confidence)}</td>
          <td>{_money_value(item.estimated_cost_per_run)}</td>
        </tr>
        """
        for item in summary.prompt_versions
    )
    return f"""
    <div class="provider-card">
      <h4>Prompt comparison</h4>
      <div class="table-scroll compact-table">
        <table>
          <thead><tr><th>Version</th><th>Tool acc.</th><th>Esc.</th><th>Conf.</th><th>Cost</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def _agentops_regression_panel(regression) -> str:
    deltas = regression.deltas
    rows = "".join(
        f"""
        <tr>
          <td>{_h(delta.metric)}</td>
          <td>{_number_or_na(delta.previous)}</td>
          <td>{_number_or_na(delta.current)}</td>
          <td>{_number_or_na(delta.delta)}</td>
          <td>{_h("yes" if delta.regressed else "no")}</td>
        </tr>
        """
        for delta in deltas
    )
    return f"""
    <div class="provider-card">
      <h4>Regression window</h4>
      <p class="compact-note">Compares latest 5 runs against the previous 5 runs.</p>
      <div class="table-scroll compact-table">
        <table>
          <thead><tr><th>Metric</th><th>Prev.</th><th>Curr.</th><th>Delta</th><th>Reg.</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def _agentops_run_detail(container: AppContainer, run) -> str:
    if run is None:
        return """
        <div class="empty-state">
          <h2>No run selected</h2>
          <p>Create a copilot run from the console to inspect the trace.</p>
        </div>
        """
    evaluation = container.agentops_service.evaluate_run(run)
    tool_calls = "".join(
        f"""
        <li>
          <span>{_h(trace.tool_name.value)} · {_h(trace.status)} · {_h(trace.risk.value)}</span>
          <small>{_h(trace.summary)}</small>
        </li>
        """
        for trace in run.tool_calls
    )
    if not tool_calls:
        tool_calls = "<li><span>No tool calls</span><small>Trace is empty.</small></li>"
    return f"""
    <div class="detail-head">
      <div>
        <p class="eyebrow">Selected run</p>
        <h2>{_h(run.intent)}</h2>
      </div>
      <span class="status {_h(evaluation.confidence.value)}">{_h(evaluation.confidence.value)}</span>
    </div>
    <table>
      <tr><th>Prompt version</th><td>{_h(run.prompt_version)}</td></tr>
      <tr><th>Expected tool</th><td>{_h(evaluation.expected_tool.value if evaluation.expected_tool else "unevaluated")}</td></tr>
      <tr><th>Selected tool</th><td>{_h(evaluation.selected_tool.value if evaluation.selected_tool else "-")}</td></tr>
      <tr><th>Correct</th><td>{_tool_correctness(evaluation.tool_selection_correct)}</td></tr>
      <tr><th>Failure</th><td>{_h(evaluation.failure_type.value if evaluation.failure_type else "-")}</td></tr>
      <tr><th>Human escalation</th><td>{_h("yes" if evaluation.human_escalated else "no")}</td></tr>
      <tr><th>Decision reason</th><td>{_h(evaluation.decision_reason)}</td></tr>
    </table>
    <section>
      <h3>Run timeline</h3>
      <ol class="audit">{tool_calls}</ol>
    </section>
    """


def _benchmark_datasets() -> dict[str, Path]:
    root = _project_root() / "examples" / "benchmark" / "datasets"
    if not root.is_dir():
        return {}
    return {
        item.name: item
        for item in sorted(root.iterdir())
        if item.is_dir() and (item / "expected.json").is_file()
    }


def _run_benchmark(container: AppContainer, dataset_path: Path, provider_key: str) -> dict:
    dataset = load_evaluation_dataset(dataset_path)
    expected_records = records_from_dataset(dataset)
    provider_pair, parser, extractor = build_provider_pair(provider_key, container.settings)
    validate_benchmark_run(dataset, provider_pair, container.settings)
    run = run_dataset(
        dataset,
        parser,
        extractor,
        rate_limit_s=0,
    )
    report = generate_comparison_json_report([run], expected_records)
    container.benchmark_history.save(
        dataset_name=dataset.name,
        provider_name=provider_pair.key,
        report=report,
    )
    return _comparison_report_from_history(container, dataset.name, report)


def _comparison_report_from_history(
    container: AppContainer, dataset_name: str, current_report: dict
) -> dict:
    provider_summaries = []
    seen_providers = set()
    reports = [current_report]
    reports.extend(
        record.report
        for record in container.benchmark_history.list_recent(limit=50)
        if record.dataset_name == dataset_name
    )
    for report in reports:
        for provider in report.get("providers") or []:
            provider_name = str(provider.get("provider") or "")
            if not provider_name or provider_name in seen_providers:
                continue
            seen_providers.add(provider_name)
            provider_summaries.append(provider)
    if not provider_summaries:
        return current_report
    return generate_comparison_json_report_from_provider_summaries(
        dataset=dataset_name,
        provider_reports=provider_summaries,
    )


def _benchmark_history(container: AppContainer) -> str:
    records = container.benchmark_history.list_recent(limit=5)
    if not records:
        return """
        <div class="history-block">
          <h3>Recent runs</h3>
          <p class="empty">No saved benchmark runs.</p>
        </div>
        """
    rows = []
    for record in records:
        best = (record.report.get("ranking") or [{}])[0]
        rows.append(
            f"""
            <div class="history-row">
              <span>{_h(record.dataset_name)}</span>
              <small>{_h(_provider_name(best.get("provider", record.provider_name)))}</small>
              <small>{_pct(best.get("field_accuracy"))} accuracy</small>
            </div>
            """
        )
    return f"""
    <div class="history-block">
      <h3>Recent runs</h3>
      <div class="history-list">{''.join(rows)}</div>
    </div>
    """


def _provider_safety_notice(providers, selected_key: str, container: AppContainer) -> str:
    selected = next((provider for provider in providers if provider.key == selected_key), None)
    if selected is None:
        return ""
    info = safety_info(selected, container.settings)
    class_name = "safety-note real" if info.provider_mode == "real" else "safety-note"
    return f'<p class="{class_name}">{_h(info.message)}</p>'


def _benchmark_result(report: dict | None, datasets: dict[str, Path]) -> str:
    if not datasets:
        return """
        <section class="panel benchmark-result">
          <h2>No datasets found</h2>
          <p class="empty">Add a dataset under examples/benchmark/datasets to run a benchmark.</p>
        </section>
        """
    if report is None:
        return """
        <section class="panel benchmark-result empty-state">
          <h2>Select a dataset</h2>
          <p>No benchmark run yet.</p>
        </section>
        """
    ranking = report["ranking"]
    providers = report["providers"]
    best = ranking[0] if ranking else {}
    return f"""
    <section class="panel benchmark-result">
      <div class="section-head">
        <div>
          <p class="eyebrow">Results</p>
          <h2>{_h(report["dataset"])} comparison</h2>
        </div>
        <span class="status approved">{_h(report["providers_count"])} provider</span>
      </div>
      <div class="benchmark-cards">
        {_benchmark_card("Best provider", _provider_name(best.get("provider", "-")))}
        {_benchmark_card("Field accuracy", _pct(best.get("field_accuracy")))}
        {_benchmark_card("Document success", _pct(best.get("document_success_rate")))}
        {_benchmark_card("Estimated cost", _money_value(best.get("estimated_cost_total")))}
      </div>
      {_decision_panel(report.get("decision", {}))}
      <h3>Provider ranking</h3>
      <div class="table-scroll">
        <table class="benchmark-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Provider</th>
              <th>Field accuracy</th>
              <th>Document success</th>
              <th>Avg latency</th>
              <th>Cost</th>
              <th>Error rate</th>
            </tr>
          </thead>
          <tbody>{_ranking_rows(ranking)}</tbody>
        </table>
      </div>
      <h3>Provider details</h3>
      <div class="provider-grid">{_provider_cards(providers)}</div>
      <h3>Known limitations</h3>
      <ul class="issues">{''.join(f"<li>{_h(item)}</li>" for item in report["limitations"])}</ul>
    </section>
    """


def _dataset_options(datasets: dict[str, Path], selected_name: str) -> str:
    if not datasets:
        return '<option value="">No datasets available</option>'
    return "".join(
        f'<option value="{_h(name)}" {"selected" if name == selected_name else ""}>{_h(name)}</option>'
        for name in datasets
    )


def _provider_options(providers, selected_key: str) -> str:
    return "".join(
        f'<option value="{_h(provider.key)}" {"selected" if provider.key == selected_key else ""}>{_h(provider.label)}</option>'
        for provider in providers
    )


def _ranking_rows(ranking: list[dict]) -> str:
    return "".join(
        f"""
        <tr>
          <td>{_h(item["rank"])}</td>
          <td>{_h(_provider_name(item["provider"]))}</td>
          <td>{_pct(item["field_accuracy"])}</td>
          <td>{_pct(item["document_success_rate"])}</td>
          <td>{_h(round(item["average_latency_ms"]))} ms</td>
          <td>{_money_value(item["estimated_cost_total"])}</td>
          <td>{_pct(item["provider_error_rate"])}</td>
        </tr>
        """
        for item in ranking
    )


def _decision_panel(decision: dict) -> str:
    recommended = decision.get("recommended_provider")
    if not recommended:
        return ""
    reasons = decision.get("reasons") or []
    score = float(decision.get("decision_score") or 0)
    return f"""
    <section class="decision-panel">
      <div>
        <p class="eyebrow">Decision</p>
        <h3>{_h(_provider_name(recommended))}</h3>
        <p class="empty">Recommended provider by weighted benchmark score.</p>
      </div>
      <div class="decision-score">
        <span>{score:.2f}</span>
        <small>Decision score</small>
      </div>
      <ul class="decision-reasons">
        {''.join(f"<li>{_h(item)}</li>" for item in reasons[:4])}
      </ul>
    </section>
    """


def _provider_cards(providers: list[dict]) -> str:
    return "".join(
        f"""
        <article class="provider-card">
          <h4>{_h(_provider_name(provider["provider"]))}</h4>
          <dl>
            <dt>Mode</dt><dd>{_h(provider.get("provider_mode", "unknown"))}</dd>
            <dt>Field accuracy</dt><dd>{_pct(provider["field_accuracy"])}</dd>
            <dt>Document success</dt><dd>{_pct(provider["document_success_rate"])}</dd>
            <dt>Missing fields</dt><dd>{_pct(provider["missing_field_rate"])}</dd>
            <dt>Invalid schema</dt><dd>{_pct(provider["invalid_schema_rate"])}</dd>
            <dt>Avg latency</dt><dd>{_h(round(provider["average_latency_ms"]))} ms</dd>
            <dt>Cost / doc</dt><dd>{_money_value(provider["estimated_cost_per_document"])}</dd>
          </dl>
          {_provider_errors(provider)}
          {_failure_examples(provider)}
        </article>
        """
        for provider in providers
    )


def _provider_errors(provider: dict) -> str:
    errors = provider.get("provider_errors") or []
    if not errors:
        return ""
    items = "".join(
        f"<li><strong>{_h(item['document_id'])}</strong>: {_h(item['error'])}</li>"
        for item in errors
    )
    return f"""
    <div class="provider-errors">
      <h5>Provider errors</h5>
      <ul class="issues compact-issues">{items}</ul>
    </div>
    """


def _failure_examples(provider: dict) -> str:
    examples = provider.get("failure_examples") or []
    if not examples:
        if float(provider.get("field_accuracy") or 0) >= 1:
            return '<p class="ok compact-note">No field mismatches in this run.</p>'
        return """
        <div class="failure-examples stale">
          <h5>Failure details unavailable</h5>
          <p class="compact-note">This saved provider summary has mismatches, but it was stored before detailed failure examples were available. Re-run this provider for the selected dataset to populate expected vs predicted values.</p>
        </div>
        """
    rows = "".join(
        f"""
        <tr>
          <td>{_h(item["field_name"])}</td>
          <td>{_h(item["expected"])}</td>
          <td>{_h(item["predicted"])}</td>
        </tr>
        """
        for item in examples
    )
    return f"""
    <div class="failure-examples">
      <h5>Failure details</h5>
      <p class="compact-note">First mismatched fields. Use this to explain why accuracy dropped.</p>
      <div class="table-scroll compact-table">
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Expected</th>
              <th>Predicted</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def _benchmark_card(label: str, value) -> str:
    value_text = str(value)
    compact = " compact-value" if len(value_text) > 18 else ""
    return f'<div class="benchmark-card{compact}"><span>{_h(value_text)}</span><small>{_h(label)}</small></div>'


def _provider_name(value) -> str:
    return str(value).replace("+", " + ")


def _login_page(error: str) -> str:
    return _layout(
        "Sign in",
        f"""
        <main class="login-shell">
          <section class="login-panel">
            <p class="eyebrow">Document Intelligence MVP</p>
            <h1>Sign in to the console</h1>
            {_notice(error, "error")}
            <form class="stack" method="post" action="/ui/login">
              <label for="admin_token">Admin token</label>
              <input id="admin_token" name="admin_token" type="password" autocomplete="current-password" required>
              <button class="button primary" type="submit">Sign in</button>
            </form>
          </section>
        </main>
        """,
    )


def _selected_document(container: AppContainer, documents, document_id: UUID | None):
    if document_id is not None:
        try:
            return container.documents.get(document_id)
        except NotFoundError:
            return None
    return documents[0] if documents else None


def _document_list(documents, selected) -> str:
    if not documents:
        return '<p class="empty">No documents yet.</p>'
    rows = []
    selected_id = selected.id if selected else None
    for document in documents:
        active = " active" if document.id == selected_id else ""
        rows.append(
            f"""
            <a class="doc-row{active}" href="/ui?document_id={document.id}">
              <span>{_h(document.original_filename)}</span>
              <span class="status {_h(document.status.value)}">{_h(document.status.value)}</span>
            </a>
            """
        )
    return "".join(rows)


def _review_queue(documents) -> str:
    if not documents:
        return '<p class="empty">Queue is clear.</p>'
    return "".join(
        f'<a class="doc-row" href="/ui?document_id={document.id}">{_h(document.original_filename)}</a>'
        for document in documents
    )


def _copilot_panel(document, result: CopilotResult | None) -> str:
    document_input = (
        f'<input type="hidden" name="document_id" value="{document.id}">' if document else ""
    )
    explain_disabled = "" if document else "disabled"
    execute_form = _copilot_execute_form(document)
    return f"""
    <section class="copilot-panel">
      <div class="section-head">
        <h2>Ask Copilot</h2>
        <span class="status read_only">agent</span>
      </div>
      <div class="copilot-actions">
        <form method="post" action="/ui/copilot">
          <input type="hidden" name="action" value="summarize">
          <button class="button small" type="submit">Summarize workflow</button>
        </form>
        <form method="post" action="/ui/copilot">
          <input type="hidden" name="action" value="explain">
          {document_input}
          <button class="button small" type="submit" {explain_disabled}>Explain selected</button>
        </form>
        <form method="post" action="/ui/copilot">
          <input type="hidden" name="action" value="recommend">
          {document_input}
          <button class="button small" type="submit" {explain_disabled}>Recommend next</button>
        </form>
        {execute_form}
      </div>
      {_copilot_result(result)}
    </section>
    """


def _copilot_execute_form(document) -> str:
    if document is None:
        return """
        <button class="button small" type="button" disabled>Execute with confirmation</button>
        """
    tool_name = ""
    label = "Execute with confirmation"
    if document.status == DocumentStatus.QUEUED:
        tool_name = AgentToolName.PROCESS_DOCUMENT.value
        label = "Execute process"
    elif document.status == DocumentStatus.APPROVED:
        tool_name = AgentToolName.EXPORT_APPROVED_CSV.value
        label = "Execute export"
    if not tool_name:
        return """
        <button class="button small" type="button" disabled>Execute with confirmation</button>
        """
    return f"""
    <form method="post" action="/ui/copilot">
      <input type="hidden" name="action" value="execute">
      <input type="hidden" name="document_id" value="{document.id}">
      <input type="hidden" name="execute_tool" value="{_h(tool_name)}">
      <button class="button small primary" type="submit">{_h(label)}</button>
    </form>
    """


def _copilot_result(result: CopilotResult | None) -> str:
    if result is None:
        return '<p class="empty">Ask for a workflow summary or select a document for guidance.</p>'
    response = result.tool_response
    recommendation = response.data.get("recommendation")
    recommendation_block = ""
    if isinstance(recommendation, dict):
        recommendation_block = f"""
        <div class="copilot-card">
          <small>Recommendation</small>
          <strong>{_h(recommendation.get("action"))}</strong>
          <p>{_h(recommendation.get("why"))}</p>
          {_copilot_list("Evidence", recommendation.get("evidence"))}
          {_copilot_list("Why not", recommendation.get("why_not"))}
        </div>
        """
    escalation = ""
    if response.human_escalation_reason:
        escalation = f"""
        <div class="copilot-card warning">
          <small>Human escalation</small>
          <p>{_h(response.human_escalation_reason)}</p>
        </div>
        """
    return f"""
    <div class="copilot-result">
      <div class="copilot-card">
        <small>{_h(response.tool_name.value)} · {_h(response.status)} · {_h(response.risk.value)}</small>
        <strong>{_h(response.summary)}</strong>
        <p>Confidence: <b>{_h(response.confidence.value)}</b></p>
        {_copilot_list("Evidence", response.evidence)}
      </div>
      {recommendation_block}
      {escalation}
    </div>
    """


def _copilot_list(label: str, items) -> str:
    if not items:
        return ""
    return (
        f"<small>{_h(label)}</small><ul>"
        + "".join(f"<li>{_h(item)}</li>" for item in items)
        + "</ul>"
    )


def _document_detail(container: AppContainer, document) -> str:
    if document is None:
        return """
        <div class="empty-state">
          <h2>No document selected</h2>
          <p>Upload a PDF invoice to start the processing workflow.</p>
        </div>
        """
    extraction = None
    try:
        extraction = container.extractions.get_for_document(document.id)
    except NotFoundError:
        pass
    return f"""
    <div class="detail-head">
      <div>
        <p class="eyebrow">Selected document</p>
        <h2>{_h(document.original_filename)}</h2>
      </div>
      <span class="status {_h(document.status.value)}">{_h(document.status.value)}</span>
    </div>
    <div class="actions">
      {_process_button(document)}
      {_review_buttons(document)}
    </div>
    <div class="document-workbench">
      <section class="preview-pane">
        <h3>Source document</h3>
        <iframe title="PDF preview" src="/ui/documents/{document.id}/preview"></iframe>
      </section>
      <section class="result-pane">
        <h3>Extraction</h3>
        {_extraction_table(extraction)}
      </section>
      <section class="validation-pane">
        <h3>Validation</h3>
        {_validation_list(extraction)}
      </section>
    </div>
    {_review_form(document, extraction)}
    <section>
      <h3>Audit trail</h3>
      {_audit_list(container, document)}
    </section>
    """


def _process_button(document) -> str:
    if document.status != DocumentStatus.QUEUED:
        return ""
    return f"""
    <form method="post" action="/ui/documents/{document.id}/process">
      <button class="button primary" type="submit">Process</button>
    </form>
    """


def _review_buttons(document) -> str:
    if document.status != DocumentStatus.NEEDS_REVIEW:
        return ""
    return f"""
    <form method="post" action="/ui/review/{document.id}/approve">
      <button class="button primary" type="submit">Approve</button>
    </form>
    <form method="post" action="/ui/review/{document.id}/reject">
      <input type="hidden" name="notes" value="Rejected from UI">
      <button class="button danger" type="submit">Reject</button>
    </form>
    """


def _review_form(document, extraction) -> str:
    if document.status != DocumentStatus.NEEDS_REVIEW or extraction is None:
        return ""
    data = extraction.extraction_result.extraction.data
    return f"""
    <section>
      <h3>Review correction</h3>
      <form class="review-grid" method="post" action="/ui/review/{document.id}/save">
        {_input("vendor_name", "Vendor", data.vendor_name)}
        {_input("invoice_number", "Invoice number", data.invoice_number)}
        {_input("invoice_date", "Invoice date", _date(data.invoice_date), "date")}
        {_input("due_date", "Due date", _date(data.due_date), "date")}
        {_input("subtotal", "Subtotal", data.subtotal)}
        {_input("tax", "Tax", data.tax)}
        {_input("total", "Total", data.total)}
        {_input("currency", "Currency", data.currency)}
        <label class="wide">Notes<textarea name="notes" rows="3"></textarea></label>
        <button class="button primary" type="submit">Save correction</button>
      </form>
    </section>
    """


def _extraction_table(extraction) -> str:
    if extraction is None:
        return '<p class="empty">No extraction yet.</p>'
    data = extraction.extraction_result.extraction.data
    rows = [
        ("Vendor", data.vendor_name),
        ("Invoice number", data.invoice_number),
        ("Invoice date", _date(data.invoice_date)),
        ("Due date", _date(data.due_date)),
        ("Subtotal", data.subtotal),
        ("Tax", data.tax),
        ("Total", data.total),
        ("Currency", data.currency),
    ]
    return (
        "<table>"
        + "".join(f"<tr><th>{_h(label)}</th><td>{_h(value)}</td></tr>" for label, value in rows)
        + "</table>"
    )


def _validation_list(extraction) -> str:
    if extraction is None:
        return '<p class="empty">Run processing first.</p>'
    issues = extraction.validation_report.issues
    if not issues:
        return '<p class="ok">No validation issues.</p>'
    return (
        '<ul class="issues">'
        + "".join(
            f"<li><strong>{_h(issue.field_name)}</strong>: {_h(issue.message)}</li>"
            for issue in issues
        )
        + "</ul>"
    )


def _audit_list(container: AppContainer, document) -> str:
    events = container.audits.list_for_document(document.id)
    if not events:
        return '<p class="empty">No audit events.</p>'
    return (
        '<ol class="audit">'
        + "".join(
            f"<li><span>{_h(event.event_type)}</span><small>{_h(event.created_at.isoformat())}</small></li>"
            for event in events
        )
        + "</ol>"
    )


def _input(name: str, label: str, value, input_type: str = "text") -> str:
    return (
        f"<label>{_h(label)}"
        f'<input name="{_h(name)}" type="{input_type}" value="{_h(value)}">'
        "</label>"
    )


def _invoice_data(
    vendor_name: str,
    invoice_number: str,
    invoice_date: str,
    due_date: str,
    subtotal: str,
    tax: str,
    total: str,
    currency: str,
) -> InvoiceData:
    return InvoiceData(
        vendor_name=_blank(vendor_name),
        invoice_number=_blank(invoice_number),
        invoice_date=_parse_date(invoice_date),
        due_date=_parse_date(due_date),
        subtotal=_parse_decimal(subtotal),
        tax=_parse_decimal(tax),
        total=_parse_decimal(total),
        currency=_blank(currency),
    )


def _parse_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def _parse_decimal(value: str) -> Decimal | None:
    value = value.strip()
    return Decimal(value) if value else None


def _blank(value: str) -> str | None:
    value = value.strip()
    return value or None


def _metric(label: str, value) -> str:
    return f'<div class="metric"><span>{_h(value)}</span><small>{_h(label)}</small></div>'


def _notice(message: str, kind: str) -> str:
    if not message:
        return ""
    return f'<div class="notice {kind}">{_h(message)}</div>'


def _layout(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{_h(title)}</title>
        <style>{_css()}</style>
      </head>
      <body>{body}</body>
    </html>
    """


def _css() -> str:
    return """
    :root { color-scheme: light; --bg: #f6f7f9; --panel: #ffffff; --ink: #171a1f; --muted: #667085; --line: #d9dee7; --blue: #175cd3; --green: #067647; --red: #b42318; --amber: #b54708; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); font-family: Arial, Helvetica, sans-serif; letter-spacing: 0; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { font-size: 30px; margin-bottom: 0; }
    h2 { font-size: 20px; }
    h3 { font-size: 16px; margin-bottom: 12px; }
    a { color: inherit; text-decoration: none; }
    input, textarea, button, select { font: inherit; }
    input, textarea, select { width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; background: #fff; }
    label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px 0; text-align: left; vertical-align: top; }
    th { width: 150px; color: var(--muted); font-weight: 600; }
    .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 28px 32px 16px; }
    .top-actions { display: flex; gap: 10px; align-items: center; }
    .eyebrow { color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 6px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 0 32px 16px; }
    .metric, .panel, .login-panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
    .metric { padding: 16px; display: grid; gap: 4px; }
    .metric span { font-size: 26px; font-weight: 700; }
    .metric small, .empty, .audit small { color: var(--muted); }
    .workspace { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 16px; padding: 0 32px 32px; }
    .panel { padding: 18px; min-width: 0; }
    .sidebar { align-self: start; }
    .detail { min-height: 560px; }
    .stack { display: grid; gap: 10px; margin-bottom: 22px; }
    .section-head, .detail-head, .actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .actions { justify-content: flex-start; margin: 14px 0 22px; }
    .button { border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; background: #fff; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; min-height: 38px; }
    .button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    .button.danger { background: var(--red); border-color: var(--red); color: #fff; }
    .button.ghost { background: transparent; }
    .button.small { min-height: 32px; padding: 7px 10px; font-size: 13px; }
    .document-list { display: grid; gap: 8px; margin-bottom: 22px; }
    .doc-row { display: flex; justify-content: space-between; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: 6px; padding: 10px; background: #fff; }
    .doc-row.active { border-color: var(--blue); box-shadow: inset 3px 0 0 var(--blue); }
    .compact .doc-row { font-size: 14px; }
    .copilot-panel { border-top: 1px solid var(--line); padding-top: 16px; margin-top: 8px; }
    .copilot-actions { display: grid; grid-template-columns: 1fr; gap: 8px; margin-bottom: 14px; }
    .copilot-actions form, .copilot-actions button { width: 100%; }
    .copilot-result { display: grid; gap: 10px; }
    .copilot-card { border: 1px solid var(--line); border-radius: 6px; background: #fff; padding: 10px; font-size: 13px; overflow-wrap: anywhere; }
    .copilot-card.warning { border-color: #fedf89; background: #fffaeb; }
    .copilot-card small { display: block; color: var(--muted); margin-bottom: 5px; }
    .copilot-card strong { display: block; margin-bottom: 6px; line-height: 1.3; }
    .copilot-card p { margin: 0 0 8px; color: #344054; line-height: 1.35; }
    .copilot-card ul { margin: 0 0 8px; padding-left: 18px; color: #344054; }
    .copilot-card li { margin-bottom: 4px; }
    .status { border-radius: 999px; padding: 4px 8px; color: #344054; background: #eef2f6; font-size: 12px; white-space: nowrap; }
    .status.approved, .status.exported { color: var(--green); background: #dcfae6; }
    .status.needs_review, .status.processing, .status.queued { color: var(--amber); background: #fef0c7; }
    .status.failed, .status.rejected { color: var(--red); background: #fee4e2; }
    .grid.two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, .65fr); gap: 24px; }
    .document-workbench { display: grid; grid-template-columns: minmax(320px, .95fr) minmax(320px, 1fr) minmax(240px, .55fr); gap: 18px; align-items: start; }
    .preview-pane iframe { width: 100%; height: 620px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }
    .issues, .audit { padding-left: 20px; }
    .audit li { margin-bottom: 8px; }
    .audit span { display: block; font-weight: 600; }
    .ok { color: var(--green); }
    .notice { margin: 0 32px 14px; padding: 10px 12px; border-radius: 6px; border: 1px solid var(--line); background: #fff; }
    .notice.success { border-color: #abefc6; color: var(--green); }
    .notice.error { border-color: #fecdca; color: var(--red); }
    .login-shell { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
    .login-panel { width: min(420px, 100%); padding: 24px; }
    .review-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 24px; }
    .review-grid .wide { grid-column: 1 / -1; }
    .benchmark-shell { display: grid; grid-template-columns: minmax(280px, 340px) minmax(0, 1fr); gap: 20px; align-items: start; padding: 0 32px 32px; }
    .agentops-shell { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, .42fr); gap: 20px; align-items: start; padding: 0 32px 32px; }
    .backoffice-shell { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 20px; align-items: start; padding: 0 32px 32px; }
    .backoffice-grid { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; align-items: start; margin: 18px 0; }
    .backoffice-summary dl { display: grid; grid-template-columns: 160px 1fr; gap: 8px 12px; margin: 0 0 18px; }
    .backoffice-summary dt { color: var(--muted); }
    .backoffice-summary dd { margin: 0; font-weight: 700; overflow-wrap: anywhere; }
    .plan-control { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 16px 0; margin: 16px 0; }
    .plan-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .step-list { display: grid; gap: 10px; }
    .step-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }
    .step-row p { color: #344054; margin: 6px 0; line-height: 1.35; }
    .step-row small { color: var(--muted); line-height: 1.35; overflow-wrap: anywhere; }
    .step-actions, .approval-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .agentops-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .agentops-main, .agentops-detail { min-height: 520px; }
    .agentops-grid { display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; align-items: start; }
    .benchmark-table tr.active td { background: #f8fafc; }
    .benchmark-control { position: sticky; top: 16px; }
    .benchmark-form { display: grid; gap: 14px; }
    .safety-note { margin: 0; padding: 10px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--muted); font-size: 13px; line-height: 1.35; }
    .safety-note.real { border-color: #fedf89; background: #fffaeb; color: var(--amber); }
    .history-block { border-top: 1px solid var(--line); margin-top: 18px; padding-top: 16px; }
    .history-list { display: grid; gap: 8px; }
    .history-row { display: grid; gap: 3px; border: 1px solid var(--line); border-radius: 6px; padding: 10px; background: #fff; }
    .history-row span { font-weight: 700; overflow-wrap: anywhere; }
    .history-row small { color: var(--muted); }
    .benchmark-result { min-height: 520px; }
    .benchmark-cards { display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 14px; margin: 18px 0 26px; }
    .benchmark-card { min-height: 102px; padding: 14px; display: grid; align-content: space-between; gap: 10px; background: #fff; border: 1px solid var(--line); border-radius: 8px; }
    .benchmark-card span { display: block; font-size: 22px; line-height: 1.2; font-weight: 700; overflow-wrap: anywhere; }
    .benchmark-card.compact-value span { font-size: 20px; }
    .benchmark-card small { color: var(--muted); }
    .decision-panel { display: grid; grid-template-columns: minmax(220px, 1fr) 150px minmax(260px, 1.2fr); gap: 16px; align-items: start; border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin-bottom: 24px; background: #fff; }
    .decision-panel h3 { font-size: 20px; margin-bottom: 6px; overflow-wrap: anywhere; }
    .decision-score { display: grid; gap: 4px; justify-items: start; }
    .decision-score span { font-size: 28px; font-weight: 700; }
    .decision-score small { color: var(--muted); }
    .decision-reasons { margin: 0; padding-left: 18px; color: var(--muted); font-size: 14px; }
    .decision-reasons li { margin-bottom: 6px; }
    .table-scroll { overflow-x: auto; margin-bottom: 24px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .benchmark-table { min-width: 760px; }
    .benchmark-table th, .benchmark-table td { padding: 12px 14px; }
    .benchmark-table th { width: auto; }
    .benchmark-table tbody tr:last-child td { border-bottom: 0; }
    .provider-grid { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 14px; margin-bottom: 22px; }
    .provider-card { border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: #fff; }
    .provider-card h4 { margin: 0 0 14px; overflow-wrap: anywhere; }
    .provider-card dl { display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; margin: 0; font-size: 14px; }
    .provider-card dt { color: var(--muted); }
    .provider-card dd { margin: 0; font-weight: 700; }
    .provider-errors, .failure-examples { border-top: 1px solid var(--line); margin-top: 14px; padding-top: 12px; }
    .provider-errors h5, .failure-examples h5 { margin: 0 0 6px; font-size: 14px; }
    .compact-issues { margin: 0; font-size: 13px; }
    .compact-note { color: var(--muted); font-size: 13px; line-height: 1.35; margin: 0; }
    .compact-table { margin: 10px 0 0; }
    .compact-table table { min-width: 520px; font-size: 13px; }
    .compact-table th, .compact-table td { padding: 8px 10px; overflow-wrap: anywhere; }
    .compact-table th { width: auto; }
    .empty-state { display: grid; place-items: center; min-height: 420px; text-align: center; color: var(--muted); }
    @media (max-width: 1180px) { .document-workbench { grid-template-columns: 1fr; } .preview-pane iframe { height: 520px; } }
    @media (max-width: 1180px) { .benchmark-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 1180px) { .decision-panel { grid-template-columns: 1fr; } }
    @media (max-width: 1180px) { .agentops-grid, .backoffice-grid { grid-template-columns: 1fr; } .agentops-shell, .backoffice-shell { grid-template-columns: 1fr; } }
    @media (max-width: 900px) { .workspace, .metrics, .grid.two, .review-grid, .benchmark-shell, .provider-grid, .agentops-metrics { grid-template-columns: 1fr; } .benchmark-control { position: static; } .topbar { align-items: flex-start; } }
    @media (max-width: 680px) { .benchmark-cards { grid-template-columns: 1fr; } }
    @media (max-width: 560px) { .topbar, .metrics, .workspace, .benchmark-shell, .backoffice-shell { padding-left: 14px; padding-right: 14px; } h1 { font-size: 24px; } .section-head, .detail-head, .top-actions, .step-row { align-items: flex-start; grid-template-columns: 1fr; flex-direction: column; } .step-actions { justify-content: flex-start; } }
    """


def _date(value) -> str:
    return value.isoformat() if value else ""


def _pct(value) -> str:
    return f"{float(value or 0):.2%}"


def _pct_or_na(value) -> str:
    if value is None:
        return "n/a"
    return _pct(value)


def _number_or_na(value) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}"


def _tool_correctness(value) -> str:
    if value is None:
        return "unevaluated"
    return "yes" if value else "no"


def _money_value(value) -> str:
    if value is None:
        return "n/a"
    return f"${float(value):.4f}".rstrip("0").rstrip(".")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _h(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def _url(value: str) -> str:
    return quote(value, safe="")


def _safe_header_filename(value: str) -> str:
    return value.replace('"', "").replace("\r", "").replace("\n", "") or "document.pdf"


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
