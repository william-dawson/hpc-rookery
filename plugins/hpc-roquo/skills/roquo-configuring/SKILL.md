---
name: roquo-configuring
description: Use when the user wants to set up, configure, or troubleshoot ROQUO (RIKEN R-CCS) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/roquo.json file. Also use when roquo tools fail with connection or embedding errors.
---

# Configuring ROQUO (RIKEN R-CCS)

Settings live in `~/.hpc-agent/roquo.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `ROQUO_HOST` and `ROQUO_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "login.roquo.qc.r-ccs.riken.jp",
    "user": "<your-username>"
  },
  "defaults": {
    "account": "<your-project>"
  }
}
```

## What must be true before it can connect

Register your public key yourself in the ROQUO Portal
(https://portal.roquo.qc.r-ccs.riken.jp/) under 'SSH Keys': paste the
contents of your .pub file and press Add. If that screen says keys
cannot be changed there, open a portal ticket instead.

Set defaults.account to the project you want billed. ROQUO uses it for
both billing and the group that owns files your jobs write, and a job
without it silently falls back to a restrictive default account rather
than failing. `sacctmgr -nP show assoc user=$USER format=Account` on
the login node lists what you may charge.

Login nodes are x86_64 and compute nodes are aarch64, so anything you
build on a login node will not run on a compute node.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/roquo.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

## What ROQUO needs beyond the SSH basics

ROQUO has no one-time password or bastion — a registered public key is
enough, which makes it straightforward compared with some RIKEN machines.

**Key registration is self-service.** The user does it in the ROQUO Portal
(`https://portal.roquo.qc.r-ccs.riken.jp/`) under **SSH Keys**: paste the
contents of the `.pub` file, press Add. Keys appear in the list under the
comment at the end of the public key. If that screen instead says keys
cannot be changed there, administrators manage keys for that account and
the user has to open a portal ticket — tell them that rather than letting
them hunt for the button.

Never ask for, echo, or paste a private key. Only the `.pub` file.

**`defaults.account` matters here more than on most machines.** ROQUO uses
the account for two things: what gets billed, and which group owns the
files a job writes. A job without one is not rejected — it silently
charges a restrictive default. So an unset account produces working jobs
with wrong-group output, which is harder to notice than an error. Get the
list with `sacctmgr -nP show assoc user=$USER format=Account` on the login
node, or `get_projects(facility="roquo")` once SSH works.

**The login host has three nodes behind it.**
`login.roquo.qc.r-ccs.riken.jp` is an alias for `login1`, `login2` and
`login3`, each reachable directly as `loginN.roquo.qc.r-ccs.riken.jp`. The
alias is the right thing to put in the config; name a specific node only
if the user has a reason.

## Verifying

`hpc-doctor roquo` checks the SSH connection and that Slurm answers
(`sinfo --version`). A good first real test is a one-GPU job on the
`roquo` partition with a short wall time — `nvidia-smi -L` is enough to
prove the GPU plan landed.

Be aware when interpreting results that **modules only load on compute
nodes**, so `module avail` over `run_command_on_cluster` (which runs on
the login node) will not show what a job sees. That's expected, not a
broken setup.

## Running on ROQUO itself

If the agent is running on a ROQUO login node, set
`{"ssh": {"host": "localhost"}}` — that selects direct local execution
with no SSH at all, so no key registration is involved.

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
3. **Write the file** to `~/.hpc-agent/roquo.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor roquo
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   roquo` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest roquo
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
