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
from unittest.mock import patch

try:
    from usr.plugins.cortex_scout.helpers.client import CortexScoutClient, CortexScoutError
    from usr.plugins.cortex_scout.helpers import runtime as runtime_helper
    from usr.plugins.cortex_scout.helpers.runtime import ensure_running, stop
except ModuleNotFoundError:
    from helpers import runtime as runtime_helper
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

    def test_ensure_running_restarts_dead_process(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            binary = write_fake_scout_binary(tmp, "fake-scout")
            base_url = f"http://127.0.0.1:{port}"
            config = {
                "base_url": base_url,
                "binary_path": binary,
                "auto_start": True,
                "auto_install": False,
                "runtime_dir": os.path.join(tmp, "runtime"),
                "startup_timeout_seconds": 5,
            }

            ensure_running(config)
            first = runtime_helper._process
            self.assertIsNotNone(first)
            first.kill()
            first.wait(timeout=2)

            ensure_running(config)
            second = runtime_helper._process
            self.assertIsNotNone(second)
            self.assertIsNot(first, second)
            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")

    def test_download_without_checksum_fails_before_trusting_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runtime_helper, "_download") as download:
                with self.assertRaises(CortexScoutError) as raised:
                    ensure_running({
                        "base_url": f"http://127.0.0.1:{free_port()}",
                        "auto_start": True,
                        "auto_install": True,
                        "release_version": "v9.9.9",
                        "bin_dir": tmp,
                        "startup_timeout_seconds": 1,
                    })

        self.assertIn("checksum", str(raised.exception).lower())
        download.assert_not_called()

    def test_supported_default_assets_have_checksums(self):
        cases = [
            ("Linux", "aarch64", "cortex-scout-3.3.7-linux-arm64.tar.gz"),
            ("Darwin", "arm64", "cortex-scout-3.3.7-macos-arm64.tar.gz"),
            ("Windows", "AMD64", "cortex-scout-3.3.7-windows-x64.zip"),
            ("Windows", "ARM64", "cortex-scout-3.3.7-windows-arm64.zip"),
        ]

        for system, machine, asset in cases:
            with self.subTest(system=system, machine=machine):
                with patch.object(runtime_helper.platform, "system", return_value=system):
                    with patch.object(runtime_helper.platform, "machine", return_value=machine):
                        self.assertEqual(runtime_helper._default_asset_name(), asset)
                self.assertIn(asset, runtime_helper.CHECKSUMS)

    def test_linux_x64_without_release_asset_fails_loudly(self):
        with patch.object(runtime_helper.platform, "system", return_value="Linux"):
            with patch.object(runtime_helper.platform, "machine", return_value="x86_64"):
                with self.assertRaises(CortexScoutError) as raised:
                    runtime_helper._default_asset_name()

        self.assertIn("No Cortex Scout release binary", str(raised.exception))

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
