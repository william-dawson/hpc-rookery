# Pi package

This directory is the [Pi](https://github.com/earendil-works/pi) harness
target for hpc-rookery. The root `package.json` is the Pi-package manifest;
`pi/extension.ts` is the extension it loads. The extension is harness glue
only — every cluster operation stays in the Python MCP servers, exactly as
the Codex and Claude Code plugins consume them.

## Install

```sh
pi install git:github.com/william-dawson/hpc-rookery@main
```

From a checkout, `pi -e ./pi/extension.ts` tries it for one session, or
`pi install ./` installs the checkout persistently. Pi pins a git install
to the ref you name; update with `pi update --extensions`.

## What loads

| Piece | Behavior |
|---|---|
| `hpc` MCP server | `direct` exposure — all tools are declared to the model, because the skill packs instruct it to call them by name. 300s per-request timeout: job and file operations travel over SSH. |
| `hpc-docs` MCP server | `deferred` exposure — `search_docs`, `list_doc_sections`, `read_doc_section` surface through `tool_search` when a machine guide is needed. |
| `hpc-facilities` skill | contributed in every session. |
| `hpc-<slug>` skill packs | contributed for the facilities selected with `/hpc`. |

Tools are named `mcp__hpc__submit_job`, `mcp__hpc__search_docs`, and so on.
Inspect both servers with `/mcp` inside a session.

Both servers launch with the same command as `plugins/hpc/.mcp.json`:

```sh
uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-mcp
```

so the Python side always tracks `main` regardless of which ref the Pi
package was installed from — identical to the Codex and Claude Code
plugins' behavior. The first launch resolves the environment; run
`hpc-doctor` once (same `uv tool run`, entry point `hpc-doctor`) to warm
the cache and configure cluster access.

## /hpc

Facility skill packs are opt-in, matching the marketplace model: the base
plugin never loads guidance for machines you don't use.

- `/hpc` — interactive picker (↑↓ move, Space toggles, Enter applies,
  Esc cancels). Applying reloads the session so the packs load.
- `/hpc set rikyu,fugaku` — set the selection non-interactively (usable in
  RPC and print mode).
- `/hpc list` — show the selected and available slugs.
- `/hpc clear` — load no facility packs.

The selection is stored per **user**, not per project, in
`~/.pi/agent/hpc-rookery.json` (`{ "facilities": ["rikyu"] }`) — HPC access
belongs to the user's ssh config and `~/.hpc-agent`, not to a repository.
Skills are contributed through the `resources_discover` event, so Pi
package resource filters do not manage them; `/hpc` is the one mechanism.

## Safety gate

`mcp__hpc__fs_rm` asks for confirmation before every call (cluster
filesystems have no trash). Sessions without a UI (print/JSON mode) fail
closed — the call is blocked rather than silently allowed. The gate keys on
the registered server name; if you override the server in your own
`mcp.json` under a different name, the gate does not apply.

## Overrides and notes

- A server defined in your own `~/.pi/agent/mcp.json` (or project
  `.pi/mcp.json`) with the name `hpc` or `hpc-docs` takes precedence over
  the extension's registration — that is the supported way to change
  exposure, timeout, or the install ref.
- `pi mcp list` does not see extension-registered servers (shell commands
  load no extensions); use `/mcp` inside a session.
- Don't install the same skills twice: use this package *or* a manual copy
  of the skill directories, not both — duplicate skill names produce a
  startup warning.
- `package.json` is hand-maintained (it is deliberately tiny); bump its
  `version` alongside plugin versions when the extension changes. It is
  `"private": true` so the Python repository is never accidentally
  published to npm; distribution is via git, per the repo's
  never-publish-`hpc_agent_core` rule.
