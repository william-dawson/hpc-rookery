---
name: irene-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on Irene (CEA TGCC), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on Irene (CEA TGCC)

Every tool call in this skill uses `facility="irene"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="irene", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="irene", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="irene")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="irene", path=...)` for a running
  job, or `fs_view` once it has finished.

Use `get_job_status` for a specific job and `get_job_statuses` for several or
for the user's live queue. The backend reads `ccc_mpp -u $USER` for
pending/running jobs and falls back to `ccc_macct <job-id>` for finished ones.
The recent-jobs tool returns only the live queue, because Bridge has no
date-window history query — a finished job must be asked for by ID.

Default output files are `irene_<job-id>.o` and `irene_<job-id>.e` in the
submission directory, unless the spec set explicit stdout/stderr paths.
Inspect those with `fs_tail` or `fs_view` alongside native accounting before
diagnosing a failure.

## Prefer the tools over the raw commands

Each of these has a tool that records the action properly; reach for the raw
command only to see something the tools do not expose.

| Bridge command | use instead |
|---|---|
| `ccc_mpp -u $USER` | `get_job_statuses` |
| `ccc_macct <job-id>` | `get_job_status` on a finished job |
| `ccc_mdel <job-id>` | `cancel_job` |
| `ccc_malter -T <seconds> <job-id>` | `update_job` with a new duration |

`ccc_mstat -u` gives a more detailed live view than `ccc_mpp` and has no tool
equivalent, so it is a reasonable raw query. Only time-limit changes are
verified through `ccc_malter`; confirm with the user before cancelling
anything.

## Polling policy is a site rule, not a preference

TGCC asks for no more than roughly one or two aggregate scheduler queries per
minute and **explicitly prohibits `watch`** on scheduler or Bridge commands.
When waiting on a job, poll by ID at that cadence and say so, rather than
tightening the loop because an answer is slow to arrive.

## Consumption affects scheduling

`ccc_myproject` shows project consumption and `ccc_compuse` fair-share
standing. Both directions have consequences worth telling a user about:
under-consumption can get awarded hours reduced for some project types, while
over-consumption lowers priority and can leave jobs running only as bonus
jobs. If a job is queued far longer than its size suggests, standing is worth
checking before blaming the queue.

## Cancelling and updating

- `cancel_job(facility="irene", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="irene", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `irene-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="irene")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="irene", query=...)` on the `hpc-docs` server.
