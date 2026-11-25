---
name: ai-hpz-demo
description: Interactive demo of ai-hpz (hpz workstation) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# ai-hpz (hpz workstation) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="ai-hpz"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="ai-hpz")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="ai-hpz")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `ai-hpz-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="ai-hpz")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="ai-hpz", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="ai-hpz", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="ai-hpz", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="ai-hpz", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="ai-hpz", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="ai-hpz", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="ai-hpz", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/ai-hpz-submitting-jobs`, monitor
existing jobs via `/ai-hpz-monitoring-jobs`, or ask about the machine via
`/ai-hpz-reference`.

## Facility notes for this demo

**Connectivity check on hpz:** `get_projects` is unsupported here (no Slurm
accounting) and always errors with "does not support". Use
`get_resources(facility="ai-hpz")` instead to prove SSH works; only stop if
*that* fails.

Lead with what makes hpz different: a single workstation, one `debug`
partition, a single GPU (Quadro RTX 5000) that jobs reserve with `gpus=1`, and GROMACS
2026 with CUDA as the main workload. Show `get_facility` facts and a docs
search such as "GROMACS GPU mdrun threads". Keep the demo read-only unless
the user asks for a job.

If a job is requested, preview a tiny CPU job (e.g. `hostname` with
`cpu_cores_per_process=1`, `duration=300`) and ask before submitting. Offer a
short `gmx --version` job with `gpus=1` as the GROMACS/GPU check.
