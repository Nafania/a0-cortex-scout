from __future__ import annotations

from helpers.extension import Extension

try:
    from usr.plugins.cortex_scout.helpers.autostart import start_background
except ModuleNotFoundError:
    from helpers.autostart import start_background


class CortexScoutAutostart(Extension):
    def execute(self, **kwargs):
        start_background("agent-zero-startup")
