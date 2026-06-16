import os
import tempfile
import unittest

try:
    from usr.plugins.cortex_scout.helpers.autostart import start_now
    from usr.plugins.cortex_scout.helpers.client import CortexScoutClient
    from usr.plugins.cortex_scout.helpers.runtime import stop
    from usr.plugins.cortex_scout.tests.test_runtime import free_port, write_fake_scout_binary
except ModuleNotFoundError:
    from helpers.autostart import start_now
    from helpers.client import CortexScoutClient
    from helpers.runtime import stop
    from tests.test_runtime import free_port, write_fake_scout_binary


class CortexScoutAutostartTests(unittest.TestCase):
    def tearDown(self):
        stop()

    def test_start_now_starts_scout_from_config(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            binary = write_fake_scout_binary(tmp, "fake-scout")
            base_url = f"http://127.0.0.1:{port}"

            start_now("test", {
                "base_url": base_url,
                "binary_path": binary,
                "auto_start": True,
                "auto_install": False,
                "runtime_dir": os.path.join(tmp, "runtime"),
                "startup_timeout_seconds": 5,
            })

            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")


if __name__ == "__main__":
    unittest.main()
