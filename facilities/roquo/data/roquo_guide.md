# ROQUO Orientation Guide

ROQUO is a RIKEN Center for Computational Science (R-CCS) GPU
supercomputer built around NVIDIA GB200 nodes, scheduled by Slurm.

**Provenance:** written from the operator's online manual, then checked
against the live system on 2026-10-27. Verified there: SSH, Slurm 26.05.3,
both partitions and their node counts, the QOS policy, and that a rendered
script is accepted by `sbatch`. Not verified: a job running to completion —
the project available for testing had zero billing points. Where the manual
and the live system disagreed, this follows the live system and says so.
Quotas remain unverified (the manual marks them TBD), so read those live.

## The one thing to get right first

**Login nodes are x86_64. Compute nodes are aarch64.** Anything you build
on a login node will not run on a compute node. Build on a compute node,
in an interactive job, or in a batch job. This is the mistake that costs
the most time here, because the failure appears much later than the cause.

The same split applies to containers: images must be aarch64-compatible,
and an x86_64 image simply won't run. It also applies to the `work`
partition, which is x86_64 — binaries built there don't run on `roquo`.

## Getting in

SSH to `login.roquo.qc.r-ccs.riken.jp`, which is an alias for `login1`,
`login2` and `login3` (each reachable directly as
`loginN.roquo.qc.r-ccs.riken.jp`).

Register your public key yourself in the ROQUO Portal
(`https://portal.roquo.qc.r-ccs.riken.jp/`) under **SSH Keys**: paste the
contents of your `.pub` file and press Add. Keys are listed by the comment
at the end of the public key. Never paste a private key. If that screen
says keys can't be changed there, administrators manage them for your
account and you file a portal ticket instead.

The portal is also where you see your username, UID, groups and which of
them are billing groups, request storage quota changes, and issue API
tokens. Most profile fields need a ticket to change; your login shell is
the exception.

## Slurm

Two partitions, and they are genuinely different machines:

- **`roquo`** — the default. 135 GB200 GPU nodes, aarch64, in eight racks
  (`qr01`–`qr08`), nodes named like `qr01n01`. No node-count cap under the
  normal QOS (the manual's "36 nodes per job" is the `general` QOS's limit,
  and `general` isn't allowed on this partition).
- **`work`** — five CPU-only x86_64 nodes (`work01`–`work05`), AMD EPYC
  9655 with 192 logical CPUs and about 1510 GiB usable each. No GPUs. For
  builds, pre/post-processing, workflow servers, and VS Code Remote.

Per-rack partitions `roquo-rack01`–`roquo-rack08` were removed on
2026-10-13. If you find them in an old script, delete them and use
`--switches=1` instead to keep an allocation inside one rack (it waits up
to five minutes before spanning racks; `--switches=1@<time>` shortens
that).

**Always set `--account=<project>`.** It chooses both what gets billed and
which group owns the files the job writes. Leaving it out doesn't fail the
job — it falls back to a restrictive default account, which is worse,
because the job runs and behaves strangely instead of stopping. List what
you can charge with `sacctmgr -nP show assoc user=$USER format=Account`.

**Always set `--time`.** The default is one hour on both partitions, which
is rarely what you meant.

Standard `sbatch` / `squeue --me` / `salloc` / `srun` / `scancel` /
`sinfo` all work as expected, and accounting is available, so
`sacct -j <jobid> -o JobID,State,ExitCode,Elapsed,MaxRSS` gives you job
history rather than just the live queue.

## Asking for GPUs

Use `--gres=gpu:N` with N from 1 to 4 — this is the per-node `gres`
dialect, not the job-total `--gpus=N` that some other RIKEN machines use.

A GPU request rounds up to one of three fixed node plans:

| Plan | GPUs | CPU cores | Memory |
|---|---|---|---|
| qtr | 1 | 36 | 400 GB |
| half | 2 | 72 | 800 GB |
| full | 4 | 144 | 1600 GB |

A job that names no GPU, CPU or memory flags gets the `qtr` plan.

Asking for more than one node's worth in a single `--gres` request is
rejected outright with `ROQUO-E001`. For multiple nodes, combine
`--gres=gpu:4` with `--nodes=N` — and for tightly coupled multi-node work
you want whole nodes anyway, since each GPU has its own directly attached
NIC and asking for fewer GPUs means less bandwidth.

## Wall time and QOS

QOS trades wall time for priority, and which ones a partition accepts is
not what the manual implies. From the live scheduler:

| Partition | Accepts | Partition's own MaxTime |
|---|---|---|
| `roquo` | `normal`, `p1`, `p2`, `p3`, `p4`, `p5` | 3 days |
| `work` | `normal`, `long`, `p4`, `p5` | 30 days |

Ceilings per QOS: `normal` 3 days, `p1` 2 days, `p2` 1 day, `p3` 12 hours,
`long` 30 days. `p4` and `p5` have no ceiling of their own, so only the
partition's MaxTime bounds them. A `general` QOS also exists but isn't
accepted by either partition, so you can't use it here. `p3` additionally
allows only one job at a time per user.

**The trap, and it is not only on `work`.** Exceeding the *QOS* ceiling
while still inside the *partition's* MaxTime is accepted by Slurm and then
never scheduled — the job parks on `QOSMaxWallDurationPerJobLimit`, which
looks exactly like waiting for a busy queue. That's any `work` job over 3
days without `--qos=long`, and equally any `roquo` job over its `p1`/`p2`/
`p3` ceiling. Going over the *partition's* MaxTime is the safe case: Slurm
refuses it at submit with a clear message.

## The work partition's own rules

You must give a CPU count — `--cpus-per-task` or `--ntasks`, from 1 to 192
(`ROQUO-E101` if you forget, `ROQUO-E102` if you overshoot). Memory is
8 GiB per allocated CPU by default and also capped there, so `--mem` can
go down but not above CPUs × 8 GiB (`ROQUO-E103`). Jobs share nodes, so
you get only what you allocated.

For VS Code Remote: you can only SSH to a work node while your own job is
running on it. The documented setup puts a `ProxyCommand` in your local
`~/.ssh/config` that runs `srun` on the login node and relays through
`socat` to the node's sshd, so connecting allocates a node and
disconnecting releases it. `socat` is already installed there. The
connection drops when `--time` runs out.

## Storage

- **Home** (`/home/hps1/<username>`) — small; configuration and source
  only. Check with `lfs quota -h -u $USER /home/hps1`.
- **Project** (`/projects/hps1/<project>`, Lustre) — persistent and shared
  with your project. Datasets, results and SIF images belong here. Check
  with `lfs df -h /projects/hps1`. Quota changes go through the portal and
  need a stated reason.
- **Scratch** (`/scratch/<jobid>`, also `$SLURM_SCRATCH`) — node-local
  NVMe, visible only to that job, deleted the moment it ends. Copy
  anything you want to keep before the job exits.

Inside a job `$TMPDIR` points at `$SLURM_SCRATCH/tmp`. Don't write to
`/tmp` directly.

The manual does not publish actual quota figures — they're marked TBD — so
read them live rather than assuming.

## Modules

Lmod, with the usual `module avail` / `load` / `list` / `unload` / `purge`
/ `spider`.

**Modules load on compute nodes only, not on login nodes.** A `module
load` in a login shell won't behave the way it does inside a job.

Available: `gcc/14`, `cuda/13.3`, `hpcx/2.50` (and `2.51`), `nvhpc/26.9`,
`nvhpc-openmpi/26.5`. Note that bare `module load cuda` resolves to
`cuda/13.4`, which is the default — not `13.3`, which you have to name.

## MPI

Two stacks, and Lmod treats them as mutually exclusive — loading one swaps
the other out:

- **`hpcx/2.50`** (OpenMPI 5 over UCX) — launch with **`srun`**.
- **`gcc/14` + `nvhpc/26.5` + `nvhpc-openmpi/26.5`** (OpenMPI 4 over UCX),
  for NVHPC compilers and CUDA-aware MPI — launch with **`mpirun`**.
  `srun --mpi=pmix` aborts before `MPI_Init` on this stack and is
  unsupported.

Compiling for the GPUs means Blackwell: compute capability 10.0, so
`-arch=sm_100` for `nvcc` or `-gpu=cc100` for NVHPC.

Known sharp edges, all of which produce confusing failures:

- Plain `-lmpi` fails with "cannot find -lmpi". Pass MPI include and
  library paths explicitly.
- `mpicc -cuda` doesn't work, due to a CUDA 13.2 device-header conflict.
  Compile with `nvcc` using `nvc++` as the host compiler, or use `nvc++`
  directly.
- Don't load the `cuda` module or set `NVHPC_CUDA_HOME` alongside the
  NVHPC stack — it breaks `mpirun`.
- Call `cudaSetDevice()` and `cudaFree(0)` **before** `MPI_Init`, or the
  job aborts with "cannot find remote protocol".
- Slurm's TaskProlog injects the UCX settings CUDA-aware MPI needs. Don't
  unset them.
- NVSHMEM applications (HPL in the hpc-benchmarks container, for instance)
  need `NVSHMEM_IBGDA_NIC_HANDLER=cpu_host_memory` or they can hang after
  `cuda_nvshmem_init`. Ordinary CUDA-aware MPI doesn't need it.

For reference, the manual reports about 93 GB/s for one GPU pair at 16 MB,
and about 378 GB/s aggregate across two nodes of four GPUs at 32 MB.

## Containers

Two runtimes. Pyxis/Enroot pulls and runs in one step:

    srun --container-image=nvcr.io#nvidia/<image:tag> \
         --container-mounts=<host>:<container> <cmd>

Apptainer runs a local SIF:

    apptainer exec --nv <image.sif> <cmd>

Keep images under `/projects/hps1/<project>`, and remember they must be
aarch64.

## Reading sbatch's output

Two things make ROQUO's `sbatch` messages easy to misread.

**Every line is bilingual** — Japanese first, then the same message in
English, both carrying the same `ROQUO-nnn` code. Match on the code, not
the text.

**Warnings are printed as errors.** A line reading
`sbatch: error: [ROQUO-W003] …` is a *warning* (note the `W`): it means
your request was rounded up to a node plan, which is normal and expected.
Judge success by sbatch's exit status and whether a job ID came back, not
by whether the word "error" appears.

## Common failure modes

- **A binary works on the login node and dies on a compute node** — it was
  built for x86_64. Rebuild on a compute node. Same cause if something
  built on `work` fails on `roquo`.
- **`ROQUO-E001`** — the request exceeds one node. Use `--gres=gpu:4`
  with `--nodes=N`.
- **`ROQUO-E101` / `E102` / `E103`** — on `work`: no CPU count, too many
  CPUs (max 192), or more memory than 8 GiB × CPUs.
- **A `work` job sits queued forever with `QOSMaxWallDurationPerJobLimit`**
  — more than 3 days without `--qos=long`. Nothing rejected it at submit
  time.
- **An MPI job aborts before `MPI_Init`** — `srun --mpi=pmix` on the NVHPC
  stack. Use `mpirun`, or switch to `hpcx` and use `srun`.
- **"cannot find remote protocol"** — CUDA wasn't initialized before
  `MPI_Init`.
- **"cannot find -lmpi"** — MPI paths weren't passed explicitly.
- **Email notifications never arrive** — `--mail-user` needs a full
  address containing `@`, and `--mail-type` must be set too. A bare
  username silently sends nothing.
- **`module load` seems to do nothing** — you're on a login node. Modules
  only load on compute nodes.
- **A job writes files the rest of the project can't read** — it ran
  without `--account`, so a restrictive default owned the output.
- **`ROQUO-E202`, "Jobs cannot be submitted with a personal account"** —
  you charged the account named after your username. `sacctmgr` lists it
  next to your real billing group, but it cannot be charged. Use the
  `qc-prj-*` group; `get_projects` marks which entries are chargeable.
- **`ROQUO-E201`, "Not enough billing points"** — the charging group is out
  of points. sbatch then ends with the unhelpful `Batch job submission
  failed: Unspecified error`, so read the whole message, not the last line.
  There's no command for the balance — it's in the Portal — and the fix is
  to have administrators add points, or to charge a different project.
- **`ROQUO-W003`** — not a failure at all; see "Reading sbatch's output".
