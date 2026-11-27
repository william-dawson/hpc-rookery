---
name: ai-naur-demo
description: Interactive demo of ai-Naur (Naur GB300 node) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# ai-Naur (Naur GB300 node) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="ai-naur"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="ai-naur")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="ai-naur")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `ai-naur-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="ai-naur")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="ai-naur", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="ai-naur", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="ai-naur", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="ai-naur", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="ai-naur", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="ai-naur", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="ai-naur", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/ai-naur-submitting-jobs`, monitor
existing jobs via `/ai-naur-monitoring-jobs`, or ask about the machine via
`/ai-naur-reference`.

## Facility notes for this demo

**Connectivity check on naur:** `get_projects` is unsupported here (no
working Slurm accounting) and always errors with "does not support". Use
`get_resources(facility="ai-naur")` instead to prove SSH works; only stop if
*that* fails.

Lead with what makes naur different: an Arm (aarch64) host with 72
Neoverse-V2 cores, ~744 GiB of memory and a single NVIDIA GB300 GPU with
~251 GiB that jobs reserve with `gpus=1`; the NVIDIA HPC SDK 26.9 and CUDA
13.2 as modules. Show `get_facility` facts and a docs search such as
"request the GPU" or "why can't I set memory". Mention that `get_resources`
also lists `prado`, `shannon` and `backus` — other machines in the same
Slurm, not part of this facility. Keep the demo read-only unless the user
asks for a job.

If a job is requested, preview a tiny CPU job (e.g. `hostname` with
`cpu_cores_per_process=1`, `duration=300`, no `memory`) and ask before
submitting. Offer a short `nvidia-smi` job with `gpus=1` as the GPU check.
