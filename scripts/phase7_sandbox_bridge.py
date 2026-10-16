"""Loopback-only Docker bridge to the existing local ERPNext sandbox.

The optional fault drops one successful synthetic submit response. It never
retries a write. No credentials or request/response bodies are logged.
"""

from __future__ import annotations

import http.client
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

COUNTS = {"create": 0, "submit": 0, "dropped_submit_responses": 0}
LOCK = Lock()


class Bridge(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/__release__/fault-status":
            data = json.dumps(COUNTS).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)
            return
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        submit = self.command == "POST" and self.path == "/api/method/frappe.client.submit"
        create = self.command == "POST" and self.path == "/api/resource/Purchase%20Invoice"
        if self.command == "POST":
            if not (submit or create):
                self.send_error(403)
                return
            payload = json.loads(body or b"{}")
            invoice = payload.get("doc", {}) if submit else payload
            if isinstance(invoice, str):
                invoice = json.loads(invoice)
            if not str(invoice.get("bill_no", "")).startswith("REL-"):
                self.send_error(403, "Only release synthetic invoices are permitted")
                return
        connection = http.client.HTTPConnection("host.docker.internal", 8080, timeout=60)
        try:
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "content-length"}
            }
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            with LOCK:
                if create:
                    COUNTS["create"] += 1
                if submit:
                    COUNTS["submit"] += 1
                drop = (
                    submit
                    and response.status == 200
                    and os.getenv("DROP_SUBMIT_ONCE") == "true"
                    and not COUNTS["dropped_submit_responses"]
                )
                if drop:
                    COUNTS["dropped_submit_responses"] += 1
            if drop:
                print(
                    json.dumps(
                        {"event": "synthetic_submit_response_dropped", "remote_status": 200}
                    ),
                    flush=True,
                )
                self.close_connection = True
                return
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18080), Bridge).serve_forever()
