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
  `get_projects(facility="{{SLUG}}")` has shown the user's real projects. It
  is a convenience, not a licence to submit: every job still passes an
  explicit account.
- `defaults.filesystems` — the normal Bridge `-m` list. `scratch,work` for
  ordinary jobs, `scratch,store` when reading or writing STORE, and
  `scratch,work,store` when all three are needed.

`{{ENV_PREFIX}}_HOST`, `{{ENV_PREFIX}}_ACCOUNT`, `{{ENV_PREFIX}}_FILESYSTEMS`
and `{{ENV_PREFIX}}_CONFIG` override the file.

## What a healthy check looks like

`hpc-doctor {{SLUG}}` should read `✓` throughout except embedding, which reads
`!` rather than `✗`: no shared embedding endpoint is configured for Irene, so
docs search runs on BM25 keyword matching. That is expected, not a fault.
