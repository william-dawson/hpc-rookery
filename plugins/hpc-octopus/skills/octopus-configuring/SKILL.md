---
name: octopus-configuring
description: Use when the user wants to set up, configure, or troubleshoot Octopus (RIKEN R-CCS) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/octopus.json file. Also use when octopus tools fail with connection or embedding errors.
---

# Configuring Octopus (RIKEN R-CCS)

Settings live in `~/.hpc-agent/octopus.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `OCTOPUS_HOST` and `OCTOPUS_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "octopus"
  }
}
```

## What must be true before it can connect

Octopus accepts non-interactive, key-based SSH; the MCP server cannot
answer a password prompt. Add an 'octopus' alias to ~/.ssh/config
using the management-node hostname and username issued to you by
the site, or set ssh.host to that user@host value directly.
No account is normally required in the config: Slurm applies the
user's DefaultAccount. If you belong to several projects and want
a persistent override, add defaults.account after get_projects has
shown the real account names; never copy another user's account.
Running on an Octopus front end? Use host=localhost instead.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/octopus.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

Octopus requires non-interactive key-based SSH to the management node. Use an
SSH alias or user@host issued for the user's own account; do not invent a
public hostname. If the agent runs on an Octopus front end, use
`"host": "localhost"`.

An account override is optional because Slurm supplies each user's
`DefaultAccount`. Only configure `defaults.account` after `get_projects` has
shown that user's real associations. Docs embeddings use the shared RIKEN
endpoint when a key is available and otherwise fall back to BM25.

   - **Running the agent session directly on this facility's own
     front-end/login node** (not a personal laptop)? Use
     `"host": "localhost"` instead — no SSH key needed. Skip the
     verification step below for this case; there's nothing to probe.
   - Verify with: `ssh -o BatchMode=yes <host> 'echo ok'` (BatchMode
     matters — the server cannot answer a password prompt; key-based auth
     is required). Not applicable for `"host": "localhost"`.
   - **Enable SSH multiplexing unless the user explicitly opts out.** This
     lets repeated agent operations reuse one authenticated connection rather
     than making the login node authenticate every call. Recommend an SSH
     alias and, after showing the exact change and receiving confirmation,
     add a narrowly scoped block to `~/.ssh/config` without overwriting any
     unrelated entries:
     ```sshconfig
     Host <alias>
       ControlMaster auto
       ControlPath ~/.ssh/controlmasters/%C
       ControlPersist 30m
     ```
     Create `~/.ssh/controlmasters` with mode `0700`, then open the initial
     master in the user's own terminal with `ssh -MNf <alias>`. Set
     `ssh.host` to that same alias. `ControlMaster no` is an intentional
     opt-out; do not add or change multiplexing settings when it is present.
2. **Embedding API key** (optional — skippable; BM25 keyword search still
   works without it). Store it under `embedding.api_key`.
3. **Write the file** to `~/.hpc-agent/octopus.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor octopus
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   octopus` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest octopus
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
