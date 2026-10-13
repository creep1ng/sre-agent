"""Full published-schema validation shared only by issue-30 observers."""

import json
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


def contract_validator(version="2.7.0"):
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), "invalid contract release"
    directory = Path("/candidate/schemas/releases") / version / "json-schema"
    schemas = [json.loads(p.read_text()) for p in directory.rglob("*.json")]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    schema = next(s for s in schemas if s["$id"] == f"urn:sre-agent:schema:audit-event:{version}")
    return Draft202012Validator(
        schema, registry=registry, format_checker=FormatChecker()
    ), directory


def canonical_event(row, required):
    # Only top-level optional SQL NULL means absence; JSONB values stay exact.
    return {k: v for k, v in row.items() if v is not None or k in required}


def authentication_event_valid(event, validator, request_id, start, end):
    return validator.is_valid(event) and (
        event["stage"] == "authentication"
        and event["response_status"] == 401
        and event["reason_code"] == "authentication_failed"
        and event["outcome"] == "error"
        and event["correlation"]["request_id"] == request_id
        and (event["operation"], event["action"])
        in {("mcp.invoke", "invoke"), ("credentials.authenticate", "authenticate")}
        # This random unknown credential can yield a credential HMAC, not a Principal.
        and set(event.get("identity", {})) <= {"credential_ref"}
        and "redacted_content" not in event
        and "untrusted_input" not in event
        and datetime.fromisoformat(start)
        <= datetime.fromisoformat(event["occurred_at"])
        < datetime.fromisoformat(end)
    )
