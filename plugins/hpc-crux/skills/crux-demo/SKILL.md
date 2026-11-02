---
name: crux-demo
description: Interactive demo of Crux (ALCF) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# Crux (ALCF) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="crux"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="crux")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="crux")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `crux-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="crux")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="crux", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="crux", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="crux", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="crux", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="crux", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="crux", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="crux", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/crux-submitting-jobs`, monitor
existing jobs via `/crux-monitoring-jobs`, or ask about the machine via
`/crux-reference`.

## Facility notes for this demo

Start by explaining the connection model: Crux is normally reached over a
multiplexed SSH master the user authenticated once with their one-time
passcode (`host` = that ssh alias), or directly on an access node with
`host=localhost`. If the master has expired, the demo's SSH-dependent steps
will fail with permission denied — have the user re-run `ssh -MNf crux`
rather than asking for the passcode.

`get_projects` is the natural "prove the connection works" call here: it
runs sbank on the login node and returns the user's chargeable ALCF projects
with their remaining node-hour balances — worth showing as a table.

For the Step 6 test job, a one-node `debug` job is right (the queue exists
for exactly this): 1 node, 10 minutes, the user's configured account,
`executable="echo"` with a marker argument. Note that `workq-route` would
also work but may queue behind production work; `debug` has at most one
running job per user, so a previous demo job must be finished first.

The port is live-validated (2026-11-02: doctor, read-only smoke, and real
one-node debug jobs end to end) — but if any step behaves in a way the
skill notes didn't predict, report the mismatch rather than improvising an
explanation.
