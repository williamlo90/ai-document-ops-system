import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const tokens = {
  uploader: 'uploader-e2e-token',
  reviewer: 'reviewer-e2e-token',
  admin: 'admin-e2e-token',
}

test('real stack processes, corrects, approves, and exports a duplicate invoice', async ({
  page,
}) => {
  await login(page, tokens.uploader, 'Invoices')
  await uploadInvoice(page)
  runWorker()
  await uploadInvoice(page)
  runWorker()

  await expect
    .poll(async () => Boolean(await findBlockedInvoice(page)), {
      message: 'worker should persist a duplicate blocker',
    })
    .toBe(true)
  const blockedInvoice = await findBlockedInvoice(page)
  if (!blockedInvoice) throw new Error('Duplicate blocker disappeared before review.')
  const documentId = blockedInvoice.id
  const originalInvoiceNumber = blockedInvoice.invoice_number ?? 'INV-001'
  const correctedInvoiceNumber = `${originalInvoiceNumber}-CORRECTED`

  await logout(page)
  await login(page, tokens.reviewer, 'Inbox')
  await page.goto(`/review/${documentId}`)
  await expect(page.getByRole('heading', { name: 'Review invoice' })).toBeVisible()
  await expect(page.getByText('Approval blocked', { exact: true }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Edit Invoice number' }).click()
  const invoiceNumberEditor = page.locator('.review-field-editor input')
  await invoiceNumberEditor.fill(correctedInvoiceNumber)
  await page.getByRole('button', { name: 'Save Invoice number' }).click()
  await expect(page.getByText('Ready for decision', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('No validation blockers were found.')).toBeVisible()

  await page.getByRole('button', { name: 'Open decision panel' }).click()
  const decisionPanel = page.getByRole('dialog', { name: 'Reviewer decision' })
  await expect(decisionPanel).toBeVisible()
  await decisionPanel.getByRole('button', { name: 'Approve' }).click()
  const approveDialog = page.getByRole('dialog', { name: 'Approve invoice?' })
  await approveDialog.getByRole('button', { name: 'Approve' }).click()
  await expect(decisionPanel.getByText('Decision recorded')).toBeVisible()
  await decisionPanel.getByRole('button', { name: 'Close decision panel' }).click()

  await logout(page)
  await login(page, tokens.admin, 'Inbox')
  await page.goto('/exports?status=ready')
  await page.getByRole('checkbox', { name: `Select ${correctedInvoiceNumber}` }).check()
  await page.getByRole('button', { name: 'Add to export' }).click()

  const batchPanel = page.getByRole('dialog', { name: 'Export batch' })
  await expect(batchPanel).toBeVisible()
  await batchPanel.getByRole('button', { name: 'Create export' }).click()
  const exportDialog = page.getByRole('dialog', { name: 'Create export' })
  await exportDialog.getByRole('button', { name: 'Create export' }).click()
  await expect(page.getByText('1 invoices exported successfully.')).toBeVisible()

  const exported = await fetchInvoices(page)
  const completed = exported.items.find((item) => item.id === documentId)
  expect(completed?.business_status).toBe('exported')
})

async function login(page: Page, token: string, expectedHeading: string) {
  await page.goto('/')
  await page.getByLabel('Role token').fill(token)
  await page.getByRole('button', { name: 'Open workspace' }).click()
  await expect(
    page.getByRole('heading', { name: expectedHeading, exact: true }).first(),
  ).toBeVisible()
}

async function logout(page: Page) {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Open demo workspace' })).toBeVisible()
}

async function uploadInvoice(page: Page) {
  await page.goto('/invoices')
  await page.getByRole('button', { name: 'Upload invoice' }).click()
  const dialog = page.getByRole('dialog', { name: 'Upload invoice' })
  const invoicePath = path.resolve(
    process.env.FULLSTACK_REPO_ROOT!,
    'examples',
    'benchmark',
    'datasets',
    'invoice_scenarios_v1',
    'documents',
    'duplicate_original.pdf',
  )
  await dialog.locator('input[type="file"]').setInputFiles(invoicePath)
  await dialog.getByRole('button', { name: 'Upload invoice' }).click()
  await expect(dialog).toHaveCount(0)
}

function runWorker() {
  try {
    execFileSync(process.env.FULLSTACK_PYTHON!, ['-m', 'app.worker'], {
      cwd: process.env.FULLSTACK_REPO_ROOT,
      env: process.env,
      stdio: 'pipe',
    })
  } catch (error) {
    const failure = error as { stdout?: Buffer; stderr?: Buffer; message: string }
    throw new Error(
      [failure.message, failure.stdout?.toString().trim(), failure.stderr?.toString().trim()]
        .filter(Boolean)
        .join('\n'),
    )
  }
}

async function findBlockedInvoice(page: Page) {
  const invoices = await fetchInvoices(page)
  return invoices.items.find((item) => item.has_validation_errors) ?? null
}

async function fetchInvoices(page: Page): Promise<InvoiceList> {
  return page.evaluate(async () => {
    const response = await fetch('/invoices?page=1&page_size=100', {
      credentials: 'same-origin',
    })
    if (!response.ok) throw new Error(`Invoice API returned ${response.status}`)
    return response.json()
  })
}

type InvoiceList = {
  items: Array<{
    id: string
    invoice_number: string | null
    business_status: string
    has_validation_errors: boolean
  }>
}
