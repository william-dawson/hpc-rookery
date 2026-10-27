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
node, or `get_projects(facility="{{SLUG}}")` once SSH works.

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
