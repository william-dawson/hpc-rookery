---
name: irene-configuring
description: Use when the user wants to set up, configure, or troubleshoot Irene (CEA TGCC) — SSH access, the embedding endpoint for docs search (RAG), or the ~/.hpc-agent/irene.json file. Also use when irene tools fail with connection or embedding errors.
---

# Configuring Irene (CEA TGCC)

Settings live in `~/.hpc-agent/irene.json` (the common directory
shared by every facility this plugin serves — one file per facility). Env
vars `IRENE_HOST` and `IRENE_EMBED_API_KEY` override the
file; the embedding key also falls back to a shared `RCCS_EMBED_API_KEY`
env var if several facilities share the same endpoint.

The file this facility needs (add `"embedding": {"api_key": "..."}` too if
docs search should use vector rather than keyword matching):

```json
{
  "ssh": {
    "host": "irene"
  },
  "computer": {
    "passfile": "/path/to/local/password-file-if-needed"
  },
  "defaults": {
    "account": "<your-TGCC-project>",
    "filesystems": "scratch,work"
  }
}
```

## What must be true before it can connect

Use the Irene SSH destination issued in your TGCC project
documentation; no public hostname is assumed here. Prefer an
existing 'irene' alias in ~/.ssh/config, or set ssh.host to the
issued user@host. If the account needs password-file authentication,
put that local path under computer.passfile (not ssh.passfile).
Set defaults.account only to a project returned by get_projects;
Bridge checks that project against the requested partition before
submitting. defaults.filesystems supplies mandatory #MSUB -m and
normally starts as scratch,work. IRENE_ACCOUNT and
IRENE_FILESYSTEMS override those values. Use host=localhost when
already running on an Irene front end.

## Guided setup — interview the user, then write the file

Read the existing `~/.hpc-agent/irene.json` first and only ask
about what's missing or being changed.

1. **SSH** — ask how they reach this facility's login node:

Use the Irene SSH destination from the user's TGCC project documentation;
prefer an existing `irene` alias in `~/.ssh/config`, otherwise the issued
`user@host`. Access details live in site and project documentation, not in
any public guide, so ask rather than guessing a hostname.

**If SSH needs a password, set `computer.passfile`** to a local file holding
it — not `ssh.passfile`, which is not read. This is Irene's most common
configuration mistake.

Use `host=localhost` only when the agent is already running on an Irene front
end; that path uses no SSH at all and needs no key or passfile.

## Settings that matter here

- `defaults.account` — a remembered TGCC project. Set it only after
  `get_projects(facility="irene")` has shown the user's real projects. It
  is a convenience, not a licence to submit: every job still passes an
  explicit account.
- `defaults.filesystems` — the normal Bridge `-m` list. `scratch,work` for
  ordinary jobs, `scratch,store` when reading or writing STORE, and
  `scratch,work,store` when all three are needed.

`IRENE_HOST`, `IRENE_ACCOUNT`, `IRENE_FILESYSTEMS`
and `IRENE_CONFIG` override the file.

## What a healthy check looks like

`hpc-doctor irene` should read `✓` throughout except embedding, which reads
`!` rather than `✗`: no shared embedding endpoint is configured for Irene, so
docs search runs on BM25 keyword matching. That is expected, not a fault.

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
3. **Write the file** to `~/.hpc-agent/irene.json` (`mkdir -p
   ~/.hpc-agent` first if needed), then `chmod 600` it — it may hold an API
   key. Never commit it or echo the key back in conversation.
4. **Validate**:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main hpc-doctor irene
   ```
   (From a checkout of this repo: `.venv/bin/python -m hpc_mcp.doctor
   irene` also works.)
5. **If the embedding endpoint was added or changed**, rebuild this
   facility's docs index:
   ```bash
   uv tool run --quiet --from git+https://github.com/william-dawson/hpc-rookery.git@main python -m hpc_mcp.ingest irene
   ```
   Then run the doctor again — it should report "chunks with embeddings".

## Notes

- Settings are read fresh on every tool call, so a config file edit
  (including switching `ssh.host` to/from `"localhost"`) applies
  immediately — no server restart needed. A rebuilt docs index still needs
  the `hpc-docs` server restarted to be picked up.
- Off-network or without a key, docs search transparently falls back to
  BM25 keyword search over the same content — the plugin still works.
