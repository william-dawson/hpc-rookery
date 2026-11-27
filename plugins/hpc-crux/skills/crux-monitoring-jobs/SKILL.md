---
name: crux-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on Crux (ALCF), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on Crux (ALCF)

Every tool call in this skill uses `facility="crux"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="crux", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="crux", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="crux")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="crux", path=...)` for a running
  job, or `fs_view` once it has finished.

`get_job_status` reads the full `qstat -fx` record — including finished
jobs, since ALCF keeps about two weeks of history, and the exit status of a
finished job. The **`message` field comes from PBS's comment attribute**,
which is where every "why isn't it running" answer lives (insufficient
nodes, filesystem down, held for too many failed attempts, deletion
notices). Read it before diagnosing anything else.

Job output files: `<name>.o<seq>` and `<name>.e<seq>` in the directory the
job was submitted from — take `meta_data.workdir` from the status record
(usually `~/agent/jobs`) rather than assuming the home root, and read them
with `fs_tail` while running or `fs_view` once finished. `meta_data.output_path`
and `meta_data.error_path` name the exact files; `workdir` keeps working for
finished jobs too, since it falls back to the output directory when PBS
history no longer carries the submission environment.

Recent jobs (`get_job_statuses` with an empty id list) come from
`qselect`/`qstat` with full untruncated ids; the two-week window is the
ceiling. A few states worth decoding:

- A `preemptable` job reported `failed` with a comment about deletion at
  the scheduler's request was **preempted**, not crashed — and because the
  backend renders `-r y`, it requeues and will run again once the demand job
  finishes. Say that, don't declare data loss.
- A job you cancelled via `cancel_job` reports `canceled` immediately; if
  polled again before PBS finishes the deletion it may briefly show as
  `failed` with a nonzero exit status — the deletion, not the application.
- An id that returns `unknown` with a note about the routing queue means
  the job fit no execution queue and was dropped after `qsub` returned:
  check node count and walltime against `get_facility`'s queue limits
  before resubmitting.

`get_resources` returns one row per queue (job counts, from `qstat -Q`) each
carrying the machine-wide node pool (`allocated`/`idle`/`other`/`total` from
`pbsnodes`) — Crux queues share one node pool, so idle nodes mean any queue
can start. `get_drained_nodes` maps `pbsnodes -l` for down nodes.

`update_job` maps onto `qalter` (name, walltime, project, node count — and
walltime can even be lowered on a *running* job) and `qmove` (queue or
reservation changes, queued jobs only). Anything else in the spec is
reported back as not applied.

## Cancelling and updating

- `cancel_job(facility="crux", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="crux", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `crux-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="crux")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="crux", query=...)` on the `hpc-docs` server.
