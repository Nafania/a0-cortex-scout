from __future__ import annotations

import asyncio
import json
from typing import Any

from helpers import plugins
from helpers.tool import Response, Tool
from usr.plugins.cortex_scout.helpers.client import CortexScoutClient, CortexScoutError


PLUGIN_NAME = "cortex_scout"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _config(agent: Any) -> dict[str, Any]:
    config = plugins.get_plugin_config(PLUGIN_NAME, agent=agent) or {}
    return {
        "base_url": config.get("base_url") or "http://127.0.0.1:5000",
        "timeout_seconds": _int(config.get("timeout_seconds"), 120),
        "max_response_chars": _int(config.get("max_response_chars"), 20000),
    }


def _object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise CortexScoutError("arguments must be a JSON object")


def _format(data: dict[str, Any], max_chars: int) -> str:
    if isinstance(data, dict) and isinstance(data.get("content"), list):
        texts = [
            str(item.get("text", ""))
            for item in data["content"]
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if texts:
            prefix = "Cortex Scout tool error:\n" if data.get("isError") else ""
            text = prefix + "\n\n".join(texts)
            return _truncate(text, max_chars)
    return _truncate(json.dumps(data, ensure_ascii=False, indent=2), max_chars)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


class CortexScout(Tool):
    async def execute(
        self,
        action: str = "call",
        tool: str = "",
        arguments: dict[str, Any] | str | None = None,
        **_kwargs: Any,
    ) -> Response:
        cfg = _config(self.agent)
        client = CortexScoutClient(**cfg)
        action = str(action or "call").strip().lower()

        try:
            if action == "health":
                data = await asyncio.to_thread(client.health)
            elif action in {"list_tools", "tools"}:
                data = await asyncio.to_thread(client.list_tools)
            elif action == "call":
                data = await asyncio.to_thread(client.call_tool, tool, _object(arguments))
            else:
                return Response(
                    message="Unsupported Cortex Scout action. Use health, list_tools, or call.",
                    break_loop=False,
                )
        except (CortexScoutError, json.JSONDecodeError) as exc:
            return Response(
                message=(
                    f"Cortex Scout request failed: {exc}\n"
                    "Start Cortex Scout separately, for example: cortex-scout --port 5000"
                ),
                break_loop=False,
            )

        return Response(message=_format(data, cfg["max_response_chars"]), break_loop=False)
