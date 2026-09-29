const { defineConfig } = require('/e2e/node_modules/@playwright/test');
module.exports = defineConfig({
  testDir: '/out', testMatch: 'extra-ui.spec.js', outputDir: '/out/extra-results', reporter: 'line', workers: 1,
  use: { baseURL: 'http://127.0.0.1:4173', browserName: 'chromium', screenshot: 'on' },
  webServer: { command: 'python3 -m http.server 4173 --bind 127.0.0.1', cwd: '/repo', port: 4173, reuseExistingServer: false },
});
