---
name: tsubame-configuring
description: Use when the user wants to set up, configure, or troubleshoot TSUBAME4.0 (Science Tokyo) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/tsubame.json file. Also use when tsubame tools fail with connection or embedding errors.
---

# Configuring TSUBAME4.0 (Science Tokyo)

Settings live in `~/.hpc-agent/tsubame.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `TSUBAME_HOST` and `TSUBAME_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "tsubame"
  },
  "defaults": {
    "group": "<your-TSUBAME-group>"
  }
}
```

## What must be true before it can connect

TSUBAME4 accepts registered SSH keys, not password prompts. Register
your public key in the TSUBAME portal, then add a 'tsubame' alias
to ~/.ssh/config pointing at login.t4.gsic.titech.ac.jp and your
Science Tokyo username, or set ssh.host to that user@host value.
Set defaults.group to a TSUBAME group returned by get_projects if
normal jobs should charge it. Omitting the group deliberately uses
the free trial limits (2 resource units, 3 minutes, priority -5).
Never copy a group name from an example. TSUBAME_GROUP overrides
the configured default; use host=localhost when already logged in.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/tsubame.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

TSUBAME4 requires non-interactive, registered SSH-key access. Register the
user's public key in the TSUBAME portal, then configure an SSH alias named
`tsubame` for `login.t4.gsic.titech.ac.jp`, or put the issued user@host in
`ssh.host`. Use `localhost` when the agent already runs on a login node.

Set `defaults.group` only to a group returned by
`get_projects(facility="tsubame")`; `TSUBAME_GROUP` overrides it. An omitted
group is meaningful and selects the strictly limited free trial. Docs search is
BM25-only because no embedding endpoint has been verified.

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
3. **Write the file** to `~/.hpc-agent/tsubame.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor tsubame
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   tsubame` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest tsubame
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
