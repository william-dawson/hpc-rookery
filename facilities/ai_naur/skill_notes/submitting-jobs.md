naur is a single Arm (aarch64) node. This facility submits only to the Slurm
partition `naur` (the cluster default, no time limit). A partial spec gets
`queue_name="naur"` filled in; any other partition is rejected — `prado`,
`shannon` and `backus`, which `get_resources` also lists, are different
machines. Keep `node_count=1` and never set `attributes.account`.

**Never set `resources.memory`.** The node is registered in Slurm with 1 MiB
of memory, so any `--mem` request is refused at submit ("Requested node
configuration is not available"); the spec is rejected before it gets that
far. Jobs share the node's ~744 GiB with no per-job limit, so tell the user
when a job is expected to use a large share of it.

**CPUs are allocated and enforced per job.** There are 72 cores (no
hyperthreads). A job sees exactly the cores it asked for, so set
`cpu_cores_per_process` to the thread count the program will use, and set
`OMP_NUM_THREADS` to match in `pre_launch` or `environment`.

**The GPU is an enforced Slurm GRES.** There is one NVIDIA GB300 (~251 GiB).
Set `resources.gpus=1` for any job that uses it; it renders as
`--gres=gpu:1`, reserves the GPU (a second GPU job pends with `Resources`)
and sets `CUDA_VISIBLE_DEVICES=0`. `gpus` above 1 is rejected. A job without
`gpus=1` cannot see the GPU at all — `nvidia-smi` prints "No devices found" —
so a "no CUDA device" error almost always means the request was left out.

**No containers.** There is no Singularity/Apptainer, so `spec.container` is
rejected, and users cannot reach the Docker daemon. Use host software.

### Architecture

Everything must be built for aarch64. Binaries copied from an x86 machine
(including the sibling hpz workstation) fail with `Exec format error`. The
kernel uses 64 KiB pages, which a few prebuilt packages do not expect; if a
wheel or binary crashes at start-up, suspect that before the job shape.
GROMACS is not installed here.

### Compilers, CUDA and MPI

Modules work inside batch jobs, and the module directories are already on
the default path (no `module use` line is needed):

```
pre_launch: module load nvhpc/26.9     # nvc, nvc++, nvfortran, CUDA 13.3, Open MPI 5
pre_launch: module load cuda-13.2      # system CUDA toolkit only (nvcc, CUDA_PATH)
```

Other SDK variants, all 26.9: `nvhpc-nompi`, `nvhpc-hpcx`,
`nvhpc-hpcx-cuda13`, `nvhpc-hpcx-cuda13-openmpi4`,
`nvhpc-hpcx-cuda13-openmpi5`, `nvhpc-byo-compiler`. They conflict with each
other, so load one. System GCC/gfortran 13.3 need no module.

There is no MPI outside the SDK modules: `mpirun` exists only after
`module load nvhpc/26.9` (or an `hpcx` variant). On this single node, launch
MPI programs with that `mpirun -np N` and request the ranks as
`process_count=N`; keep ranks × threads within 72.

Build in a job, not on the login shell, when the build is heavy — the login
shell is the same host the jobs run on and is not confined by Slurm.

Stage inputs and run directories under `~/agent/work/<run>/` and set
`spec.directory` to it. Home is a local ~1.8 TB NVMe filesystem on naur with
no quota and no purge; it is not shared with the other machines.

**Paths:** a relative `stdout_path`/`stderr_path` is resolved by Slurm from
`spec.directory`, not from home. With `directory="agent/work/run1"`, write
`stdout_path="run1.out"` (lands in that directory), not
`"agent/work/run1/run1.out"` (would land in `agent/work/run1/agent/work/...`).
Without `stdout_path`, output goes to `slurm-<jobid>.out` in the directory.
