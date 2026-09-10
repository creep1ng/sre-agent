import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://web";

export default defineConfig({
  testDir: "tests/browser",
  testMatch: ["api-seam.spec.js", "production-proxy.spec.js", "principals.spec.js"],
  outputDir: "test-results/production-browser",
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
});
