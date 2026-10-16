import { readFileSync, writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const fixturePath = process.env.RELEASE_FIXTURE
const statePath = process.env.RELEASE_STATE
const stage = process.env.RELEASE_TEST_STAGE ?? 'submit'
test.skip(!fixturePath || !statePath, 'An isolated provisioned release fixture is required.')

async function login(page: Page, role: string) {
  await page.goto('/')
  const signOut = page.getByRole('button', { name: 'Sign out' })
  if (await signOut.isVisible()) await signOut.click()
  await page.getByLabel('Role token').fill(`release-${role}`)
  await page.getByRole('button', { name: 'Open workspace' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

async function call(page: Page, path: string, payload: unknown, token: string, method = 'POST') {
  const response = await page.request.fetch(path, {
    method,
    data: payload,
    headers: { 'X-Access-Token': `release-${token}` },
  })
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true)
  return response.json()
}

test('Docker browser intake, correction, AP approval and unknown submit', async ({ page }) => {
  test.skip(stage !== 'submit')
  const fixture = JSON.parse(readFileSync(fixturePath!, 'utf8'))
  await login(page, 'uploader')
  await page.goto('/invoices')
  await page.getByRole('button', { name: 'Upload invoice' }).click()
  const dialog = page.getByRole('dialog', { name: 'Upload invoice' })
  const uploaded = page.waitForResponse(
    (r) => r.url().endsWith('/documents/upload') && r.request().method() === 'POST',
  )
  await dialog.locator('input[type="file"]').setInputFiles(fixture.pdf)
  await dialog.getByRole('button', { name: 'Upload invoice' }).click()
  const documentId = (await (await uploaded).json()).document.id as string
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/documents/${documentId}`, {
          headers: { 'X-Access-Token': 'release-admin' },
        })
        return Boolean((await response.json()).extraction)
      },
      { timeout: 60_000 },
    )
    .toBe(true)
  await login(page, 'reviewer')
  // Broad regression deliberately uses mock extraction plus a controlled reviewer
  // error. It does not score these fixture corrections as AI extraction accuracy.
  await call(
    page,
    `/review/${documentId}/save`,
    {
      corrected_data: { ...fixture.invoice, total: '101.00' },
      notes: 'Deliberate synthetic total error for browser correction',
    },
    'reviewer',
  )
  await login(page, 'reviewer')
  await page.goto(`/review/${documentId}`)
  await expect(page.getByText('Approval blocked', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Edit Total amount', exact: true }).click()
  await page.locator('.review-field-editor input').fill('100.00')
  await page.getByRole('button', { name: 'Save Total amount', exact: true }).click()
  await expect(page.getByText('Ready for decision', { exact: true }).first()).toBeVisible()
  const revision = await call(page, `/ap/invoices/${documentId}/capture`, {}, 'reviewer')
  const fields = Object.fromEntries(
    Object.entries(revision.fields)
      .filter(([, value]) => (value as { effective: unknown }).effective !== null)
      .map(([path, value]) => {
        const effective = (value as { effective: unknown }).effective
        return [
          path,
          {
            kind: 'corrected',
            raw: String(effective),
            effective,
            page: 1,
            excerpt: String(effective),
            reason: 'Verified against the authored synthetic PDF',
          },
        ]
      }),
  )
  await call(
    page,
    `/ap/invoices/${documentId}/evidence`,
    {
      expected_revision: revision.version,
      fields,
      reason: 'Verify printed release fixture fields',
    },
    'reviewer',
    'PUT',
  )
  await page.reload()
  await page.getByText('Prepare purchasing evidence review', { exact: true }).click()
  await page.getByLabel('Company', { exact: true }).fill(fixture.company)
  await page.getByLabel('Source system', { exact: true }).fill('erpnext')
  await page.getByLabel('PO identifiers (comma separated)').fill(fixture.sources[0].source_id)
  await page.getByLabel('Receipt identifiers (comma separated)').fill(fixture.sources[1].source_id)
  await page
    .getByLabel('Line 1: PO identifier and line identifier, separated by a colon')
    .fill(`${fixture.sources[0].source_id}:${fixture.sources[0].lines[0].source_line_id}`)
  await page.getByRole('button', { name: 'Prepare evidence snapshot' }).click()
  await expect(
    page.getByRole('heading', { name: 'Purchasing evidence: awaiting_approval' }),
  ).toBeVisible()
  await login(page, 'approver')
  await page.goto(`/review/${documentId}`)
  await page.getByRole('button', { name: 'Approve this evidence snapshot' }).click()
  await page.getByRole('button', { name: 'Assess three-way match' }).click()
  await page.getByRole('button', { name: 'Approve match and reserve quantity' }).click()
  const created = page.waitForResponse(
    (r) => r.url().endsWith('/draft') && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Create and verify ERP draft' }).click()
  expect((await (await created).json()).state).toBe('confirmed')
  await page
    .getByLabel('Independent submit approval reason')
    .fill('Checked release source, PO, receipt and verified ERP draft')
  await page.getByRole('button', { name: 'Approve ERP submit separately' }).click()
  await page.getByRole('button', { name: 'Submit approved ERP draft' }).click()
  await expect(page.getByRole('button', { name: 'Reconcile submit outcome' })).toBeVisible()
  await expect(page.getByText('Posted and verified against ERP document and ledger')).toHaveCount(0)
  const evidence = await page.request.get(`/ap/invoices/${documentId}`, {
    headers: { 'X-Access-Token': 'release-admin' },
  })
  const matchId = (await evidence.json()).match_status.match.id
  const status = await page.request.get(`/ap/posting/${matchId}`, {
    headers: { 'X-Access-Token': 'release-admin' },
  })
  const posting = await status.json()
  expect(posting.submit.state).toBe('unknown')
  writeFileSync(
    statePath!,
    JSON.stringify(
      {
        document_id: documentId,
        match_id: matchId,
        target: posting.submit.target,
        approval_hash: posting.submit_approval.approval_hash,
        unknown_observed: true,
      },
      null,
      2,
    ),
  )
})

test('rollback keeps unknown state and permits read-only reconciliation', async ({ page }) => {
  test.skip(stage !== 'reconcile')
  const state = JSON.parse(readFileSync(statePath!, 'utf8'))
  await login(page, 'approver')
  await page.goto(`/review/${state.document_id}`)
  await expect(page.getByText('Sandbox posting is disabled in configuration.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Submit approved ERP draft' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Reconcile submit outcome' }).click()
  await expect(page.getByText('Posted and verified against ERP document and ledger')).toBeVisible()
  await page.screenshot({
    path: process.env.RELEASE_SCREENSHOT ?? 'test-results/release-posted.png',
    fullPage: true,
  })
  state.reconciled_while_writes_disabled = true
  writeFileSync(statePath!, JSON.stringify(state, null, 2))
})

test('current image retains verified history after another restart', async ({ page }) => {
  test.skip(stage !== 'inspect')
  const state = JSON.parse(readFileSync(statePath!, 'utf8'))
  await page.setViewportSize({ width: 1536, height: 1024 })
  await login(page, 'approver')
  await page.goto(`/review/${state.document_id}`)
  await expect(page.getByText('Posted and verified against ERP document and ledger')).toBeVisible()
  await expect(page.getByText(/Submit issue:/)).toHaveCount(0)
  const response = await page.request.get(`/ap/posting/${state.match_id}`)
  const status = await response.json()
  expect(status.posted_verified).toBe(true)
  expect(status.submit.target).toBe(state.target)
  await page
    .getByRole('heading', { name: 'ERPNext sandbox delivery' })
    .locator('..')
    .screenshot({
      path: process.env.RELEASE_SCREENSHOT ?? 'test-results/release-posted-panel.png',
    })
})
