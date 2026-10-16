from __future__ import annotations

from http.client import HTTPConnection, RemoteDisconnected
from http.server import ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import Mock, patch

from scripts import phase7_sandbox_bridge as bridge


class SandboxBridgeTests(unittest.TestCase):
    def setUp(self):
        bridge.COUNTS.update(create=0, submit=0, dropped_submit_responses=0)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Bridge)
        self.thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 1)
        self.addCleanup(self.server.shutdown)
        self.upstream = Mock()
        self.upstream.getresponse.return_value.status = 200
        self.upstream.getresponse.return_value.read.return_value = b'{"message":{"docstatus":1}}'
        self.patch = patch.object(bridge.http.client, "HTTPConnection", return_value=self.upstream)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def submit(self, bill):
        client = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(client.close)
        client.request(
            "POST", "/api/method/frappe.client.submit", json.dumps({"doc": {"bill_no": bill}})
        )
        response = client.getresponse()
        response.read()
        return response.status

    def test_non_release_write_never_reaches_erp(self):
        self.assertEqual(self.submit("CUSTOMER-INVOICE"), 403)
        self.upstream.request.assert_not_called()

    def test_response_loss_occurs_once_without_an_automatic_write_retry(self):
        with patch.dict("os.environ", {"DROP_SUBMIT_ONCE": "true"}):
            with self.assertRaises(RemoteDisconnected):
                self.submit("REL-UNIT")
            self.assertEqual(self.upstream.request.call_count, 1)
            self.assertEqual(self.submit("REL-UNIT"), 200)
        self.assertEqual(bridge.COUNTS["dropped_submit_responses"], 1)
        self.assertEqual(self.upstream.request.call_count, 2)
