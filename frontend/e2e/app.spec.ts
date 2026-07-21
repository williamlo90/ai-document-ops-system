import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const observedAt = '2026-07-21T03:00:00Z'

type TestRole = 'administrator' | 'reviewer' | 'uploader'

async function clickPrimaryNavigation(page: Page, name: string) {
  const link = page.getByRole('link', { name, exact: true })
  const usesDrawer = await page.evaluate(() => window.matchMedia('(max-width: 720px)').matches)
  if (usesDrawer) {
    const drawerOpen = await page.locator('.ops-sidebar').evaluate((element) => element.classList.contains('is-open'))
    if (!drawerOpen) await page.getByRole('button', { name: 'Open navigation' }).click()
    await link.click()
    return
  }
  const isReachable = await link.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.left < window.innerWidth
  })
  if (!isReachable) await page.getByRole('button', { name: 'Open navigation' }).click()
  await link.click()
}

async function exposePrimaryNavigation(page: Page) {
  const navigation = page.getByRole('navigation', { name: 'Primary navigation' })
  if (!(await navigation.isVisible())) await page.getByRole('button', { name: 'Open navigation' }).click()
}

async function mockProductApi(
  page: Page,
  options: { role?: TestRole; overviewFailure?: boolean } = {},
) {
  const role = options.role ?? 'administrator'
  await page.route('**/*', async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())

    if (pathname === '/auth/session') {
      await route.fulfill({ json: {
        authenticated: true,
        actor: role === 'administrator' ? 'E2E Administrator' : role === 'reviewer' ? 'E2E Reviewer' : 'E2E Uploader',
        user_id: `e2e-${role}`,
        workspace_id: 'e2e',
        role,
        is_admin: role === 'administrator',
      } })
      return
    }
    if (request.resourceType() === 'document') {
      await route.continue()
      return
    }
    if (pathname === '/backoffice/workspace') {
      await route.fulfill({ json: { workspace_id: 'e2e', work_items: [], pending_approvals: [], documents: [], metrics: {} } })
      return
    }
    if (pathname === '/overview/dashboard') {
      if (options.overviewFailure) {
        await route.fulfill({ status: 503, json: { detail: 'Dashboard temporarily unavailable' } })
      } else {
        await route.fulfill({ json: overviewFixture(role) })
      }
      return
    }
    if (pathname === '/invoices') {
      await route.fulfill({ json: {
        items: [], page: 1, page_size: 10, total: 0, total_pages: 1,
        summary: { all: 0, waiting_review: 0, needs_correction: 0, approved: 0, exported: 0 },
        insights: { flagged: 0, duplicates_suspected: 0, tax_amount_issues: 0 },
      } })
      return
    }
    if (pathname === '/review/worklist') {
      await route.fulfill({ json: {
        items: [], page: 1, page_size: 10, total: 0, total_pages: 1,
        summary: { in_queue: 0, high_risk: 0, invoice_due_today: 0, average_review_seconds: null },
      } })
      return
    }
    if (pathname === '/exceptions') {
      await route.fulfill({ json: {
        items: [], page: 1, page_size: 10, total: 0, total_pages: 1,
        summary: { open_exceptions: 0, high_risk: 0, warning_issues: 0, invoices_affected: 0, categories: {}, top_issues: [] },
        assignee_options: [],
        capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
      } })
      return
    }
    if (pathname === '/exports/workspace') {
      await route.fulfill({ json: {
        capabilities: { destinations: [], scheduling: false, drafts: true, retry: true, configured_provider: 'csv', destination_available: true },
        summary: {
          ready: { count: 0, amount: null, currency: null },
          in_batch: { count: 0, amount: null, currency: null },
          exported: { count: 0, amount: null, currency: null },
          blocked: { count: 0, amount: null, currency: null },
        },
        items: [], page: 1, page_size: 10, total: 0, total_pages: 1,
        filters: { vendors: [], currencies: [], approvers: [] }, batch: null, recent_runs: [],
      } })
      return
    }
    if (pathname === '/evaluation/dashboard') {
      await route.fulfill({ json: {
        gates: { field_match: 0.95, validation_match: 0.95, regression_tolerance_pp: 1 },
        preflight: {
          dataset_id: 'invoice-scenarios', dataset_version: 'v1', dataset_label: 'Synthetic invoice scenarios',
          available_documents: 20, documents: 20, limited: false, provider_calls_estimate: 20,
          estimated_cost_usd: null, cost_note: 'No run selected.', runnable: false, provider: 'not configured',
        },
        runs: [], selected_run: null, trend: [], regression: null, fields: [],
        scenario_coverage: {
          dataset_id: 'invoice-scenarios', dataset_version: 'v1',
          claim_boundary: 'Synthetic evidence only.', included_in_selected_run: false, groups: [],
        },
        attempts: [],
      } })
      return
    }
    if (pathname === '/system/dashboard') {
      await route.fulfill({ json: {
        observed_at: observedAt,
        freshness: { state: 'current', label: 'Observed now' },
        overall: { status: 'operational', title: 'All observed services are operational', detail: 'No current service issue is stored.' },
        kpis: { processing_now: 0, waiting: 0, completed_today: 0, needs_attention: 0 },
        services: [], alerts: [],
        flow: { window_label: 'Today', denominator: 'Current records', stages: [] },
        recent_jobs: [], integrations: [], audit: [],
        maintenance: { scheduled: false, title: 'No maintenance scheduled', detail: 'The application has no stored maintenance window.' },
      } })
      return
    }

    await route.continue()
  })
}

function overviewFixture(role: TestRole) {
  return {
    observed_at: observedAt,
    actor: { name: role === 'administrator' ? 'E2E Administrator' : 'E2E Reviewer', role },
    briefing: {
      attention_count: 0,
      title: 'No invoices require attention right now',
      detail: 'New review work will appear here.',
      action_label: 'Open review queue',
      action_href: '/review-queue',
    },
    kpis: [
      { id: 'waiting_review', label: 'Waiting for review', count: 0, note: 'No pending decisions', tone: 'blue', href: '/review-queue' },
      { id: 'needs_correction', label: 'Needs correction', count: 0, note: 'No correction requests', tone: 'red', href: '/invoices?status=needs_correction' },
      { id: 'exceptions', label: 'Open exceptions', count: 0, note: 'No stored blockers', tone: 'orange', href: '/exceptions' },
      { id: 'approved', label: 'Approved', count: 0, note: 'No approved invoices', tone: 'teal', href: '/invoices?status=approved' },
    ],
    findings: [], alerts: [], queue: { total: 0, items: [] },
    throughput: {
      window_label: 'Last 7 days',
      series: [{ id: 'processed', label: 'Processed' }, { id: 'sent_for_review', label: 'Sent for review' }],
      points: [], method: 'Stored audit events.',
    },
    exception_breakdown: { total: 0, categories: [] },
    pipeline: { items: [], excluded_count: 0, note: 'Current invoice state.' },
    recent_decisions: [],
    capabilities: { export_access: role === 'administrator', due_policy: false, sla_policy: false, historical_issue_snapshots: false },
  }
}

test('administrator can navigate every implemented primary page without a reload', async ({ page }) => {
  await mockProductApi(page)
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: /Good .* E2E/i })).toBeVisible()

  for (const [link, heading] of [
    ['Invoices', 'Invoices'],
    ['Review Queue', 'Review Queue'],
    ['Exceptions', 'Exceptions'],
    ['Exports', 'Exports'],
    ['Evaluation', 'Evaluation'],
    ['System', 'System'],
  ] as const) {
    await clickPrimaryNavigation(page, link)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }

  await expect(page.getByRole('link', { name: 'Settings', exact: true })).toHaveCount(0)
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Evaluation', exact: true })).toBeVisible()
})

test('uploader lands on invoices and cannot enter reviewer or administrator areas', async ({ page }) => {
  await mockProductApi(page, { role: 'uploader' })
  await page.goto('/')
  await expect(page).toHaveURL(/\/invoices$/)
  await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload invoice', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Review Queue', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'System', exact: true })).toHaveCount(0)

  await page.goto('/exports')
  await expect(page).toHaveURL(/\/invoices$/)
})

test('reviewer sees review work but not upload, export, evaluation, or system controls', async ({ page }) => {
  await mockProductApi(page, { role: 'reviewer' })
  await page.goto('/invoices')
  await exposePrimaryNavigation(page)
  await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Upload invoice', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Review Queue', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Exports', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Evaluation', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'System', exact: true })).toHaveCount(0)
})

test('dashboard failure is explicit and recoverable', async ({ page }) => {
  await mockProductApi(page, { overviewFailure: true })
  await page.goto('/overview')
  await expect(page.getByRole('alert')).toContainText('Dashboard temporarily unavailable')
  await expect(page.getByRole('button', { name: 'Try again' })).toBeEnabled()
})

test('overview has no serious accessibility violations or page-level overflow', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockProductApi(page)
  await page.goto('/overview')
  await expect(page.getByRole('heading', { name: /Good .* E2E/i })).toBeVisible()
  await page.waitForTimeout(800)
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact ?? ''))).toEqual([])
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})

test('mobile navigation opens and closes without shifting the page', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'The off-canvas navigation is used only at the mobile breakpoint.')
  await mockProductApi(page)
  await page.goto('/overview')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Close navigation' }).click()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
