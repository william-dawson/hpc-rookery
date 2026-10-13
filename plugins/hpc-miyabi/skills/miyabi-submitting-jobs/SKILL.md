---
name: miyabi-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on Miyabi (JCAHPC). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on Miyabi (JCAHPC)

Every tool call in this skill uses `facility="miyabi"`.

Miyabi runs PBS Professional. There is no safe queue default: choose among
CPU (`-c`), full GH200 (`-g`), and MIG (`-mig`) queues after checking
`get_resources(facility="miyabi")` and the current limits in the bundled
guide.

Every job needs `attributes.account`, rendered as
`#PBS -W group_list=<project>`. If the user omits it, the backend reads their
own `defaults.group`/`MIYABI_GROUP`; it never guesses or bundles a real group.

Resource mapping:

- `node_count` -> PBS `select` chunks (nodes on `-c`/`-g`, MIG instances on
  `-mig`).
- `processes_per_node` -> `mpiprocs`.
- `cpu_cores_per_process` -> `ompthreads`.
- `memory` -> per-chunk `mem=<N>gb`.

Full-GPU and MIG allocation is selected by the queue, not a PBS GPU flag.
Leave `resources.gpus=0`, or make it equal `node_count`. Use debug queues only
for short validation jobs. The earlier port smoke-tested C OpenMP, one- and
two-node C MPI, one full G node, and one `2g.24gb` MIG instance on 2026-07-13;
this hub port still needs a new live job when access returns.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="miyabi", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="miyabi", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="miyabi")` (live occupancy) and
  `get_facility(facility="miyabi")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="miyabi", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
