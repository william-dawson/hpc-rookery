---
name: irene-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on Irene (CEA TGCC). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on Irene (CEA TGCC)

Every tool call in this skill uses `facility="irene"`.

Default ordinary CPU/MPI work to `rome`. Use `xlarge` for large single-node
memory and the `v100` family only for GPU-capable software.

Every Irene job needs a partition (`queue_name`), a TGCC project (`account`),
and filesystems (`custom_attributes.filesystems`, normally `scratch,work`). If
the project was not already chosen in config or by the user, call
`get_projects` and ask which association to charge. The backend rechecks that
project/partition pair through `ccc_compuse` at submission time.

Use `process_count` for total Bridge tasks, `cpu_cores_per_process` for cores
per task, and `ccc_mprun` as the launcher. GPU allocation is derived from the
live CpN/GpN core ratio, so inspect `get_resources` when the shape is not
obvious. Containers use a pcocc image name and render as `ccc_mprun -C`.
Preview the `#MSUB` script and ask permission before submitting.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="irene", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="irene", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="irene")` (live occupancy) and
  `get_facility(facility="irene")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="irene", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
