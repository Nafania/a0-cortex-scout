import hashlib
import os
import socket
import stat
import tarfile
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from usr.plugins.cortex_scout.helpers.client import CortexScoutClient, CortexScoutError
    from usr.plugins.cortex_scout.helpers.runtime import ensure_running, stop
except ModuleNotFoundError:
    from helpers.client import CortexScoutClient, CortexScoutError
    from helpers.runtime import ensure_running, stop


class HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"healthy","service":"cortex-scout"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        return


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class CortexScoutRuntimeTests(unittest.TestCase):
    def tearDown(self):
        stop()

    def test_ensure_running_keeps_existing_healthy_server(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthyHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            ensure_running({"base_url": base_url, "auto_start": False})
            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ensure_running_starts_configured_binary(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            binary = write_fake_scout_binary(tmp, "fake-scout")

            base_url = f"http://127.0.0.1:{port}"
            ensure_running({
                "base_url": base_url,
                "binary_path": binary,
                "auto_start": True,
                "auto_install": False,
                "runtime_dir": os.path.join(tmp, "runtime"),
                "startup_timeout_seconds": 5,
            })

            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")

    def test_ensure_running_downloads_binary_when_missing(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source")
            os.mkdir(source)
            write_fake_scout_binary(source, "cortex-scout")

            archive = os.path.join(tmp, "cortex-scout.tar.gz")
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(os.path.join(source, "cortex-scout"), arcname="cortex-scout")

            with open(archive, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()

            bin_dir = os.path.join(tmp, "bin")
            base_url = f"http://127.0.0.1:{port}"
            ensure_running({
                "base_url": base_url,
                "auto_start": True,
                "auto_install": True,
                "download_url": f"file://{archive}",
                "binary_sha256": digest,
                "bin_dir": bin_dir,
                "startup_timeout_seconds": 5,
            })

            self.assertTrue(os.path.exists(os.path.join(bin_dir, "cortex-scout")))
            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")

    def test_ensure_running_reports_missing_binary(self):
        with self.assertRaises(CortexScoutError) as raised:
            ensure_running({
                "base_url": f"http://127.0.0.1:{free_port()}",
                "binary_path": "/missing/cortex-scout",
                "auto_start": True,
                "auto_install": False,
                "startup_timeout_seconds": 1,
            })

        self.assertIn("Cortex Scout binary not found", str(raised.exception))


def write_fake_scout_binary(directory, name):
    binary = os.path.join(directory, name)
    with open(binary, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import sys
            from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/health":
                        body = b'{"status":"healthy","service":"cortex-scout"}'
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    self.send_response(404)
                    self.end_headers()
                def log_message(self, *_args):
                    return

            port = int(sys.argv[sys.argv.index("--port") + 1])
            ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
            """
        ))
    os.chmod(binary, os.stat(binary).st_mode | stat.S_IXUSR)
    return binary


if __name__ == "__main__":
    unittest.main()
