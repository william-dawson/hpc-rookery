---
name: irene-demo
description: Interactive demo of Irene (CEA TGCC) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# Irene (CEA TGCC) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="irene"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="irene")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="irene")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `irene-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="irene")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="irene", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="irene", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="irene", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="irene", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="irene", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="irene", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="irene", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/irene-submitting-jobs`, monitor
existing jobs via `/irene-monitoring-jobs`, or ask about the machine via
`/irene-reference`.

## Facility notes for this demo

Lead with Irene's defining fact: normal jobs are CPU/MPI work on `rome`, and
the public scheduler interface is Bridge rather than raw Slurm. Show static
partitions, live `ccc_mpinfo` occupancy, the user's project associations, a
documentation search, and a home-directory listing. Keep this overview
read-only.

If the user requests a test job, preview a one-task, five-minute `rome` spec
using a project returned by `get_projects` and the configured filesystem list,
then ask before submission. Poll no faster than TGCC policy allows and inspect
`irene_<job-id>.o` after completion. Raw commands follow the remote-command
skill's preview, permission, and recap workflow.
