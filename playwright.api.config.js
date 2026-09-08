import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/browser",
  testMatch: "api-seam.spec.js",
  outputDir: "test-results/browser-api",
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
  webServer: [
    {
      command: "python scripts/browser_api_test_server.py",
      port: 4174,
      reuseExistingServer: false,
    },
    {
      command: "scripts/browser-api-nginx-server.sh",
      port: 4173,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
