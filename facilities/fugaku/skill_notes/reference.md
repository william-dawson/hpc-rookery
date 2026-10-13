Fugaku is RIKEN R-CCS's flagship: **158,976 nodes of A64FX (Arm SVE),
48 compute cores each, no GPUs anywhere in the system**, scheduled by
Fujitsu's PJM rather than Slurm.

### Orientation facts (fallback only — prefer the tools)

- **Architecture**: A64FX, Armv8.2-A + SVE 512-bit. x86_64 binaries,
  containers and wheels will not run. Cross-compilation is the norm — see
  the `{{SLUG}}-build` skill, which covers the four verified toolchains.
- **Scheduler**: PJM. `pjsub` submits, `pjstat` queries, `pjdel` cancels,
  `pjalter` changes a queued job's elapse limit. There is no `sacct`,
  `squeue`, or `sacctmgr`; nevertheless, `get_projects` lists the current
  user's PJM groups through `id -Gn`, and `get_project_allocations` reports
  a group's Fugaku Points from `accountj_pt` when that group has point
  accounting. PJM exposes no separately verified per-user point share.
- **Resource groups** (the PJM equivalent of a partition): `small`
  (1–384 nodes, ≤72h), `large` (385+ nodes, ≤24h), `int` (interactive),
  `f-pt` (priority, **consumes Fugaku Points**), `spot-*` (low priority).
  Which ones an account may use depends on its project — confirm with
  `pjacl --rg <name>` rather than assuming.
- **Project group is mandatory** on every job, and the shared `fugaku`
  group cannot submit. A `trial` (Startup Project) group can only use
  `spot-*` groups.
- **Storage is layered**: `$HOME` on the first layer; second-layer volumes
  (`/vol####`) must be declared per job via `PJM_LLIO_GFSCACHE`. Spack
  lives on second-layer storage too, so jobs using it need the declaration.
- **Output**: `<name>.<job_id>.out`/`.err` in the submission directory, and
  for MPI jobs the per-rank output lands under `output.<jobid>/` in the
  working directory instead — see `{{SLUG}}-monitoring-jobs`.

### Getting help

Point users at RIKEN R-CCS's Fugaku support desk; this plugin cites no
documentation URL, since there's no confirmed-stable public page to send
people to.
