from __future__ import annotations

import threading

from .runtime import ensure_running


PLUGIN_NAME = "cortex_scout"

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
        from helpers import plugins

        config = plugins.get_plugin_config(PLUGIN_NAME) or {}
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
