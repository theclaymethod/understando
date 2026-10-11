import { defineConfig, devices } from "@playwright/test";
import { mkdirSync, mkdtempSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// The test isolation (tests/isolate.sh, scripts/testguard.py): the guard marker, a temp root, and the
// temp folder in the root. learn/e2e.sh sets them; a direct `npx playwright test` gets its own root.
// The main process sets them before the workers start, and the workers inherit them.
if (!process.env.UNDERSTANDO_TEST_ROOT) process.env.UNDERSTANDO_TEST_ROOT = realpathSync(mkdtempSync(join(tmpdir(), "understando-test-")));
process.env.UNDERSTANDO_TEST = "1";
process.env.PYTHONDONTWRITEBYTECODE = "1";
mkdirSync(join(process.env.UNDERSTANDO_TEST_ROOT, "tmp"), { recursive: true });
process.env.TMPDIR = join(process.env.UNDERSTANDO_TEST_ROOT, "tmp");

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  workers: 4,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: "list",
  use: { trace: "retain-on-failure", viewport: { width: 1500, height: 1000 } },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1500, height: 1000 } } }],
});
