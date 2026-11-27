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
