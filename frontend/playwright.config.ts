import { defineConfig, devices } from "@playwright/test";

/**
 * E2E smoke tests run against the full docker compose stack through Nginx (single origin).
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
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
