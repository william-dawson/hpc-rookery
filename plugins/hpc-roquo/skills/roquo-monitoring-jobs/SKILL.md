---
name: roquo-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on ROQUO (RIKEN R-CCS), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on ROQUO (RIKEN R-CCS)

Every tool call in this skill uses `facility="roquo"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="roquo", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="roquo", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="roquo")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="roquo", path=...)` for a running
  job, or `fs_view` once it has finished.

## Accounting is available

ROQUO runs Slurm with accounting, so job history is queryable, not just
the live queue. `get_job_status` / `get_job_statuses` work for finished
jobs, and the underlying `sacct -j <jobid> -o
JobID,State,ExitCode,Elapsed,MaxRSS` is what the manual points users at
for a post-mortem.

## Queue reasons that mean something specific here

**`QOSMaxWallDurationPerJobLimit` on a `work` job** — the job asked for
more than 3 days without `qos: long`. It will **never start**. Nothing
rejected it at submit time, so it looks like an ordinary wait. If you see
this reason, stop waiting and resubmit; `submit_job` through this plugin
refuses the combination up front, so a job in this state was almost
certainly submitted by hand.

**A `roquo` job waiting with `--switches=1`** — the topology request waits
up to five minutes for nodes inside one rack before giving up and spanning
racks. A short wait here is normal and self-resolving.

## Finding a job's output

Jobs commonly write to `%x_%j.log` relative to the submission directory.
If a job wrote results to `$SLURM_SCRATCH` (`/scratch/<jobid>`), **they
are gone** — that area is node-local and deleted when the job ends. When a
user can't find output from a completed job, this is the first thing to
check, and the only fix is to resubmit with the copy-out step added.

## Node names

Compute nodes are `qrNNnMM` (rack `qr01`–`qr08`, e.g. `qr01n01`); `work`
nodes are `work01`–`work05`. A node name tells you which partition a job
actually ran on, which matters because the two have different
architectures — if something behaved oddly, confirming it ran on `qr*` vs
`work*` is a fast way to catch an architecture mismatch.

`get_drained_nodes(facility="roquo")` reports nodes Slurm has taken out
of service, which is worth checking before concluding a partition is
simply busy.

## Cancelling and updating

- `cancel_job(facility="roquo", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="roquo", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `roquo-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="roquo")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="roquo", query=...)` on the `hpc-docs` server.
