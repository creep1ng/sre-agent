#!/usr/bin/env python3
"""Emit sanitized controlled HTTP + PostgreSQL evidence for issue #25."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

ROOT = "/app"


class Provider:
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def create(self, request):
        from sre_agent.gateway.providers import ProviderFailure, ProviderResult

        if self.fail:
            raise ProviderFailure("unavailable")
        return ProviderResult(
            response_id="resp_issue25controlled",
            model=request.model,
            text="ISSUE25_PRIVATE_OUTPUT_" + request.input.rsplit("_", 1)[-1],
            provider=request.provider,
        )


class FailingAuditStore:
    async def append(self, _event):
        raise RuntimeError("controlled audit failure")


def require_safe_settings():
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENROUTER")}
    from sre_agent.settings import Settings

    settings = Settings.from_environment(env)
    parsed = urlsplit(settings.database_url)
    if parsed.hostname != "db" or unquote(parsed.path.lstrip("/")) != "sre_agent":
        raise RuntimeError("refusing non-isolated database target")
    for name in ("ADMIN_HUMAN_API_KEY", "RESTRICTED_HARNESS_API_KEY"):
        if not env.get(name):
            raise RuntimeError("required synthetic seed key missing")
    if not settings.audit_hmac_key:
        raise RuntimeError("audit HMAC setting missing")
    return settings, env


def headers(key):
    return {"Authorization": "Bearer " + key}


def persisted(request_id):
    from sre_agent.settings import Settings

    dsn = Settings.from_environment(
        {k: v for k, v in os.environ.items() if not k.startswith("OPENROUTER")}
    ).database_url
    with psycopg.connect(dsn) as connection:
        return connection.execute(
            "SELECT event_id::text,response_status,latency_ms FROM audit_events "
            "WHERE operation='responses.create' AND correlation->>'request_id'=%s",
            (request_id,),
        ).fetchall()


def audit_projection(client, admin, request_id, marker):
    listed = client.get("/v1/audit-events", params={"request_id": request_id}, headers=admin)
    if listed.status_code != 200 or len(listed.json().get("items", [])) != 1:
        raise RuntimeError("filtered audit list mismatch")
    item = listed.json()["items"][0]
    detail = client.get("/v1/audit-events/" + item["event_id"], headers=admin)
    if detail.status_code != 200 or detail.json() != item:
        raise RuntimeError("audit detail mismatch")
    if (
        marker in listed.text + detail.text
        or "ISSUE25_PRIVATE_OUTPUT_" in listed.text + detail.text
    ):
        raise RuntimeError("content marker escaped projection")
    if "redacted_content" in item or item.get("content_state") != "absent":
        raise RuntimeError("audit projection content invariant mismatch")
    return listed, detail, item


def main():
    sys.path.insert(0, ROOT + "/src")
    settings, env = require_safe_settings()
    from sre_agent.application import create_application

    admin = headers(env["ADMIN_HUMAN_API_KEY"])
    cases = []
    provider = Provider()
    with TestClient(create_application(settings, llm_provider=provider)) as client:
        scenarios = (
            ("allow", env.get("INCIDENT_HARNESS_API_KEY"), {}, 200),
            ("deny", env["RESTRICTED_HARNESS_API_KEY"], {}, 403),
            ("auth401", None, {}, 401),
            ("invalid422", env.get("INCIDENT_HARNESS_API_KEY"), {"input": ""}, 422),
            ("provider503", env.get("INCIDENT_HARNESS_API_KEY"), {}, 503),
        )
        for name, key, override, expected in scenarios:
            provider.fail = name == "provider503"
            marker = "ISSUE25_PRIVATE_PROMPT_" + uuid4().hex
            body = {"model": "triage-agent", "input": marker, **override}
            response = client.post("/v1/responses", headers=headers(key) if key else {}, json=body)
            if response.status_code != expected:
                raise RuntimeError("producer status mismatch: " + name)
            request_id = response.json().get("request_id")
            rows = persisted(request_id)
            if len(rows) != 1 or rows[0][1] != expected or rows[0][2] < 0:
                raise RuntimeError("producer SQL evidence mismatch: " + name)
            listed, detail, item = audit_projection(client, admin, request_id, marker)
            if (
                item.get("event_id") != rows[0][0]
                or item.get("correlation", {}).get("request_id") != request_id
                or item.get("response_status") != rows[0][1]
                or item.get("latency_ms") != rows[0][2]
            ):
                raise RuntimeError("HTTP/SQL correspondence mismatch: " + name)
            cases.append(
                {
                    "name": name,
                    "request_id": request_id,
                    "producer_status": expected,
                    "list_status": listed.status_code,
                    "detail_status": detail.status_code,
                    "items": [item],
                    "sql": {
                        "count": len(rows),
                        "event_id": rows[0][0],
                        "response_status": rows[0][1],
                        "latency_ms": rows[0][2],
                    },
                }
            )

        marker = "ISSUE25_PRIVATE_PROMPT_" + uuid4().hex
        fail_app = create_application(
            settings, llm_provider=Provider(), audit_store=FailingAuditStore()
        )
        with TestClient(fail_app) as failing_client:
            ca6 = failing_client.post(
                "/v1/responses",
                headers=headers(env["INCIDENT_HARNESS_API_KEY"]),
                json={"model": "triage-agent", "input": marker},
            )
        ca6_id = ca6.json()["request_id"]
        ca6_rows = persisted(ca6_id)
        ca6_list = client.get("/v1/audit-events", params={"request_id": ca6_id}, headers=admin)
        if (
            ca6.status_code != 503
            or ca6_rows
            or ca6_list.status_code != 200
            or ca6_list.json()["items"]
        ):
            raise RuntimeError("CA6 fail-closed persistence mismatch")
        cases.append(
            {
                "name": "auditStoreFailure",
                "request_id": ca6_id,
                "producer_status": ca6.status_code,
                "list_status": ca6_list.status_code,
                "items": [],
                "sql": {"count": len(ca6_rows)},
            }
        )

        probe = str(uuid4())
        selector = {"request_id": probe}
        read_cases = (
            ("unauth", selector, {}, 401),
            ("nonadmin", selector, headers(env["RESTRICTED_HARNESS_API_KEY"]), 403),
            ("missingFilter", {}, admin, 422),
            ("contentFilter", {**selector, "content": "1"}, admin, 422),
            ("emptyQuery", selector, admin, 200),
        )
        read_controls = []
        for name, params, auth, expected in read_cases:
            read_response = client.get("/v1/audit-events", params=params, headers=auth)
            read_controls.append(
                {"name": name, "status": read_response.status_code, "sql_count": 0}
            )
            if read_response.status_code != expected:
                raise RuntimeError("audit read control mismatch: " + name)
            if name in ("unauth", "nonadmin") and "items" in read_response.json():
                raise RuntimeError("unauthorized audit response exposed a list")
            if name == "emptyQuery" and read_response.json().get("items") != []:
                raise RuntimeError("valid empty query returned items")
            if name in ("unauth", "nonadmin") and probe in read_response.text:
                raise RuntimeError("unauthorized audit response exposed the filter")
        if persisted(probe):
            raise RuntimeError("read-control probe unexpectedly has a producer row")
        print(
            json.dumps(
                {
                    "evidence_kind": "controlled integration",
                    "captured_at": datetime.now(UTC).isoformat(),
                    "cases": cases,
                    "read_controls": read_controls,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "issue25 audit evidence capture failed; no sensitive details emitted",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
