---
name: ai-hpz-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on ai-hpz (hpz workstation), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on ai-hpz (hpz workstation)

Every tool call in this skill uses `facility="ai-hpz"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="ai-hpz", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="ai-hpz", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="ai-hpz")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="ai-hpz", path=...)` for a running
  job, or `fs_view` once it has finished.

hpz's Slurm has **no accounting**, which limits what monitoring can show:

- `get_job_status` reads `squeue` while a job is pending or running, then
  `scontrol show job` for a short time after it ends. Once Slurm forgets the
  job, the status becomes UNKNOWN / "not found" — that is expected, not a
  failure. Read the job's stdout/stderr with `fs_tail` instead.
- `get_job_statuses` with an empty id list shows only the current live
  queue; there is no multi-day history.
- `get_resources` and `get_drained_nodes` work (sinfo). `get_projects` and the
  allocation tools are unsupported.

So check a job promptly after it finishes if the exit code matters, and
always point the user at the output files.

Common hpz failures:

- GPU job pending with reason `Resources` — another job holds the single
  GPU; it starts when that job ends.
- `Requested node configuration is not available` at submit — more than
  one GPU, or more CPUs/memory than the node has.
- GROMACS GPU out-of-memory or very slow — some job is using the GPU
  without having requested it (Slurm does not block that). Ask the user
  before inspecting with `nvidia-smi` (remote-command workflow).
- Pending with reason `Resources` — other jobs hold the CPUs/memory; lower
  the request or wait.
- `gmx: command not found` / `nvcc: command not found` — add
  `source /usr/local/gromacs/bin/GMXRC` or the HPC SDK `module use`/`module
  load` lines to `pre_launch`.

## Cancelling and updating

- `cancel_job(facility="ai-hpz", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="ai-hpz", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `ai-hpz-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="ai-hpz")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="ai-hpz", query=...)` on the `hpc-docs` server.
