import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const frontendRoot = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(frontendRoot, '..')
const runRoot =
  process.env.FULLSTACK_RUN_ROOT ??
  path.join(frontendRoot, 'test-results', `fullstack-${process.pid}-${Date.now()}`)
const python =
  process.env.E2E_PYTHON ??
  (process.platform === 'win32' ? path.join(repoRoot, '.venv', 'Scripts', 'python.exe') : 'python')

mkdirSync(runRoot, { recursive: true })

const backendEnvironment = {
  ENV_FILE: path.join(runRoot, '.missing-env'),
  PYTHONPATH: path.join(repoRoot, 'backend'),
  APP_ENV: 'test',
  APP_ADMIN_TOKEN: 'admin-e2e-token',
  APP_UPLOADER_TOKEN: 'uploader-e2e-token',
  APP_REVIEWER_TOKEN: 'reviewer-e2e-token',
  APP_METRICS_TOKEN: 'metrics-e2e-token',
  APP_WORKSPACE_ID: 'fullstack-e2e',
  STORAGE_BACKEND: 'sqlite',
  SQLITE_PATH: path.join(runRoot, 'invoice-review.sqlite3'),
  UPLOAD_ROOT: path.join(runRoot, 'uploads'),
  PARSER_PROVIDER: 'mock',
  EXTRACTOR_PROVIDER: 'mock',
  MALWARE_SCANNING_ENABLED: 'false',
  WORKER_POLL_SECONDS: '0.1',
}

Object.assign(process.env, backendEnvironment, {
  FULLSTACK_PYTHON: python,
  FULLSTACK_REPO_ROOT: repoRoot,
  FULLSTACK_RUN_ROOT: runRoot,
})

const pythonCommand = /\s/.test(python) ? `"${python}"` : python

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/fullstack.spec.ts',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-fullstack' }]],
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: repoRoot,
      env: backendEnvironment,
      url: 'http://127.0.0.1:8000/ready',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 4174',
      cwd: frontendRoot,
      url: 'http://127.0.0.1:4174',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: 'fullstack-chromium',
      use: { ...devices['Desktop Chrome'], browserName: 'chromium' },
    },
  ],
})
