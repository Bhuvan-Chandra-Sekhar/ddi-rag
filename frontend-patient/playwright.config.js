import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.E2E_PORT || 5057);

// The Flask launcher runs under the repo's virtualenv when there is one,
// otherwise whatever `python` is on PATH (CI installs requirements into it).
const candidates = [
  process.env.E2E_PYTHON,
  path.resolve(here, '../venv/Scripts/python.exe'),
  path.resolve(here, '../venv/bin/python'),
].filter(Boolean);
const python = candidates.find((candidate) => fs.existsSync(candidate)) || 'python';

// These tests run the real built bundle (ddi_rag/static/patient-app), served
// by the real Flask app, against an isolated seeded database. `npm run e2e`
// rebuilds the bundle first so they always exercise the current source.
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  // One shared database and global switches (kill switch, explanation
  // outage), so specs run one at a time.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  timeout: 30_000,
  expect: { timeout: 7_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `"${python}" e2e/serve_test_app.py`,
    cwd: here,
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: { E2E_PORT: String(PORT) },
    // Always a fresh, freshly seeded server: leftover state from an earlier
    // run is exactly the kind of thing these tests must not depend on.
    reuseExistingServer: false,
    timeout: 90_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] }, testIgnore: /responsive\.spec\.js/ },
    {
      name: 'mobile',
      use: { ...devices['Pixel 7'] },
      testMatch: [/responsive\.spec\.js/, /a11y\.spec\.js/],
    },
  ],
});
