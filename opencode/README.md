# OpenCode plugin

This directory is the [OpenCode](https://opencode.ai) harness target for
hpc-rookery: a plugin that registers the two MCP servers every facility
shares and contributes the selected facility skill packs. The Python
servers stay the single engine — the same `uv tool run --from git+...`
command `plugins/hpc/.mcp.json` gives Codex and Claude Code and
`pi/extension.ts` gives Pi.

The **whole repository is the plugin package** (the root `package.json`
`exports` points here), because the plugin reads `facilities/` and the
skill packs from `plugins/` relative to itself — a git install therefore
carries everything it needs.

## Install

```sh
opencode plugin add 'github:william-dawson/hpc-rookery#main'
```

Then pick your facilities inside any session:

```text
/hpc rikyu,tsubame
```

The selection is stored in plugin storage, persists across sessions, and
loads the packs without a restart. `/hpc` alone lists the current and
available facilities; `/hpc clear` empties the selection (the shared
`hpc-facilities` skill always loads).

For development from a checkout, configure the local path instead —
same plugin, no install:

```jsonc
{
  "plugins": [{ "package": "/path/to/hpc-rookery" }]
}
```

(`npm install` inside `opencode/` once, for the `@opencode/plugin`
dependency; OpenCode loads `src/index.ts` directly, no build step.)

## Options

| Option | Default | Meaning |
|---|---|---|
| `facilities` | `[]` | The **initial** selection; `/hpc` overrides it and persists. An unknown slug fails plugin load with the list of valid ones. |
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
- **`/hpc` command** — set, list, or clear the facility selection;
  changes persist in plugin storage and reload the skill packs at once.

## Notes and limits

- Do not install via the git `::path:opencode` selector: a
  subdirectory-only install loses the `facilities/` and `plugins/`
  trees the plugin reads. Install the repository (the default, no
  `::path:`).
- No client-side argument rule is needed here, unlike the Pi extension:
  OpenCode does not pre-validate MCP tool arguments against the server's
  schema, and the server's pydantic accepts a `spec` as either an object
  or a JSON string.
- To gate destructive tools, OpenCode's permission system can deny or
  ask per tool name (see the OpenCode permissions docs), e.g. an `ask`
  rule on `hpc_fs_rm`.
- Verified against OpenCode 2.2.3 and `@opencode/plugin` 2.3.0;
  type-check with `./node_modules/.bin/tsc -p .` inside `opencode/`.
