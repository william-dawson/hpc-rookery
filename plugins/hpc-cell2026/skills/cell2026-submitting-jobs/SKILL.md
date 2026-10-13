---
name: cell2026-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on cell2026 (Shinobu Lab). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on cell2026 (Shinobu Lab)

Every tool call in this skill uses `facility="cell2026"`.

Choose between two genuinely different schedulers. `helix`, `kinase`,
`all.q`, and `gpu` route to Grid Engine; `beta`, `serine`, and `all` route to
Slurm. Omitting the selector defaults to Grid Engine `all.q`. Host selectors
are translated to the real queue plus a host constraint.

Grid Engine is the managed GPU path: request 1-2 GPUs and let the generated
script set `CUDA_VISIBLE_DEVICES` from `$SGE_HGR_gpu`. Do not set it yourself.
Choose a recorded `parallel_env`, and use no more than 32 slots for SMP/OpenMP.

Slurm has no GRES, GPU isolation, accounting, or usable memory tracking. A
one-GPU request only adds container `--nv`; it does not reserve the device.
Coordinate before heavy GPU work. Never add `--gres` or `--mem`. There is no
module system and no account on either side. Preview the selected scheduler's
script and ask permission before submission.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="cell2026", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="cell2026", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="cell2026")` (live occupancy) and
  `get_facility(facility="cell2026")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="cell2026", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
