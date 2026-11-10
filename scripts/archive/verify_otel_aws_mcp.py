#!/usr/bin/env python3
"""Live anonymous MCP boundary check. Positive authentication belongs to SRE API."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def verify(url):
    target = urlsplit(url)
    if (
        target.scheme != "http"
        or target.hostname not in {"127.0.0.1", "localhost"}
        or target.path != "/mcp"
        or target.username
        or target.password
        or target.query
        or target.fragment
    ):
        raise ValueError("use the explicitly prepared loopback SSM MCP endpoint")
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "sre-618-boundary-e2e", "version": "1"},
        },
    }
    # No credentials, ambient proxy, private files or response payload inspection.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(
        url,
        json.dumps(initialize).encode(),
        {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    print(f"anonymous MCP initialize: HTTP{status}", flush=True)
    if status not in {401, 403}:
        raise ValueError("MCP authentication boundary absent/invalid; endpoint NOT accepted")
    print("ANONYMOUS DENIAL PASS; authenticated SRE queries and signal recovery NOT verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    try:
        verify(args.url)
    except (OSError, ValueError) as error:
        message = str(error) if isinstance(error, ValueError) else "transport unavailable"
        print("verification: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
