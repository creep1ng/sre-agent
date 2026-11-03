import type { Messages } from "@/i18n";
import type admin from "../es/admin";

export default {
  "nav.identities": "Identities",
  "nav.permissions": "Permissions",
  "nav.resources": "Models and resources",
  "nav.consumption": "Consumption",
  "nav.audit": "Audit",

  "common.refresh": "Refresh",
  "common.cancel": "Cancel",
  "common.close": "Close",
  "common.loading": "Loading…",
  "common.notConfigured": "Not configured",
  "common.unavailable": "Unavailable",
  "common.truncated": "The list is truncated: more items exist.",
  "common.count": "{count} in total",
  "common.retry": "Retry",

  "status.active": "Active",
  "status.inactive": "Inactive",
  "status.revoked": "Revoked",
  "status.expired": "Expired",
  "status.unknown": "Unknown",
  "kind.human": "Person",
  "kind.agent": "Agent",

  "gate.title": "Connect an administrative key to see this section.",
  "gate.action": "Connect to the API",

  "error.network": "The API could not be reached.",
  "error.network.detail": "Check that the stack is up and try again.",
  "error.auth": "The key is not valid.",
  "error.auth.detail": "Connect another API key. Nothing else was confirmed.",
  "error.forbidden": "This key has no access.",
  "error.forbidden.detail": "The connected identity cannot see or change this. Nothing else is revealed.",
  "error.missing": "It does not exist or is not visible.",
  "error.missing.detail": "Reload the list.",
  "error.conflict": "Someone changed it before you.",
  "error.conflict.detail": "The current version is shown; nothing was overwritten.",
  "error.invalid": "The API rejected the data.",
  "error.invalid.detail": "Check the fields. Nothing changed.",
  "error.too_large": "The scope is too large.",
  "error.too_large.detail": "Narrow the filter and query again.",
  "error.unavailable": "The API did not answer as expected.",
  "error.unavailable.detail": "No empty result is substituted. Try again.",

  "type.llm_model": "LLM model",
  "type.mcp_server": "MCP server",
  "type.mcp_tool": "MCP tool",
  "type.skill": "Skill",
  "type.bok_collection": "BoK collection",
  "type.incident_workflow": "Workflow",
  "type.service_operation": "Service operation",
  "type.administrative_control": "Administrative control",

} satisfies Messages<typeof admin>;
