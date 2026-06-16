### cortex_scout
Call a running Cortex Scout HTTP/MCP server.

Use this tool for token-efficient web search, page fetch, deep research, visual scouting, or Cortex Scout browser automation when the Cortex Scout server is already running.

Actions:
- `health`: check Cortex Scout availability.
- `list_tools`: list Cortex Scout MCP tools.
- `call`: call one Cortex Scout MCP tool through `/mcp/call`.

Arguments:
- `action`: `health`, `list_tools`, or `call`.
- `tool`: Cortex Scout MCP tool name, required for `call`.
- `arguments`: JSON object passed to Cortex Scout MCP tool.

Common Cortex Scout tools:
- `web_search`
- `web_fetch`
- `deep_research`
- `visual_scout`
- `scout_browser_automate`
- `scout_browser_close`

Example:
~~~json
{
  "thoughts": ["Need fetch rendered page content with Cortex Scout."],
  "headline": "Fetching page with Cortex Scout",
  "tool_name": "cortex_scout",
  "tool_args": {
    "action": "call",
    "tool": "web_fetch",
    "arguments": {
      "mode": "single",
      "url": "https://example.com",
      "output_format": "clean_json",
      "max_chars": 1200
    }
  }
}
~~~
