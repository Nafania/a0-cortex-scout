import os
import importlib.util
import tempfile
import threading
import time
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from usr.plugins.cortex_scout.helpers import autostart as autostart_helper
    from usr.plugins.cortex_scout.helpers.client import CortexScoutClient
    from usr.plugins.cortex_scout.helpers.runtime import stop
    from usr.plugins.cortex_scout.tests.test_runtime import free_port, write_fake_scout_binary
except ModuleNotFoundError:
    from helpers import autostart as autostart_helper
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

            with patch.object(autostart_helper, "_log"):
                autostart_helper.start_now("test", {
                    "base_url": base_url,
                    "binary_path": binary,
                    "auto_start": True,
                    "auto_install": False,
                    "runtime_dir": os.path.join(tmp, "runtime"),
                    "startup_timeout_seconds": 5,
                })

            self.assertEqual(CortexScoutClient(base_url, timeout_seconds=2).health()["status"], "healthy")

    def test_start_background_deduplicates_running_thread(self):
        started = threading.Event()
        release = threading.Event()

        def slow_start(**_kwargs):
            started.set()
            release.wait(timeout=3)

        with patch.object(autostart_helper, "start_now", side_effect=slow_start):
            first = autostart_helper.start_background("test", {})
            self.assertTrue(started.wait(timeout=1))
            second = autostart_helper.start_background("test", {})
            self.assertIs(first, second)
            release.set()
            first.join(timeout=3)

    def test_install_hook_returns_before_background_start_finishes(self):
        hooks = load_plugin_file("hooks.py", "cortex_scout_hooks_under_test")

        started = threading.Event()
        release = threading.Event()

        def slow_start(**_kwargs):
            started.set()
            release.wait(timeout=3)

        with patch.object(autostart_helper, "start_now", side_effect=slow_start):
            start = time.monotonic()
            self.assertTrue(hooks.install())
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.5)
            self.assertTrue(started.wait(timeout=1))
            release.set()
            autostart_helper._thread.join(timeout=3)

    def test_startup_extension_returns_before_background_start_finishes(self):
        extension_module = types.ModuleType("helpers.extension")
        extension_module.Extension = object
        sys.modules.setdefault("helpers.extension", extension_module)
        module = load_plugin_file(
            "extensions/python/startup_migration/_10_cortex_scout_autostart.py",
            "cortex_scout_startup_extension_under_test",
        )

        started = threading.Event()
        release = threading.Event()

        def slow_start(**_kwargs):
            started.set()
            release.wait(timeout=3)

        with patch.object(autostart_helper, "start_now", side_effect=slow_start):
            start = time.monotonic()
            module.CortexScoutAutostart().execute()
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 0.5)
            self.assertTrue(started.wait(timeout=1))
            release.set()
            autostart_helper._thread.join(timeout=3)

    def test_background_failure_logs_warning(self):
        with patch.object(autostart_helper, "_log") as log:
            autostart_helper.start_now("test", {
                "base_url": f"http://127.0.0.1:{free_port()}",
                "binary_path": "/missing/cortex-scout",
                "auto_start": True,
                "auto_install": False,
            })

        level, message = log.call_args.args
        self.assertEqual(level, "warning")
        self.assertIn("autostart failed", message)

    def test_start_now_prefers_agent_zero_plugin_config(self):
        config = {"base_url": "http://127.0.0.1:5055", "auto_start": True}
        plugins_module = types.ModuleType("helpers.plugins")
        plugins_module.get_plugin_config = Mock(return_value=config)

        previous = sys.modules.get("helpers.plugins")
        sys.modules["helpers.plugins"] = plugins_module
        try:
            with patch.object(autostart_helper, "_load_local_config") as load_local_config:
                self.assertEqual(autostart_helper._load_config(), config)
        finally:
            if previous is None:
                sys.modules.pop("helpers.plugins", None)
            else:
                sys.modules["helpers.plugins"] = previous

        plugins_module.get_plugin_config.assert_called_once_with("cortex_scout", agent=None)
        load_local_config.assert_not_called()

    def test_load_config_falls_back_when_agent_zero_plugin_api_fails(self):
        config = {"base_url": "http://127.0.0.1:5055", "auto_start": True}
        plugins_module = types.ModuleType("helpers.plugins")
        plugins_module.get_plugin_config = Mock(side_effect=RuntimeError("framework not ready"))

        previous = sys.modules.get("helpers.plugins")
        sys.modules["helpers.plugins"] = plugins_module
        try:
            with patch.object(autostart_helper, "_load_local_config", return_value=config) as load_local_config:
                self.assertEqual(autostart_helper._load_config(), config)
        finally:
            if previous is None:
                sys.modules.pop("helpers.plugins", None)
            else:
                sys.modules["helpers.plugins"] = previous

        plugins_module.get_plugin_config.assert_called_once_with("cortex_scout", agent=None)
        load_local_config.assert_called_once_with()

    def test_start_now_passes_loaded_config_to_runtime(self):
        config = {"base_url": "http://127.0.0.1:5055", "auto_start": True}
        with patch.object(autostart_helper, "_load_config", return_value=config) as load_config:
            with patch.object(autostart_helper, "ensure_running") as ensure_running:
                with patch.object(autostart_helper, "_log"):
                    autostart_helper.start_now("startup")

        load_config.assert_called_once_with()
        ensure_running.assert_called_once_with(config)


def load_plugin_file(relative_path, module_name):
    path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
