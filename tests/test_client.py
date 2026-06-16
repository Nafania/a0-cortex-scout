import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from usr.plugins.cortex_scout.helpers.client import CortexScoutClient, CortexScoutError
except ModuleNotFoundError:
    from helpers.client import CortexScoutClient, CortexScoutError


class FakeScoutHandler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "healthy", "service": "cortex-scout"})
            return
        if self.path == "/mcp/tools":
            self._json(200, {"tools": [{"name": "web_fetch"}]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body) if body else {}
        self.requests.append((self.path, payload))
        if self.path == "/mcp/call" and payload.get("name") == "large":
            self._json(
                200,
                {
                    "content": [{"type": "text", "text": "x" * 200}],
                    "isError": False,
                },
            )
            return
        if self.path == "/mcp/call":
            self._json(
                200,
                {
                    "content": [{"type": "text", "text": "fetch ok"}],
                    "isError": False,
                },
            )
            return
        self._json(404, {"error": "not found"})

    def log_message(self, *_args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CortexScoutClientTests(unittest.TestCase):
    def setUp(self):
        FakeScoutHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeScoutHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_reads_health_endpoint(self):
        client = CortexScoutClient(self.base_url, timeout_seconds=2)
        self.assertEqual(client.health()["status"], "healthy")

    def test_list_tools_reads_mcp_tools_endpoint(self):
        client = CortexScoutClient(self.base_url, timeout_seconds=2)
        self.assertEqual(client.list_tools()["tools"][0]["name"], "web_fetch")

    def test_call_tool_posts_mcp_call_payload(self):
        client = CortexScoutClient(self.base_url, timeout_seconds=2)
        result = client.call_tool("web_fetch", {"url": "https://example.com"})

        self.assertEqual(result["content"][0]["text"], "fetch ok")
        self.assertEqual(
            FakeScoutHandler.requests,
            [
                (
                    "/mcp/call",
                    {
                        "name": "web_fetch",
                        "arguments": {"url": "https://example.com"},
                    },
                )
            ],
        )

    def test_http_errors_raise_cortex_scout_error(self):
        client = CortexScoutClient(self.base_url, timeout_seconds=2)
        with self.assertRaises(CortexScoutError) as raised:
            client._request("GET", "/missing")

        self.assertIn("HTTP 404", str(raised.exception))

    def test_client_parses_large_json_before_tool_truncation(self):
        client = CortexScoutClient(self.base_url, timeout_seconds=2, max_response_chars=20)
        result = client.call_tool("large", {})

        self.assertEqual(result["content"][0]["text"], "x" * 200)


if __name__ == "__main__":
    unittest.main()
