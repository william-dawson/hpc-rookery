---
name: miyabi-configuring
description: Use when the user wants to set up, configure, or troubleshoot Miyabi (JCAHPC) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/miyabi.json file. Also use when miyabi tools fail with connection or embedding errors.
---

# Configuring Miyabi (JCAHPC)

Settings live in `~/.hpc-agent/miyabi.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `MIYABI_HOST` and `MIYABI_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "miyabi-g"
  },
  "defaults": {
    "group": "<your-project-group>"
  }
}
```

## What must be true before it can connect

Miyabi asks for a one-time code at login, which non-interactive SSH
cannot answer. Use OpenSSH connection multiplexing: add a host block
to ~/.ssh/config with ControlMaster auto, ControlPath
~/.ssh/controlmasters/%C and ControlPersist 30m (mkdir -p that
directory, chmod 700), open the master once with `ssh -MNf <alias>`
entering your code, then set ssh.host to that SAME alias — a bare
hostname selects a different control socket and re-prompts.
Running on a Miyabi login node instead? Use ssh.host=localhost.
Set defaults.group to your own PBS project group: every job requires
#PBS -W group_list=<group>. Never copy a group from another user.
MIYABI_GROUP overrides the configured group.
If a call is suddenly refused with 'Permission denied
(keyboard-interactive)', the master connection expired — re-run
`ssh -MNf <alias>`. Never ask the user for their one-time code.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/miyabi.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

   - **The recommended setup is a multiplexed SSH alias.** Miyabi asks for a
     one-time code at login, which a non-interactive SSH call can never
     answer — so the user authenticates once, interactively, and every later
     `ssh`/`rsync` reuses that connection.

     Have the user add a block to `~/.ssh/config` (substituting their
     account):

     ```
     Host miyabi-g
         HostName miyabi-g.jcahpc.jp
         User <account>
         ControlMaster auto
         ControlPath ~/.ssh/controlmasters/%C
         ControlPersist 30m
     ```

     then, after `mkdir -p ~/.ssh/controlmasters && chmod 700
     ~/.ssh/controlmasters`, open the master once:

     ```bash
     ssh -MNf miyabi-g       # they enter their one-time code here
     ssh -O check miyabi-g   # Master running (pid=…)
     ```

     Set `"host"` to that **same alias**. A bare hostname, or a different
     user or port, selects a different control socket and re-prompts.
   - **Running on a Miyabi login node instead?** Use `"host": "localhost"`,
     which is direct local execution and involves no SSH at all.

**Never ask the user for their one-time code, and never try to script or
automate entering one.** The whole arrangement depends on the code being
typed by the person, once, in their own terminal.

**Also set `defaults.group`** — every PBS job needs the user's own project
group (`#PBS -W group_list=<group>`), and `submit_job` refuses without one.
`MIYABI_GROUP` overrides the file. Never reuse a group from an example or
from another user; `id -Gn` on the login node shows theirs.

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
3. **Write the file** to `~/.hpc-agent/miyabi.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor miyabi
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   miyabi` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest miyabi
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
