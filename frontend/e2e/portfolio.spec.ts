import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

test.skip(!process.env.CAPTURE_PORTFOLIO, 'Portfolio capture runs only through npm run capture:portfolio.')

const now = '2026-07-08T05:30:00Z'
const step = { id: 'step-export', action_type: 'export_invoice', risk_level: 'high', tool_name: 'invoice_export', requires_approval: true, status: 'pending', why_this: 'Validated invoice data is ready for controlled export.', why_not: 'External execution cannot proceed without reviewer approval.' }
const approval = { id: 'approval-portfolio', work_item_id: 'item-portfolio', action_step_id: step.id, status: 'pending', reviewer_notes: null, reviewed_by: null, reviewed_at: null, created_at: now }
const item = {
  id: 'item-portfolio', title: 'Review ACME invoice exception', work_type: 'invoice_export', priority: 'high', status: 'awaiting_human', linked_document_ids: ['doc-portfolio'],
  business_context: { vendor_name: 'ACME Industrial', total: '12,480.00', currency: 'USD', requested_outcome: 'Validate and export approved invoice' }, created_at: now, updated_at: now,
  current_plan_id: 'plan-portfolio', assignee: 'Finance Review', requested_outcome: 'Validate and export approved invoice', tags: ['invoice', 'total-mismatch'],
  plans: [], current_plan: { id: 'plan-portfolio', planner_version: 'planner-v2', overall_confidence: 'medium', escalation_reason: 'High-value export requires human approval.', requires_human: true, created_at: now, steps: [step], agent_run_id: 'run-portfolio' },
  drafts: [], approvals: [approval], policy_decisions: [{ id: 'policy-1', action_step_id: step.id, action_type: 'export_invoice', autonomy_level: 'balanced', risk_level: 'high', allowed: true, requires_confirmation: true, reason: 'External financial export is approval gated.' }],
  activity: [{ id: 'event-1', event_type: 'validation_completed', actor: 'document-validator', summary: 'Invoice totals require reviewer confirmation.', source: 'workflow', created_at: now }],
}
const document = { id: 'doc-portfolio', filename: 'acme-industrial-invoice.pdf', original_filename: 'acme-industrial-invoice.pdf', status: 'needs_review', created_at: now }
const extraction = {
  data: { vendor_name: 'ACME Industrial', invoice_number: 'INV-2026-1842', invoice_date: '2026-07-05', total: '12,480.00', tax_amount: '980.00', currency: 'USD', line_items: [{ description: 'Industrial control modules', quantity: '8', unit_price: '1,437.50', amount: '11,500.00' }] },
  confidence: [{ field_name: 'vendor_name', score: .96, source_page: 1, source_text: 'ACME Industrial' }, { field_name: 'total', score: .58, source_page: 1, source_text: 'Total USD 12,480.00' }],
  validation: [{ field_name: 'total', message: 'Total does not match the sum of line items and tax.', severity: 'error' }],
}
const run = { id: 'run-portfolio', actor: 'document-agent', request: 'Validate and prepare invoice export', intent: 'invoice_export', prompt_version: 'planner-v2', created_at: now, evaluation: { expected_tool: 'invoice_export', selected_tool: 'invoice_export', tool_selection_correct: true, confidence: 'medium', confidence_score: .72, failure_type: null, human_escalated: true, blocked_action_count: 1, tool_call_count: 2, estimated_cost_usd: .003, successful_completion: true, decision_reason: 'Escalated because external export requires approval.' } }

test('capture portfolio surfaces', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.route('**/*', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (pathname === '/auth/session') return route.fulfill({ json: { authenticated: true, actor: 'portfolio-reviewer' } })
    if (pathname === '/backoffice/workspace') return route.fulfill({ json: { workspace_id: 'portfolio', work_items: [item], pending_approvals: [approval], documents: [document], metrics: { work_items: 1, pending_approvals: 1, drafts: 0, policy_decisions: 1 } } })
    if (pathname === `/backoffice/work-items/${item.id}`) return route.fulfill({ json: { work_item: item } })
    if (pathname === `/documents/${document.id}`) return route.fulfill({ json: { document, extraction, audit_events: [] } })
    if (pathname === `/documents/${document.id}/content`) return route.fulfill({ contentType: 'application/pdf', body: readFileSync(path.resolve('../sample_invoice.pdf')) })
    if (pathname === `/documents/${document.id}/workflow`) return route.fulfill({ json: { document, extraction, work_item: item, current_stage: 'needs_attention', current_owner: 'Finance Review', waiting_for: 'Human approval', next_action: 'Review evidence', attention_reason: 'Total mismatch requires confirmation.', activity: item.activity } })
    if (pathname === `/invoices/${document.id}/workflow`) return route.fulfill({ status: 410, json: { detail: 'Use the document workflow projection.' } })
    if (pathname === '/operations/notifications') return route.fulfill({ json: { notifications: [], unread_count: 0 } })
    if (pathname === '/providers/health') return route.fulfill({ json: { overall_status: 'healthy', providers: [] } })
    if (pathname === '/agentops/runs') return route.fulfill({ json: { runs: [run] } })
    if (pathname === '/agentops/summary') return route.fulfill({ json: { summary: { total_runs: 1, evaluated_runs: 1, tool_selection_accuracy: 1, unsafe_action_prevention_rate: 1, successful_completion_rate: 1, escalation_rate: 1, average_confidence: .72, average_tool_calls_per_task: 2, average_latency_ms: 840, estimated_cost_per_run: .003, confidence_distribution: { medium: 1 }, failure_counts: {}, failure_trend: [] } } })
    if (pathname === '/agentops/regression') return route.fulfill({ json: { regression: { deltas: [] } } })
    if (pathname === '/agentops/prompt-versions') return route.fulfill({ json: { prompt_versions: [{ prompt_version: 'planner-v2', total_runs: 1, evaluated_runs: 1, tool_selection_accuracy: 1, escalation_rate: 1, average_confidence: .72, estimated_cost_per_run: .003 }] } })
    return route.continue()
  })
  await page.addInitScript(() => localStorage.setItem('docops-role', 'administrator'))
  await page.goto('/')
  const output = path.resolve('../docs/assets/screenshots')
  await expect(page.getByRole('heading', { name: 'Document Queue' }).first()).toBeVisible()
  await page.screenshot({ path: path.join(output, 'document-queue.png'), fullPage: true })

  await page.locator('aside.sidebar').getByRole('button', { name: 'Exceptions' }).click()
  await expect(page.getByText('All Exceptions')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'exception-review.png'), fullPage: true })

  await page.getByText(item.title, { exact: true }).click()
  await expect(page.getByRole('button', { name: 'Workspace' })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'document-workspace.png'), fullPage: true })

  await page.getByRole('button', { name: 'Approvals' }).last().click()
  await expect(page.getByText('Evidence Snapshot')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'approval-review.png'), fullPage: true })

  const sidebar = page.locator('aside.sidebar')
  await sidebar.getByRole('button', { name: 'Technical Evidence' }).click()
  await sidebar.getByRole('button', { name: 'Reliability Evidence' }).click()
  await expect(page.getByText('Local evaluation evidence')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'technical-evidence.png'), fullPage: true })
})
