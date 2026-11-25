# ai-hpz (hpz workstation) guide

## What the machine is

hpz is one workstation, not a cluster. It runs Ubuntu 24.04 and acts as its
own Slurm controller and its own only compute node. You reach it over SSH
(the `ai-hpz` alias); the login shell and the jobs run on the same host.

- CPU: one Intel Xeon Gold 6136 (Skylake-SP, AVX-512), 12 cores with two
  hardware threads each. Slurm counts 24 CPUs.
- Memory: about 187 GiB (Slurm RealMemory 192117 MiB).
- GPU: one NVIDIA Quadro RTX 5000, 16 GiB, compute capability 7.5,
  driver 535.

## Slurm on hpz

There is exactly one partition, `debug`. It is the default, has no time
limit and contains the single node `hpz`.

Slurm allocates cores and memory per job (cons_tres with CR_CORE_MEMORY), so
several small jobs can share the machine. Ask only for the CPUs and memory a
job will actually use; a job that asks for all 24 CPUs blocks everyone else.

Accounting is switched off. Consequences:

- There is no `sacct` and no project/account; never set `--account`.
- A job's status is available from `squeue` while it is queued or running and
  from `scontrol show job` for a short time after it ends. After that, the
  output files are the only record.
- `get_projects` and the allocation tools are unsupported here.

### Requesting the GPU

The single GPU is a Slurm generic resource (`gpu:quadro_rtx_5000:1`).
Request it with `--gres=gpu:1` (`--gpus=1` also works). Consequences:

- Only one job holds the GPU at a time; a second GPU job waits with reason
  `Resources` until the first ends. Asking for two GPUs is refused at submit.
- The job holding the GPU sees it as `CUDA_VISIBLE_DEVICES=0`.
- Slurm does not hide the GPU from other jobs (no device cgroup is
  configured). A job that did not request it can still see and use it, so
  never run GPU code without requesting the GPU — that breaks the
  reservation for whoever holds it.

## Storage

Everything is on one local disk (~1.8 TB, shared with the OS). Home is
`/home/<group>/<user>`. There is no separate scratch or parallel filesystem
and no quota is enforced. Keep agent-created files under `~/agent/` and runs
under `~/agent/work/<run>/`. Clean up large trajectories when you are done,
because the space is shared with the system.

## Software

### GROMACS

GROMACS 2026.3 is installed in `/usr/local/gromacs`. Login shells source its
`GMXRC` from `/etc/profile.d/gromacs.sh`, so `gmx` is already on `PATH` in a
batch job. The build:

- mixed precision, AVX-512 SIMD;
- CUDA GPU support built for sm_75 (the RTX 5000);
- thread-MPI only. There is no `gmx_mpi`, so do not launch with `mpirun` or
  `srun -n`. Run one `gmx mdrun` process and set threads with `-ntmpi` and
  `-ntomp`.

A typical single-GPU run on 8 CPUs: request `--cpus-per-task=8` (one task)
and run `gmx mdrun -deffnm md -ntmpi 1 -ntomp 8 -nb gpu -pme gpu -bonded gpu
-update gpu`. Match `-ntomp` to the CPUs Slurm allocated
(`$SLURM_CPUS_PER_TASK`). Pin threads with `-pin on` only when the job owns
the whole machine, otherwise concurrent jobs fight over the same cores.

### NVIDIA HPC SDK and CUDA

The NVIDIA HPC SDK 24.5 is installed under `/opt/nvidia/hpc_sdk`, with CUDA
12.4 bundled inside it. Its module files are not on the default module path:

```bash
module use /opt/nvidia/hpc_sdk/modulefiles
module load nvhpc/24.5        # or nvhpc-nompi, nvhpc-hpcx-cuda12, ...
```

There is no `/usr/local/cuda`. `nvcc` comes from the SDK module.

### Modules

environment-modules (Tcl) is initialised in login shells. The system module
path holds only the built-in helper modules; everything useful comes from the
HPC SDK path above. Batch scripts submitted through the agent run in a login
shell, so `module` works there.

### MPI, Python, containers

- System Open MPI 4.1.6 at `/usr/bin/mpirun`; Slurm's `srun` supports `pmi2`
  and `pmix`. With a single node, MPI is rarely needed.
- Python is the system `python3` (3.12). Use a venv under `~/agent/work/` for
  extra packages rather than `pip install --user`.
- There is no Singularity or Apptainer, so the agent's container option does
  not work here. A `docker` binary exists but is not wired into Slurm.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `Requested node configuration is not available` at submit | more than one GPU (or more CPUs/memory than the node has) was requested | ask for at most `gpu:1`, 24 CPUs, 192117 MiB |
| GPU job pends with reason `Resources` | another job holds the GPU | wait, or run on CPU |
| `gmx: command not found` in a job | script ran without a login shell | `source /usr/local/gromacs/bin/GMXRC` before `gmx` |
| `nvcc: command not found` | HPC SDK module not loaded | `module use /opt/nvidia/hpc_sdk/modulefiles; module load nvhpc/24.5` |
| GROMACS fails with GPU out-of-memory | a job that did not request the GPU is using it anyway | find it with `nvidia-smi`; always request the GPU for GPU work |
| job status says "not found" a while after it finished | no accounting; scontrol forgets finished jobs | read the job's output files instead |
| job pends with reason `Resources` | other jobs hold the CPUs/memory | lower the request or wait |
