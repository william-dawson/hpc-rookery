---
name: cell2026-demo
description: Interactive demo of cell2026 (Shinobu Lab) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# cell2026 (Shinobu Lab) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="cell2026"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="cell2026")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="cell2026")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `cell2026-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="cell2026")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="cell2026", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="cell2026", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="cell2026", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="cell2026", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="cell2026", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="cell2026", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="cell2026", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/cell2026-submitting-jobs`, monitor
existing jobs via `/cell2026-monitoring-jobs`, or ask about the machine via
`/cell2026-reference`.

## Facility notes for this demo

Explain and show both halves: Grid Engine on helix/kinase with managed RTX
A4000 assignment and durable qacct, then Slurm on beta/serine with unmanaged
GPUs and ephemeral history. Present static facts, merged live resources, a docs
search, and the filesystem without changing state.

If the user wants jobs, preview them separately and ask before each allocation:
a tiny one-GPU Grid Engine job that prints `$CUDA_VISIBLE_DEVICES`, and a tiny
CPU-only Slurm job pinned to beta. Do not imply that Slurm `gpus=1` reserves its
GPU. Retrieve each scheduler's output and explain the history difference.
Raw commands use the remote-command skill's preview, permission, and recap.
