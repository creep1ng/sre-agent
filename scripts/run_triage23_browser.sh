#!/bin/sh
set -eu

for name in E2E_TRIAGE_API_KEY E2E_NOGRANT_API_KEY E2E_OP_NOREAD_API_KEY \
  E2E_TRIAGE_READONLY_API_KEY E2E_EXTERNAL_API_KEY E2E_EXTERNAL_NOGRANT_API_KEY \
  E2E_TRIAGE_LEGACY_ALERT_ID T23_18_ARTIFACT_DIR; do
  value="$(printenv "$name" || true)"
  test -n "$value" || { echo "Missing required fixture variable: $name" >&2; exit 2; }
done
npx playwright test --config=playwright.production.config.js --workers=1 --reporter=json \
  > /artifacts/playwright.json
node -e 'const r=JSON.parse(require("fs").readFileSync("/artifacts/playwright.json")); const s=r.stats; console.log("passed="+s.expected+" skipped="+s.skipped+" failed="+s.unexpected+" flaky="+s.flaky); if(s.expected!==54||s.skipped!==0||s.unexpected!==0||s.flaky!==0) process.exit(1)'
