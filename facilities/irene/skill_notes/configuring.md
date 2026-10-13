Use the Irene SSH destination from the user's TGCC project documentation;
prefer an existing `irene` alias or the issued user@host. If authentication
needs a password file, configure it as `computer.passfile`, not
`ssh.passfile`. Use `host=localhost` only when the agent is already on an Irene
front end.

Set `defaults.account` only after `get_projects(facility="{{SLUG}}")` has shown
the user's real TGCC project, and set `defaults.filesystems` to the normal
Bridge `-m` list (`scratch,work` for ordinary jobs). `IRENE_ACCOUNT` and
`IRENE_FILESYSTEMS` override the file. Docs search is BM25-only because no
shared Irene embedding endpoint is verified.
