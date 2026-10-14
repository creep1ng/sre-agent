import { defineConfig } from "@playwright/test";

// Docker lane for specs whose transport is intercepted by the spec itself
// (mocked HTTP seam, declared per spec): the browser is real, the API never
// receives a request. Base URL points at the composed web service; there is
// deliberately no local webServer here. Only the spec file passed on the
// command line runs, e.g. tests/browser/postmortem.spec.js.

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://web";

export default defineConfig({
  testDir: "tests/browser",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results/docker-browser",
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
