---
name: crux-configuring
description: Use when the user wants to set up, configure, or troubleshoot Crux (ALCF) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/crux.json file. Also use when crux tools fail with connection or embedding errors.
---

# Configuring Crux (ALCF)

Settings live in `~/.hpc-agent/crux.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `CRUX_HOST` and `CRUX_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "crux"
  },
  "defaults": {
    "account": "<your-ALCF-project>"
  }
}
```

## What must be true before it can connect

ALCF login asks for a one-time passcode from MobilePASS+ or a
hardware token, which non-interactive SSH cannot answer. Use
OpenSSH connection multiplexing: add a 'crux' block to
~/.ssh/config with HostName crux.alcf.anl.gov, your User, and
ControlMaster auto, ControlPath ~/.ssh/controlmasters/%C,
ControlPersist 30m (mkdir -p that directory, chmod 700), open the
master once with `ssh -MNf crux` entering your passcode, then set
ssh.host to that SAME alias — a bare hostname selects a different
control socket and re-prompts.
Running on a Crux access node instead? Use ssh.host=localhost.
Set defaults.account to one of your ALCF projects (see
sbank-list-allocations -r crux): every job needs #PBS -A. Never
copy a project from another user. CRUX_ACCOUNT overrides the
configured default.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/crux.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

   - **The recommended setup is a multiplexed SSH alias.** ALCF asks for a
     one-time passcode (MobilePASS+ app or hardware token) at every login,
     which a non-interactive SSH call can never answer — so the user
     authenticates once, interactively, and every later `ssh`/`rsync` reuses
     that connection.

     Have the user add a block to `~/.ssh/config` (substituting their ALCF
     username):

     ```
     Host crux
         HostName crux.alcf.anl.gov
         User <their-ALCF-username>
         ControlMaster auto
         ControlPath ~/.ssh/controlmasters/%C
         ControlPersist 30m
     ```

     then, after `mkdir -p ~/.ssh/controlmasters && chmod 700
     ~/.ssh/controlmasters`, open the master once:

     ```bash
     ssh -MNf crux        # they type their one-time passcode here
     ssh -O check crux    # Master running (pid=…)
     ```

     Set `"host"` to that **same alias**. A bare hostname, or a different
     user or port, selects a different control socket and re-prompts.
   - **Running on a Crux access node instead?** Use `"host": "localhost"`
     (direct local execution, no SSH at all).

**Never ask the user for their one-time passcode, and never try to script or
automate entering one.** The whole arrangement depends on the passcode being
typed by the person, once, in their own terminal.

**Also set `defaults.account`** — every job is billed to an ALCF project
(`#PBS -A` is mandatory), and `submit_job` refuses without one. Find the
user's projects with `get_projects(facility="crux")` once the connection
works, or ask them to run `sbank-list-allocations -r crux`. `CRUX_ACCOUNT`
overrides the file. Never reuse a project from an example or from another
user.

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
3. **Write the file** to `~/.hpc-agent/crux.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor crux
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   crux` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest crux
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
