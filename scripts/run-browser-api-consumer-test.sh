#!/bin/sh
set -eu

cleanup() {
  docker rm --force "${BROWSER_API_NGINX_CONTAINER:-sre-agent-browser-api-nginx}" \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

: "${BROWSER_API_TEST_DATABASE_URL:?set an isolated PostgreSQL database URL}"
: "${DEMO_DATABASE_URL:?set the persistent demo database URL for the isolation guard}"

new_key() {
  printf 'sre_%s_%s' "$1" "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
}

export ADMIN_HUMAN_API_KEY="${ADMIN_HUMAN_API_KEY:-$(new_key admn)}"
export DEMO_HUMAN_API_KEY="${DEMO_HUMAN_API_KEY:-$(new_key demo)}"
export INCIDENT_HARNESS_API_KEY="${INCIDENT_HARNESS_API_KEY:-$(new_key inci)}"
export RESTRICTED_HARNESS_API_KEY="${RESTRICTED_HARNESS_API_KEY:-$(new_key rest)}"
export TRIAGE_AGENT_MODEL="${TRIAGE_AGENT_MODEL:-openai/gpt-4o-mini}"
export TRIAGE_AGENT_PROVIDER="${TRIAGE_AGENT_PROVIDER:-openai}"
export REMEDIATION_AGENT_MODEL="${REMEDIATION_AGENT_MODEL:-anthropic/claude-sonnet-4}"
export REMEDIATION_AGENT_PROVIDER="${REMEDIATION_AGENT_PROVIDER:-anthropic}"
export AUDIT_HMAC_KEY="${AUDIT_HMAC_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

npx playwright test --config=playwright.api.config.js
