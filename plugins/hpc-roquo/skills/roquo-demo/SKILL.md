---
name: roquo-demo
description: Interactive demo of ROQUO (RIKEN R-CCS) — walks through configuration, facility info, live cluster status, docs search, filesystem access, and a real job end to end.
user-invocable: true
---

# ROQUO (RIKEN R-CCS) demo

Run each step in order — actually call the tools, don't just describe the
plan. Present results as a readable narrative, not raw JSON dumps. Use
markdown headers and tables to make it scannable. Pause after each step and
show the output before moving on. Every tool call uses `facility="roquo"`.

## Step 1 — Confirm it's configured

Call `get_facility(facility="roquo")` — it needs no SSH and returns this
machine's static facts, so a good result proves config parsing works.
Summarize the partitions, storage tiers, and modules.

Then call `get_projects(facility="roquo")` to prove SSH is actually
reachable, and show which projects can be billed.

**If either call reports that the facility isn't configured, stop the demo
and switch to the `roquo-configuring` skill.** The error itself contains
the full setup directions for this machine — walk the user through those
rather than continuing.

## Step 2 — Live cluster status

Call `get_resources(facility="roquo")`. Show a table of partitions with
allocated/idle/total nodes, and point out where a job would start soonest.

## Step 3 — Documentation search

Call `search_docs(facility="roquo", query="how do I submit a job")` on
the `hpc-docs` server. Show the top result and cite its section breadcrumb.

## Step 4 — Filesystem

Call `fs_ls(facility="roquo", path=".")` to show the top of the user's
home directory on this machine.

## Step 5 — Recent jobs

Call `get_job_statuses(facility="roquo", job_ids=[])` (an empty list
means "the last ~2 days"). If there are jobs, show them as a table: job ID,
name, state, partition, elapsed — and highlight any failed ones, offering to
investigate. If there are none, say so and move on.

## Step 6 — Submit a test job

Tell the user you'll submit a short test job to verify end-to-end
submission, then call `render_job_script(facility="roquo", spec=...)` to
show exactly what will run, then `submit_job` with the same spec. Show the
returned job ID and script path. See the facility notes below for a spec
that suits this machine.

## Step 7 — Monitor and read the output

Poll `get_job_status(facility="roquo", job_id=...)` every ~15 seconds —
use `run_command_on_cluster(facility="roquo", command="sleep 15")` as the
wait, since there's no sleep tool. Stop when the state is terminal, or after
about five polls (tell the user to check back later if it's still queued).

Once it finishes, read the output: take `meta_data.workdir` from the final
status and call
`fs_tail(facility="roquo", path="<workdir>/slurm-<job_id>.out")`. Don't
assume the home directory — a job that set `directory` writes its output
there instead.

## Closing

Summarize in four bullets: configuration and facility checked, live status
seen, a job submitted and monitored, and its output retrieved. Then invite
the user to submit real work via `/roquo-submitting-jobs`, monitor
existing jobs via `/roquo-monitoring-jobs`, or ask about the machine via
`/roquo-reference`.

## Facility notes for this demo

**Billing warning for Step 6.** ROQUO bills GPU time to a project, so tell
the user what the test job will cost them in wall time before submitting,
and let them decline. Use the smallest useful shape: one GPU, five
minutes.

Suggested spec:

```json
{
  "name": "roquo-demo",
  "executable": "nvidia-smi",
  "arguments": ["-L"],
  "resources": {"gpus": 1},
  "attributes": {
    "queue_name": "roquo",
    "account": "<project>",
    "duration": 300
  }
}
```

`nvidia-smi -L` is a good demo payload here: it proves the aarch64 compute
node, the GPU allocation, and the `qtr` node plan all worked, in one line
of output.

**`attributes.account` is not optional in practice.** ROQUO accepts a job
without it and charges a restrictive default account, which also becomes
the owning group of any file the job writes — so the demo should resolve a
real project in Step 1 (`get_projects`) and pass it. If the user belongs
to several, ask which to charge rather than picking one. If Step 1's
`get_projects` fails, that is the SSH check failing; follow the template's
instruction and switch to `roquo-configuring`.

**A note for Step 2.** `get_resources` shows two partitions, `roquo` and
`work`, and they are different architectures (aarch64 vs x86_64) rather
than two sizes of the same thing. Worth saying out loud when presenting
the table, because it's the single most consequential fact about this
machine.

**A note for Step 7.** The script writes to the submission directory by
default. If the job had written to `$SLURM_SCRATCH`, the output would be
gone the moment it finished — mention that when showing where output
lives, since it's the most common way people lose results here.
