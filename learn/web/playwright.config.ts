import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  workers: 4,
  timeout: 90_000,
  reporter: "list",
  use: { trace: "retain-on-failure", viewport: { width: 1500, height: 1000 } },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1500, height: 1000 } } }],
});
