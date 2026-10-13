---
name: tsubame-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on TSUBAME4.0 (Science Tokyo). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on TSUBAME4.0 (Science Tokyo)

Every tool call in this skill uses `facility="tsubame"`.

Choose a TSUBAME resource type first. Put it in
`attributes.custom_attributes.resource_type` and use `resources.node_count` as
the number of fixed units. The resource type—not generic `gpus` or `memory`—sets
cores, memory, GPUs, and scratch. A partial spec defaults to `node_f`, priority
`-5`, and either the configured group or the free trial.

The free trial has no account and is limited to two units and three minutes.
For normal work, use a group returned by `get_projects`; never copy one from an
example. Normal jobs leave `queue_name` blank. The only evidenced explicit queue
is the subscription queue `prior`. The maximum wall time is 24 hours.

The scheduler request does not create an MPI launch line. Set `launcher`
explicitly for parallel jobs and make ranks per unit times threads per rank fit
the chosen type. With inherited environments, include `module purge` before
loading modules. Preview the generated script and ask permission before a real
submission.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="tsubame", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="tsubame", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="tsubame")` (live occupancy) and
  `get_facility(facility="tsubame")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="tsubame", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
