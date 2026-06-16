import unittest
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


def load_tool_module():
    if "helpers.plugins" not in sys.modules:
        plugins = types.ModuleType("helpers.plugins")
        plugins.get_plugin_config = lambda *_args, **_kwargs: {}
        sys.modules["helpers.plugins"] = plugins
    if "helpers.tool" not in sys.modules:
        tool = types.ModuleType("helpers.tool")
        tool.Response = type("Response", (), {})
        tool.Tool = type("Tool", (), {})
        sys.modules["helpers.tool"] = tool
    if "usr.plugins.cortex_scout.helpers.client" not in sys.modules:
        for name in (
            "usr",
            "usr.plugins",
            "usr.plugins.cortex_scout",
            "usr.plugins.cortex_scout.helpers",
        ):
            pkg = sys.modules.setdefault(name, types.ModuleType(name))
            pkg.__path__ = []
        client = types.ModuleType("usr.plugins.cortex_scout.helpers.client")
        client.CortexScoutError = RuntimeError
        client.CortexScoutClient = object
        runtime = types.ModuleType("usr.plugins.cortex_scout.helpers.runtime")
        runtime.ensure_running = lambda *_args, **_kwargs: None
        sys.modules["usr.plugins.cortex_scout.helpers.client"] = client
        sys.modules["usr.plugins.cortex_scout.helpers.runtime"] = runtime

    path = Path(__file__).resolve().parents[1] / "tools" / "cortex_scout.py"
    spec = importlib.util.spec_from_file_location("cortex_scout_tool_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CortexScoutToolConfigTests(unittest.TestCase):
    def test_config_keeps_lifecycle_keys_for_tool_recovery(self):
        source = {
            "base_url": "http://127.0.0.1:5055",
            "timeout_seconds": 7,
            "max_response_chars": 1234,
            "auto_start": True,
            "auto_install": True,
            "binary_path": "/bin/scout",
            "startup_timeout_seconds": 9,
            "release_version": "v1.2.3",
            "memory_disabled": False,
            "bin_dir": "/tmp/bin",
            "runtime_dir": "/tmp/runtime",
            "asset_name": "asset.tar.gz",
            "download_url": "file:///tmp/asset.tar.gz",
            "binary_sha256": "abc123",
        }

        module = load_tool_module()
        with patch.object(module.plugins, "get_plugin_config", return_value=source):
            config = module._config(agent=None)

        for key, value in source.items():
            self.assertEqual(config[key], value)


if __name__ == "__main__":
    unittest.main()
