cell2026 uses key-based SSH. Configure the hostname and username issued by the
lab as an SSH alias or user@host; no public hostname should be guessed. Use
`host=localhost` when the agent already runs on the head node. There are no
project/account settings.

`CELL2026_DEFAULT_SCHEDULER` may be `gridengine` (default) or `slurm`.
`CELL2026_GE_BIN` may point at the AGE binary directory when the login shell
does not put it on PATH. The optional embedding key uses the shared RIKEN
endpoint; without it, docs search falls back to BM25.
