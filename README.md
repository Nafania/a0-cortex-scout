# Cortex Scout Agent Zero Plugin

Agent Zero plugin that runs [Cortex Scout](https://github.com/cortex-works/cortex-scout) and exposes it through one tool: `cortex_scout`.

## Install

Copy this folder to:

```text
/a0/usr/plugins/cortex_scout
```

Enable the plugin in Agent Zero.

On install, Agent Zero startup, and first tool use, the plugin downloads the
matching Cortex Scout release binary into `bin/`, verifies its SHA-256 checksum,
starts it on `127.0.0.1:5055`, and keeps it alive for the Agent Zero process.

No Docker Compose and no Rust build are required.

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

The default bundled download supports upstream release `v3.3.7` assets:

- Linux ARM64
- macOS ARM64
- Windows x64
- Windows ARM64

If upstream has no binary for your platform, set `binary_path` to a compatible
`cortex-scout` executable. Current upstream release has no Linux x64 asset.
