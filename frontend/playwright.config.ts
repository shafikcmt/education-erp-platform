import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against the full docker compose stack through Nginx (single origin). Before the
 * run, create the bootstrap admin: `docker compose exec -T api python manage.py
 * create_platform_admin --email e2e-admin@example.test` (fresh volumes; see Makefile `e2e`).
 * PLAYWRIGHT_CHROMIUM_EXECUTABLE lets environments with a preinstalled Chromium reuse it.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:8080";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    // Activates the bootstrap Super Admin (created by `manage.py create_platform_admin`) once.
    { name: "setup", testMatch: /bootstrap\.setup\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] }, dependencies: ["setup"] },
  ],
});
