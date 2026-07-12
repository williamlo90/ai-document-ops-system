import { expect, test, type Page } from '@playwright/test'

const now = '2026-06-30T10:00:00Z'

function aggregate(approvalStatus = 'pending') {
  const step = { id: 'step-1', action_type: 'export_invoice', risk_level: 'high', tool_name: 'export', requires_approval: true, status: 'approved', why_this: 'Invoice is ready.', why_not: null }
  const approval = { id: 'approval-1', work_item_id: 'item-1', action_step_id: 'step-1', status: approvalStatus, reviewer_notes: null, reviewed_by: null, reviewed_at: null, created_at: now }
  return {
    id: 'item-1', title: 'Review ACME invoice', work_type: 'invoice_export', priority: 'high', status: 'awaiting_human', linked_document_ids: ['doc-1'], business_context: { requested_outcome: 'Export approved invoice' }, created_at: now, updated_at: now, current_plan_id: 'plan-1', assignee: 'Finance reviewer', requested_outcome: 'Export approved invoice', tags: ['invoice'],
    plans: [], current_plan: { id: 'plan-1', planner_version: 'test', overall_confidence: 'high', escalation_reason: null, requires_human: true, created_at: now, steps: [step], agent_run_id: 'run-1' }, drafts: [], approvals: [approval], policy_decisions: [], activity: [],
  }
}

async function mockWorkflow(page: Page, calls: string[], approvalStatus = 'pending', stage = 'needs_attention') {
  const item = aggregate(approvalStatus)
  const document = { id: 'doc-1', filename: 'acme.pdf', original_filename: 'acme.pdf', status: 'approved', created_at: now }
  await page.route('**/*', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/auth/session') return route.fulfill({ json: { authenticated: true, actor: 'e2e-admin' } })
    if (path === '/backoffice/workspace') return route.fulfill({ json: { workspace_id: 'e2e', work_items: [item], pending_approvals: item.approvals, documents: [document], metrics: { work_items: 1, pending_approvals: 1, drafts: 0, policy_decisions: 0 } } })
    if (path === '/operations/notifications') return route.fulfill({ json: { notifications: [], unread_count: 0 } })
    if (path === '/providers/health') return route.fulfill({ json: { overall_status: 'healthy', providers: [] } })
    if (path === '/operations/jobs') return route.fulfill({ json: { worker: { status: 'healthy', queued_jobs: 0, failed_jobs: 0, stalled_jobs: 0, evidence: 'ok' }, failed_jobs: [] } })
    if (path === '/backoffice/work-items/item-1') return route.fulfill({ json: { work_item: item } })
    if (path === '/documents/doc-1') return route.fulfill({ json: { document, extraction: { data: {}, confidence: [], validation: [{ field_name: 'total', message: 'Total does not match line items', severity: 'error' }] }, audit_events: [] } })
    if (path === '/documents/doc-1/content') return route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\n%%EOF' })
    if (path === '/documents/doc-1/workflow') return route.fulfill({ json: { document, extraction: null, work_item: item, current_stage: stage, current_owner: 'Finance reviewer', waiting_for: 'Human decision', next_action: 'Review', attention_reason: 'Approval required', activity: [] } })
    if (path === '/invoices/doc-1/workflow') return route.fulfill({ status: 410, json: { detail: 'Use the document workflow projection.' } })
    if (path.startsWith('/invoices/doc-1/') && ['retry', 'request-correction', 'escalate'].some((action) => path.endsWith(`/${action}`))) return route.fulfill({ status: 410, json: { detail: 'Use the document workflow command.' } })
    if (request.method() !== 'GET') {
      calls.push(`${request.method()} ${path}`)
      return route.fulfill({ json: { status: 'ok', work_item: item } })
    }
    return route.continue()
  })
  await page.addInitScript(() => localStorage.setItem('docops-role', 'administrator'))
  await page.goto('/')
  await page.getByText('Review ACME invoice', { exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'Review ACME invoice' })).toBeVisible()
}

test('approval mutation is wired to the selected approval', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls)
  await page.getByRole('button', { name: 'Approvals' }).last().click()
  await page.getByPlaceholder('Decision notes and evidence considered...').fill('Evidence checked')
  await page.getByRole('button', { name: 'Approve' }).click()
  await expect.poll(() => calls).toContain('POST /backoffice/approvals/approval-1/approve')
})

test('rejection records the human decision against the selected approval', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls)
  await page.getByRole('button', { name: 'Approvals' }).last().click()
  await page.getByPlaceholder('Decision notes and evidence considered...').fill('Evidence is insufficient')
  await page.getByRole('button', { name: 'Reject' }).click()
  await expect.poll(() => calls).toContain('POST /backoffice/approvals/approval-1/reject')
})

test('correction and escalation commands remain available from workflow activity', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls)
  await page.getByRole('button', { name: 'Activity' }).click()
  await page.getByRole('textbox', { name: 'Reason or correction instruction' }).fill('PO evidence is ambiguous')
  await page.getByRole('button', { name: 'Request Correction' }).click()
  await expect.poll(() => calls).toContain('POST /documents/doc-1/request-correction')
  await page.getByRole('button', { name: 'Escalate' }).click()
  await expect.poll(() => calls).toContain('POST /documents/doc-1/escalate')
})

test('approved execution calls the bounded step endpoint', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls, 'approved')
  await page.getByRole('button', { name: 'Plan' }).click()
  await page.getByTitle('Execute approved step').click()
  await expect.poll(() => calls).toContain('POST /backoffice/work-items/item-1/steps/step-1/execute')
})

test('durable workflow is restored after a browser reload', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Document Queue' }).first()).toBeVisible()
  await expect(page.getByText('Review ACME invoice', { exact: true }).first()).toBeVisible()
})

test('validation failures are visible with their stored evidence', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls)
  await expect(page.getByText('1 validation issue requires review')).toBeVisible()
  await expect(page.getByText('Total does not match line items')).toBeVisible()
})

test('provider failure exposes a durable retry command', async ({ page }) => {
  const calls: string[] = []
  await mockWorkflow(page, calls, 'pending', 'failed')
  await page.getByRole('button', { name: 'Activity' }).click()
  await page.getByRole('button', { name: 'Retry Processing' }).click()
  await expect.poll(() => calls).toContain('POST /documents/doc-1/retry')
})
