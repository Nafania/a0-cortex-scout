from __future__ import annotations

import json
import threading
from pathlib import Path

from .runtime import ensure_running


PLUGIN_NAME = "cortex_scout"
PLUGIN_DIR = Path(__file__).resolve().parents[1]

_lock = threading.Lock()
_thread: threading.Thread | None = None


def start_background(reason: str = "startup", config: dict | None = None) -> threading.Thread:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return _thread
        _thread = threading.Thread(
            target=start_now,
            kwargs={"reason": reason, "config": config},
            name="a0-cortex-scout-autostart",
            daemon=True,
        )
        _thread.start()
        return _thread


def start_now(reason: str = "startup", config: dict | None = None) -> None:
    if config is None:
        config = _load_config()
    try:
        ensure_running(config)
        _log("info", f"Cortex Scout: started ({reason})")
    except Exception as exc:
        _log("warning", f"Cortex Scout: autostart failed ({reason}): {exc}")


def _log(level: str, message: str) -> None:
    try:
        from helpers.print_style import PrintStyle

        getattr(PrintStyle, level)(message)
    except Exception:
        print(message)


def _load_config() -> dict:
    config = _load_agent_zero_config()
    if config is not None:
        return config
    return _load_local_config()


def _load_agent_zero_config() -> dict | None:
    try:
        from helpers import plugins
    except Exception:
        return None

    try:
        config = plugins.get_plugin_config(PLUGIN_NAME, agent=None)
    except TypeError:
        try:
            config = plugins.get_plugin_config(PLUGIN_NAME)
        except Exception:
            return None
    except Exception:
        return None

    return config if config else None


def _load_local_config() -> dict:
    config_path = PLUGIN_DIR / "config.json"
    if config_path.is_file():
        return json.loads(config_path.read_text())

    default_path = PLUGIN_DIR / "default_config.yaml"
    if not default_path.is_file():
        return {}

    try:
        from helpers import yaml as yaml_helper

        return yaml_helper.loads(default_path.read_text()) or {}
    except Exception:
        return _parse_simple_yaml(default_path.read_text())


def _parse_simple_yaml(text: str) -> dict:
    config = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        config[key.strip()] = _parse_scalar(value.strip())
    return config


def _parse_scalar(value: str):
    if not value:
        return ""
    if value in {'""', "''"}:
        return ""
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value.strip("\"'")
