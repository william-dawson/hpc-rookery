---
name: octopus-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on Octopus (RIKEN R-CCS). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on Octopus (RIKEN R-CCS)

Every tool call in this skill uses `facility="octopus"`.

Octopus is GPU-only and dual-vendor. Choose the software target first:

- NVIDIA CUDA/NVHPC -> `h200` (up to 8h) or `h200-long`.
- AMD ROCm -> `mi300x` (up to 8h) or `mi300x-long`.

Every current partition is recorded as allowing single-node jobs with 1-8
GPUs, 192 CPU cores, and 2,317,610 MiB usable memory. With that enforced
one-node shape, `resources.gpus` renders as `--gres=gpu:N`. A partial spec
defaults to one H200 GPU. Containers receive `--nv` or `--rocm`
automatically from the partition.

Normally omit `attributes.account`; Slurm applies the user's
`DefaultAccount`. If the user needs a different project, call
`get_projects(facility="octopus")` and use one of the returned associations.
Never copy an account name from an example.

The source port was checked offline but not against live Octopus. Run a tiny
H200 and MI300X job when access returns before treating the integration as
live-validated.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="octopus", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="octopus", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="octopus")` (live occupancy) and
  `get_facility(facility="octopus")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="octopus", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
