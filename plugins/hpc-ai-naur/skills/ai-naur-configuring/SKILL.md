---
name: ai-naur-configuring
description: Use when the user wants to set up, configure, or troubleshoot ai-Naur (Naur GB300 node) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/ai_naur.json file. Also use when ai-naur tools fail with connection or embedding errors.
---

# Configuring ai-Naur (Naur GB300 node)

Settings live in `~/.hpc-agent/ai_naur.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `AI_NAUR_HOST` and `AI_NAUR_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "ai-Naur"
  }
}
```

## What must be true before it can connect

naur needs non-interactive key-based SSH; the MCP server cannot
answer a password prompt. Add an 'ai-Naur' Host alias to
~/.ssh/config with the HostName, User and IdentityFile the machine's
administrator gave you, and check that `ssh ai-Naur hostname` prints
'naur' without prompting. No project/account is needed: Slurm's
accounting database is not in service. Running on naur itself? Use
host=localhost.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/ai_naur.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

naur is reached with key-based SSH through an `ai-Naur` alias in
`~/.ssh/config` (HostName, User and IdentityFile issued by the machine's
administrator). The alias must work without a password or passphrase prompt:
`ssh ai-Naur hostname` should print `naur`. Do not guess the IP address or
user name; ask the user to copy them from the administrator's instructions.

No project/account setting exists — Slurm's accounting database is not in
service on this cluster, and a configured account would be rejected. If the
agent runs on naur itself, use `"host": "localhost"`.

After writing the config, prove access with `get_resources` (it should list
a `naur` partition, alongside the sibling machines `prado`, `shannon` and
`backus`). `get_projects` is unsupported on naur, so do not use it as a
connectivity check.

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
3. **Write the file** to `~/.hpc-agent/ai_naur.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor ai-naur
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   ai-naur` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest ai-naur
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
