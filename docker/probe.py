"""E2E target of the deploy-executor (#720): answers its own version on GET /."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"service": "probe", "version": os.environ["PROBE_VERSION"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
