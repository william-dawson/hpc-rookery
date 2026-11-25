hpz is reached with key-based SSH through an `ai-hpz` alias in
`~/.ssh/config` (HostName, User and IdentityFile issued by the machine's
administrator). The alias must work without a password or passphrase prompt:
`ssh ai-hpz hostname` should print `hpz`. Do not guess the IP address or
user name; ask the user to copy them from the administrator's instructions.

No project/account setting exists — Slurm on hpz has no accounting, and a
configured account would be rejected. If the agent runs on hpz itself, use
`"host": "localhost"`.

After writing the config, prove access with `get_resources` (it should list
the single `debug` partition). `get_projects` is unsupported on hpz, so do not
use it as a connectivity check.
