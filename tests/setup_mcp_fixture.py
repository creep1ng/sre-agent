"""Controlled MCP transport ONLY; not OTel, AWS, signal recovery or LLM evidence."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + os.environ["MCP_GRAFANA_SERVER_TOKEN"]:
            self.send_response(401)
            self.end_headers()
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request["method"] == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "serverInfo": {"name": "controlled-setup-fixture", "version": "1"},
            }
        elif request["method"] == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        else:
            tool = request["params"]["name"]
            payload = (
                {"resultType": "vector", "result": []}
                if tool == "query_prometheus"
                else {"total": 0, "documents": [], "warnings": []}
            )
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
