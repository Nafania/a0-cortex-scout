# Cortex Scout Agent Zero Plugin

Agent Zero plugin that exposes a running [Cortex Scout](https://github.com/cortex-works/cortex-scout) HTTP server through one tool: `cortex_scout`.

## Install

Copy this folder to:

```text
/a0/usr/plugins/cortex_scout
```

Enable the plugin in Agent Zero, then start Cortex Scout separately:

```bash
cortex-scout --port 5000
```

The default plugin URL is `http://127.0.0.1:5000`.

## Tool

`cortex_scout` supports three actions:

- `health`: checks `/health`
- `list_tools`: reads `/mcp/tools`
- `call`: posts to `/mcp/call`

Example:

```json
{
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
```

## Notes

This plugin does not install Cortex Scout, build Rust binaries, mutate Agent Zero MCP settings, or manage background services. That keeps plugin removal clean.
