import { defineConfig, devices } from "@playwright/test";

// Browser smoke tests against the real stack (FastAPI + Next.js).
// CI starts both servers; locally, a stack that is already running on :8000 / :3000 is reused.
//   npx playwright install chromium   (once)
//   npm run test:e2e
const CI = !!process.env.CI;
const PYTHON = process.env.E2E_PYTHON || (process.platform === "win32" ? ".venv\\Scripts\\python" : "python");

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: CI ? 1 : 0,
  reporter: CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `${PYTHON} -m uvicorn app.main:app --port 8000`,
      cwd: "../backend",
      url: "http://localhost:8000/health/ready",
      reuseExistingServer: !CI,
      timeout: 300_000, // first boot trains the model when none exists
      // A separate database, so test runs never add rows to the development database.
      env: { LLM_PROVIDER: "none", CORS_ORIGINS: "http://localhost:3000", DATABASE_URL: "sqlite:///data/e2e.db" },
    },
    {
      command: CI ? "npm run start -- -p 3000" : "npm run dev -- -p 3000",
      url: "http://localhost:3000",
      reuseExistingServer: !CI,
      timeout: 120_000,
    },
  ],
});
