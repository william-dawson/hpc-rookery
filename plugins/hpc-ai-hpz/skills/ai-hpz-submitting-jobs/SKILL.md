---
name: ai-hpz-submitting-jobs
description: Use when the user wants to run, submit, or launch a job on ai-hpz (hpz workstation). Covers partition/queue selection, JobSpec construction, submission, and known gotchas specific to this facility.
user-invocable: true
---

# Submitting jobs on ai-hpz (hpz workstation)

Every tool call in this skill uses `facility="ai-hpz"`.

hpz is a single workstation with one Slurm partition, `debug` (the default,
no time limit). A partial spec gets `queue_name="debug"` filled in; any other
partition is rejected. Keep `node_count=1` and never set `attributes.account`
— Slurm here has no accounting.

**Resources are shared per job.** Slurm allocates cores and memory per job,
24 CPUs (12 cores × 2 threads) and 192,117 MiB in total. Request what the job
actually uses (`cpu_cores_per_process`, `memory`) so other users' jobs can run
alongside.

**The GPU is a Slurm GRES.** There is one Quadro RTX 5000 (16 GiB, sm_75).
Set `resources.gpus=1` for any job that uses it; it renders as
`--gres=gpu:1`, reserves the GPU (a second GPU job pends with `Resources`)
and sets `CUDA_VISIBLE_DEVICES=0`. `gpus` above 1 is rejected. Slurm does
not hide the GPU from jobs that did not request it, so never run GPU code
with `gpus` unset — it would collide with the job that holds the
reservation.

**No containers.** There is no Singularity/Apptainer, so `spec.container` is
rejected. Use the host software.

### GROMACS (the main workload)

GROMACS 2026.3, mixed precision, CUDA (sm_75), AVX-512, **thread-MPI only**
— there is no `gmx_mpi`. Never wrap it in `mpirun` or `srun -n N`; run one
process and size threads with `-ntmpi`/`-ntomp`.

Recommended single-GPU shape: `gpus=1`, `processes_per_node=1`,
`cpu_cores_per_process=8` (up to 24), and

```
pre_launch: source /usr/local/gromacs/bin/GMXRC
executable: gmx
arguments:  ["mdrun", "-deffnm", "md", "-ntmpi", "1",
             "-ntomp", "8", "-nb", "gpu", "-pme", "gpu",
             "-bonded", "gpu", "-update", "gpu"]
```

Keep `-ntomp` equal to `cpu_cores_per_process`. Add `-pin on` only if the
job asked for all 24 CPUs; otherwise concurrent jobs pin onto the same cores.
`gmx grompp` preprocessing is quick and can run in the same job before
`mdrun` (use `pre_launch`), or as its own short CPU-only job.

### Compilers and CUDA

The NVIDIA HPC SDK 24.5 (with CUDA 12.4) is not on the default module path:

```
pre_launch: module use /opt/nvidia/hpc_sdk/modulefiles && module load nvhpc/24.5
```

Other variants: `nvhpc-nompi`, `nvhpc-hpcx`, `nvhpc-hpcx-cuda12`,
`nvhpc-openmpi3`, `nvhpc-byo-compiler` (all 24.5). There is no
`/usr/local/cuda`. System Open MPI 4.1.6 is at `/usr/bin/mpirun`.

Stage inputs and run directories under `~/agent/work/<run>/` and set
`spec.directory` to it. The disk (~1.8 TB) is shared with the OS; remind the
user to delete large trajectories they no longer need.

**Paths:** a relative `stdout_path`/`stderr_path` is resolved by Slurm from
`spec.directory`, not from home. With `directory="agent/work/run1"`, write
`stdout_path="run1.out"` (lands in that directory), not
`"agent/work/run1/run1.out"` (would land in `agent/work/run1/agent/work/...`).
Without `stdout_path`, output goes to `slurm-<jobid>.out` in the directory.

## Universal rules (apply on every facility, not just this one)

- `submit_job(facility="ai-hpz", spec=spec)` — **show the user the spec
  (or a plain-language description of it) before submitting, unless
  they've explicitly said to just run it.** No exceptions for this call.
- The returned `{"job_id": ..., "script_path": ...}` — the rendered script
  is kept on the cluster; `fs_view(facility="ai-hpz", path=script_path)`
  to inspect exactly what was submitted.
- If a partition/queue/GPU choice isn't given or obvious, check
  `get_resources(facility="ai-hpz")` (live occupancy) and
  `get_facility(facility="ai-hpz")` (static limits) — don't guess.
- Don't run heavy computation on the login node — submit a job instead.
- Stage anything the cluster needs (source trees, inputs, uploads, run
  directories) under `~/agent/work/<descriptive-name>/`, never in the
  home-directory root. `~/agent/` is the agent's visible scratch area —
  `~/agent/jobs` already holds every submitted script — and the home
  root stays the user's own.
- Create a requested `spec.directory` with `fs_mkdir` **before** submission.
  Schedulers enter that directory before the script body and `pre_launch`
  runs, so a `mkdir` in `pre_launch` is too late.
- Don't guess facility-specific details not covered by the notes above —
  use `search_docs(facility="ai-hpz", query=...)` on the `hpc-docs`
  server. It searches a bundled guide, not a live site — never invent a URL
  to send the user to.
- Don't call `cancel_job` without confirming with the user first.
