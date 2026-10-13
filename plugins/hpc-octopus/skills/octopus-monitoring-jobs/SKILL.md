---
name: octopus-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on Octopus (RIKEN R-CCS), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on Octopus (RIKEN R-CCS)

Every tool call in this skill uses `facility="octopus"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="octopus", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="octopus", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="octopus")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="octopus", path=...)` for a running
  job, or `fs_view` once it has finished.

Octopus has Slurm accounting: `get_job_status` and recent history use `sacct`,
while queued jobs gain a live `squeue` wait reason. `get_resources` reports
partition occupancy, and `get_drained_nodes` reports unavailable nodes.

For failures, first compare partition and toolchain: CUDA belongs on `h200*`
and ROCm on `mi300x*`. `TIMEOUT` on a non-long partition points to its
matching `-long` queue; GPU-less containers should show `--nv` for H200 or
`--rocm` for MI300X in the retained script. Raw `nvidia-smi`, `rocm-smi`, or
job-step commands require the remote-command preview and permission workflow.

## Cancelling and updating

- `cancel_job(facility="octopus", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="octopus", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `octopus-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="octopus")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="octopus", query=...)` on the `hpc-docs` server.
