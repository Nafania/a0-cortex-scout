from __future__ import annotations

try:
    from usr.plugins.cortex_scout.helpers.autostart import start_background
except ModuleNotFoundError:
    from helpers.autostart import start_background


def install() -> bool:
    start_background("install")
    return True
