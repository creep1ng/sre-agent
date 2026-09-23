# 2.4.0 consumer migration

Release 2.4.0 is an additive `/v1` contract over immutable 2.3.0. It adds the `mcp.discovery` and `mcp.invoke` audit operations while preserving every existing 2.3.0 operation and consumer obligation. MCP discovery evidence binds only to an HMAC-referenced `mcp_server`; MCP invocation evidence binds only to an HMAC-referenced `mcp_tool`. MCP audit events carry no model-alias or routing evidence and do not require LLM consumption metadata.

MCP audit records remain metadata-only: raw credentials, arguments, results, and response content are not part of the event. The metadata schema excludes redacted content. Consumers inherit all existing 2.3.0 obligations, with an additional issue-187 conformance check for both MCP audit operations and their subject mapping.

Publishing this contract does not activate runtime contract version 2.4.0. Runtime activation belongs with integration of the MCP runtime that emits and validates these events; the existing runtime default remains unchanged in this release-contract work unit.
