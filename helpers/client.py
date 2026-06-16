from __future__ import annotations

import json
from urllib import error, request


class CortexScoutError(RuntimeError):
    pass


class CortexScoutClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int | float = 120,
        max_response_chars: int = 20000,
    ) -> None:
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url:
            raise CortexScoutError("Cortex Scout base_url is empty")
        self.base_url = base_url
        self.timeout_seconds = float(timeout_seconds or 120)
        self.max_response_chars = int(max_response_chars or 20000)

    def health(self) -> dict:
        return self._request("GET", "/health")

    def list_tools(self) -> dict:
        return self._request("GET", "/mcp/tools")

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        name = str(name or "").strip()
        if not name:
            raise CortexScoutError("Cortex Scout tool name is empty")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise CortexScoutError("Cortex Scout tool arguments must be an object")
        return self._request("POST", "/mcp/call", {"name": name, "arguments": arguments})

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            method=method.upper(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
        except error.HTTPError as exc:
            body = exc.read(1000).decode("utf-8", "replace")
            raise CortexScoutError(f"HTTP {exc.code} {url}: {body}") from exc
        except error.URLError as exc:
            raise CortexScoutError(f"Cannot reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise CortexScoutError(f"Timed out calling {url}") from exc

        text = raw.decode("utf-8", "replace")
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CortexScoutError(f"Invalid JSON from {url}: {text[:500]}") from exc
