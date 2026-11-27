# ai-Naur (Naur GB300 node) guide

## What the machine is

naur is a single Arm (aarch64) host running Ubuntu 24.04 on NVIDIA's kernel
with 64 KiB memory pages. You reach it over SSH (the `ai-Naur` alias); the
login shell and the jobs run on the same host.

- CPU: 72 Arm Neoverse-V2 cores in one socket, one thread per core.
- Memory: about 744 GiB.
- GPU: one NVIDIA GB300 with roughly 251 GiB of GPU memory, compute
  capability 10.3, driver 595.

Because the host is aarch64, programs compiled on an x86 machine do not run
here. Build on naur itself, and expect some prebuilt Python wheels or
binaries to assume 4 KiB pages or x86.

## Slurm on naur

naur is a compute node in a small Slurm cluster (version 23.11) whose
controller is a different host. The cluster has four partitions, each
holding exactly one machine of the same name: `naur` (the default), `prado`,
`shannon` and `backus`. This facility covers naur only, so every job goes to
the `naur` partition; the other three are different computers with different
CPUs, GPUs and home directories. They still show up in `get_resources` and
`get_drained_nodes`, because those list the whole cluster.

The `naur` partition has no time limit.

### CPUs

Cores are allocated per job and enforced: a job that asks for 4 CPUs sees 4
cores. Several jobs can run side by side until the 72 cores are used up, so
ask only for what the job will use.

### Memory — never request it

The node is registered in Slurm with a memory size of 1 MiB, and memory is
not a scheduled resource. Any realistic `--mem` value is refused at submit
with "Requested node configuration is not available". Leave memory out of
the job description. Jobs share the node's ~744 GiB with no per-job limit,
so a job that overuses memory can hurt the others; size the work yourself.

### Requesting the GPU

The single GPU is a Slurm generic resource (`gpu:1`). Request it with
`--gres=gpu:1` (`--gpus=1` is also accepted).

- Only one job holds the GPU at a time. A second GPU job waits with reason
  `Resources` until the first one ends. Asking for two GPUs is refused at
  submit.
- GPU access is enforced through a device cgroup. A job that did not request
  the GPU cannot use it: `nvidia-smi` inside such a job reports that no
  devices were found. If GPU code fails to find a device, the first thing to
  check is whether the job asked for the GPU.

### No accounting

The Slurm configuration points at an accounting database, but that database
does not answer, so `sacct` and `sacctmgr` fail with a connection error.
In practice:

- There is no project or account to set; leave `--account` out.
- A job's status is available from `squeue` while it is queued or running
  and from `scontrol show job` for about five minutes after it ends. After
  that the output files are the only record.
- `get_projects` and the allocation tools are unsupported here.

## Storage

Home is `/data1/<group>/<lab>/<user>`, which is a link into `/work1`, a local
NVMe filesystem on naur of about 1.8 TB. No quota is enforced and nothing is
purged automatically. There is no separate scratch or parallel filesystem,
and the home directory is local to naur — it is not the same directory as
on the other machines of the cluster. Keep agent-created files under
`~/agent/` and runs under `~/agent/work/<run>/`.

## Software

### Modules

environment-modules (Tcl) is available in login shells and in batch jobs
submitted through the agent. Unlike some sibling machines, the useful module
directories are already on the default module path, so no `module use` is
needed:

- `cuda-13.2` — the system CUDA toolkit in `/usr/local/cuda-13.2`
  (sets `CUDA_PATH`, adds `nvcc` to `PATH`).
- `nvhpc/26.9` — the NVIDIA HPC SDK: `nvc`, `nvc++`, `nvfortran`, the SDK's
  own CUDA 13.3, math libraries, and an Open MPI 5 build.
- Variants of the SDK module: `nvhpc-nompi/26.9`, `nvhpc-hpcx/26.9`,
  `nvhpc-hpcx-cuda13/26.9`, `nvhpc-hpcx-cuda13-openmpi4/26.9`,
  `nvhpc-hpcx-cuda13-openmpi5/26.9`, `nvhpc-byo-compiler/26.9`. The SDK
  modules conflict with each other; load one.

Without a module loaded, `nvcc`, `nvc` and `mpirun` are not on `PATH`.

### Compilers and MPI

- System GCC and gfortran 13.3 are always available.
- NVIDIA compilers come from `nvhpc/26.9`; they target Neoverse-V2 by
  default.
- There is no system-wide MPI. `mpirun`/`mpicc` appear after loading an
  `nvhpc` module (Open MPI 5 with the plain `nvhpc` module). Slurm's `srun`
  offers `pmi2` and `pmix`. With one node, MPI is only useful for
  shared-memory ranks.

### Python and containers

- Python is the system `python3` (3.12). Use a venv under `~/agent/work/`
  for extra packages rather than `pip install --user`.
- There is no Singularity or Apptainer, so the agent's container option does
  not work here. A `docker` binary exists, but ordinary users are not
  allowed to talk to its daemon.

### What is not installed

GROMACS is not installed on naur (it is on the sibling hpz workstation, as
an x86 build that cannot be copied over). Application software has to be
built here for aarch64.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `Requested node configuration is not available` at submit | a memory request, more than one GPU, more than 72 CPUs, or more than one node | drop the memory request; ask for at most `gpu:1`, 72 CPUs, one node |
| `No devices found` / CUDA cannot find a GPU inside a job | the job did not request the GPU | add the GPU request (`gpus=1`) |
| GPU job pends with reason `Resources` | another job holds the GPU | wait, or run on CPU |
| CPU job pends with reason `Resources` | other jobs hold the cores | lower the CPU request or wait |
| `nvcc`/`nvc`/`mpirun: command not found` | no module loaded | `module load cuda-13.2` or `module load nvhpc/26.9` |
| `Exec format error` or `cannot execute binary file` | an x86 binary was copied to this Arm host | rebuild on naur |
| `sacct`/`sacctmgr` report a refused connection | the accounting database is not in service | use `squeue`/`scontrol`, and the output files |
| job status says "not found" a while after it finished | no accounting; scontrol forgets finished jobs after ~5 minutes | read the job's output files instead |
