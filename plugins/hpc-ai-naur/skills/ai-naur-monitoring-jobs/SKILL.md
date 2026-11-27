---
name: ai-naur-monitoring-jobs
description: Use when the user asks about the status, progress, output, history, or failure of jobs on ai-Naur (Naur GB300 node), or about queue and node availability. Also use this any time you (the agent) need to check on or wait for a job you submitted, even without a fresh user request.
user-invocable: true
---

# Monitoring jobs on ai-Naur (Naur GB300 node)

Every tool call in this skill uses `facility="ai-naur"`.

## Status checks (same tools and semantics everywhere)

Use these tools even when you're checking in on your own initiative — don't
fall back to `run_command_on_cluster` with raw `squeue`/`sacct` just
because there's no new user message prompting it; the tools below return
the same information normalized, plus any facility-specific lag/quirk
handling noted below.

- **One job**: `get_job_status(facility="ai-naur", job_id=...)` — `state`
  is normalized (`queued`/`active`/`completed`/`failed`/`canceled`/`held`/
  `unknown`); `meta_data.native_state` is the scheduler's own. A queued
  job's `message` explains the wait.
- **My recent jobs**: `get_job_statuses(facility="ai-naur", job_ids=[])`
  for roughly the last two days, or pass specific IDs.
- **Cluster availability**: `get_resources(facility="ai-naur")` —
  per-partition allocated/idle/other/total node counts. Idle nodes can
  start jobs immediately.
- **Reading a job's output**: the file is `slurm-<job_id>.out` inside the
  directory the job ran in. **Get that directory from the job's own status
  record** (`meta_data.workdir`) rather than assuming `$HOME` — a job whose
  spec set `directory` writes its output there, not in the home directory.
  Then read it with `fs_tail(facility="ai-naur", path=...)` for a running
  job, or `fs_view` once it has finished.

naur's Slurm has **no working accounting** (`sacct` fails with a refused
connection), which limits what monitoring can show:

- `get_job_status` reads `squeue` while a job is pending or running, then
  `scontrol show job` for about five minutes after it ends. Once Slurm
  forgets the job, the status becomes UNKNOWN / "not found" — that is
  expected, not a failure. Read the job's stdout/stderr with `fs_tail`
  instead.
- `get_job_statuses` with an empty id list shows only the current live
  queue; there is no multi-day history.
- `get_resources` and `get_drained_nodes` work (sinfo), but they report the
  whole Slurm cluster: `prado`, `shannon` and `backus` are other machines.
  Only the `naur` row matters here, and a down sibling node (e.g. `backus`)
  does not affect naur jobs. `get_projects` and the allocation tools are
  unsupported.

So check a job promptly after it finishes if the exit code matters, and
always point the user at the output files.

Common naur failures:

- `Requested node configuration is not available` at submit — a memory
  request (never allowed here), more than one GPU, more than 72 CPUs, or
  more than one node.
- `No devices found` / CUDA finds no GPU — the job did not set `gpus=1`.
  Slurm hides the GPU from jobs that did not request it.
- GPU job pending with reason `Resources` — another job holds the single
  GPU; it starts when that job ends.
- CPU job pending with reason `Resources` — other jobs hold the cores; lower
  the request or wait.
- `nvcc` / `nvc` / `mpirun: command not found` — add `module load cuda-13.2`
  or `module load nvhpc/26.9` to `pre_launch`.
- `Exec format error` — an x86 binary was brought to this Arm host; rebuild
  it on naur.
- Out-of-memory kills with no Slurm message — memory is not limited per job,
  so another job may have exhausted the node. Ask the user before inspecting
  with `free`/`top` (remote-command workflow).

## Cancelling and updating

- `cancel_job(facility="ai-naur", job_id=...)` — **confirm with the user
  before calling this.**
- `update_job(facility="ai-naur", job_id=..., spec={...})` — pass a
  JobSpec containing only what should change, e.g.
  `{"attributes": {"duration": "02:00:00"}}`. Only fields a scheduler can
  change after submission are applied (job name, wall time, partition,
  account, reservation, node count); anything else you set is reported back
  as not applied. Only affects jobs still queued or running.

## Polling until done, from a notebook

Interactively, just call `get_job_status` again after a pause. If you're
writing a reproducible notebook instead (see `ai-naur-reproducing`), use
`hpc_agent_core.client`'s `wait_for_job(job_id, facility="ai-naur")`
rather than a hand-rolled polling loop.

Don't guess facility-specific failure modes beyond what's noted above — use
`search_docs(facility="ai-naur", query=...)` on the `hpc-docs` server.
