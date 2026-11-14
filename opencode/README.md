# OpenCode plugin

This directory is the [OpenCode](https://opencode.ai) harness target for
hpc-rookery: a plugin that registers the two MCP servers every facility
shares and contributes the selected facility skill packs. The Python
servers stay the single engine — the same `uv tool run --from git+...`
command `plugins/hpc/.mcp.json` gives Codex and Claude Code and
`pi/extension.ts` gives Pi.

## Install (from a checkout)

Run `npm install` inside this directory once (the `@opencode/plugin`
dependency); OpenCode loads `src/index.ts` directly, no build step. Then
add the plugin to `opencode.json` (global:
`~/.config/opencode/opencode.json`) with the facilities you use:

```jsonc
{
  "plugins": [
    {
      "package": "/path/to/hpc-rookery/opencode",
      "options": {
        "facilities": ["rikyu", "tsubame"]
      }
    }
  ]
}
```

## Options

| Option | Default | Meaning |
|---|---|---|
| `facilities` | `[]` | Slugs whose skill packs to load. The shared `hpc-facilities` skill always loads. An unknown slug fails plugin load with the list of valid ones. |
| `gitRef` | `git+https://github.com/william-dawson/hpc-rookery.git@main` | The `uv --from` requirement for both servers — override to test a branch or pin a tag. |

## What registers

- **MCP server `hpc`** — every tool on the provider's native tool list
  (`codemode: false`, named `hpc_submit_job`, `hpc_fs_rm`, …), because the
  skill packs instruct the model to call tools by name. 120s startup
  timeout: `uv` cold-resolves the git ref on the very first launch.
- **MCP server `hpc-docs`** — same shape, for the three guide tools.
- **Skills** — the base `hpc-facilities` pack plus one pack per selected
  facility, read from `plugins/hpc-<slug>/skills/` (the generated
  frontmatter supplies each skill's name and description).

## Notes and limits

- The plugin reads `facilities/` and `plugins/` relative to its own
  location, so it must load from a full checkout. A published plugin
  would need generated skill data inside its own package — the same
  problem the Codex/Claude packs solve by being their own directories; a
  git `::path:` subdirectory install would not resolve the skills yet.
- No client-side argument rule is needed here, unlike the Pi extension:
  OpenCode does not pre-validate MCP tool arguments against the server's
  schema, and the server's pydantic accepts a `spec` as either an object
  or a JSON string.
- To gate destructive tools, OpenCode's permission system can deny or ask
  per tool name (see the OpenCode permissions docs), e.g. an `ask` rule
  on `hpc_fs_rm`.
- Verified against OpenCode 2.2.3 and `@opencode/plugin` 2.3.0;
  `tsconfig.json` + `npm run`-less type-check:
  `./node_modules/.bin/tsc -p .`
