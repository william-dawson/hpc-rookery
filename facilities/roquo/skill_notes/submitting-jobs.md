## Before anything else: two architectures

ROQUO's login and `work` nodes are **x86_64**; its GPU compute nodes are
**aarch64**. A binary built on a login node will not run on a compute
node, and the failure shows up long after the cause. If the user is
building something, build it on a compute node (an interactive job), not
on the login node where they're typing.

The same applies to container images — they must be aarch64.

## Partitions

Only two, and treat them as separate machines:

| Partition | What it is | Architecture | GPUs |
|---|---|---|---|
| `roquo` (default) | 135 GB200 nodes in 8 racks (`qr01`–`qr08`) | aarch64 | 4 per node |
| `work` | 5 nodes for builds, pre/post-processing, workflow servers | x86_64 | none |

`roquo-rack01` … `roquo-rack08` were removed on 2026-10-13. If a user's
old script names one, point them at `roquo` plus
`custom_attributes: {"switches": "1"}`, which keeps the allocation inside
one rack. `submit_job` rejects the removed names with that advice.

## GPUs: `--gres`, per node

ROQUO uses the **per-node `gres`** dialect: `resources.gpus` renders as
`--gres=gpu:N`, N from 1 to 4. This is *not* the job-total `--gpus=N` that
RIKYU uses — don't carry a RIKYU habit over.

A GPU request rounds up to one of three fixed node plans:

| Plan | GPUs | CPU cores | Memory |
|---|---|---|---|
| qtr | 1 | 36 | 400 GB |
| half | 2 | 72 | 800 GB |
| full | 4 | 144 | 1600 GB |

A job naming no GPU, CPU or memory flags silently gets `qtr`. Say what you
want.

**For more than four GPUs, set `resources.gpus=4` and
`resources.node_count=N`** — asking for more than one node's worth in a
single request is rejected (`ROQUO-E001`), and `submit_job` catches that
before the scheduler does. There is no node-count cap under `normal` —
the manual's "36 nodes" is the `general` QOS's limit, and `general`
isn't accepted on this partition.

For tightly coupled multi-node work, ask for whole nodes (`gpus=4`): each
GPU has its own directly attached NIC, so fewer GPUs means less bandwidth.

## Always set the account, and always set the time

**`attributes.account`.** It picks both the billing target and the group
that owns files the job writes. `get_projects` returns two entries and only
one is usable: the account named after the username is a **personal
account** and ROQUO refuses jobs charged to it (`ROQUO-E202`). Each entry
carries `chargeable: true/false` — pick a `chargeable` one, and don't just
take the first result, since the personal account tends to sort first. A job without it is *not* rejected — it
falls back to a restrictive default account, which is worse than failing,
because the job runs and then its output belongs to the wrong group. Call
`get_projects(facility="{{SLUG}}")` to see what the user may charge. If
they belong to several and haven't said which, ask: it's a billing
decision. `{{ENV_PREFIX}}_ACCOUNT` or `defaults.account` in
`~/.hpc-agent/{{CONFIG_STEM}}.json` fills it in automatically when set.

**`attributes.duration`.** The scheduler default is one hour on both
partitions, which is rarely what anyone meant.

## Wall time is capped by QOS — and one failure is silent

Pass QOS as `custom_attributes: {"qos": "<name>"}` (renders as
`#SBATCH --qos=`). Which ones a partition accepts was read from the live
scheduler and is wider than the manual says:

| Partition | Accepts | Partition MaxTime |
|---|---|---|
| `roquo` | `normal`, `p1`, `p2`, `p3`, `p4`, `p5` | 3 days |
| `work` | `normal`, `long`, `p4`, `p5` | 30 days |

Ceilings: `normal` 3d, `p1` 2d, `p2` 1d, `p3` 12h, `long` 30d. `p4`/`p5`
have none of their own — only the partition bounds them. `p3` also allows
one job at a time per user.

**The silent one.** Over the *QOS* ceiling but inside the *partition's*
MaxTime, Slurm accepts the job and never schedules it: it parks on
`QOSMaxWallDurationPerJobLimit`, indistinguishable from a busy queue. Over
the *partition's* MaxTime is the safe case — Slurm refuses it at submit.
`submit_job` catches both, and the message tells you which one you hit.

This is not only a `work` problem: a `roquo` job asking 2.5 days under
`p1` (ceiling 2d) parks exactly the same way.

## The `work` partition's rules

- **A CPU count is mandatory** — `resources.cpu_cores_per_process`
  (`--cpus-per-task`) or `resources.process_count` (`--ntasks`), 1–192.
  Omitting it is `ROQUO-E101`.
- **Memory is capped at 8 GiB per allocated CPU**, and defaults there too.
  Over that is `ROQUO-E103`.
- **No GPUs.** GPU work goes to `roquo`.
- **`p1`/`p2`/`p3` don't exist here.** `long` raises the ceiling to 30
  days but caps the job at 4 CPUs and 8 GiB (and the user at 8 CPUs,
  16 GiB, 4 concurrent jobs).
- **The trap:** over 3 days *without* `qos: long` is accepted and then
  **never starts** — it sits on `QOSMaxWallDurationPerJobLimit` looking
  merely queued. `submit_job` refuses this outright, because a job that
  never starts is indistinguishable from a busy queue.

## Modules

Lmod, but **modules load on compute nodes only, not login nodes.** A
`module load` in the login shell will not behave the way it does in a job,
so put module loads in the job script.

Available: `gcc/14`, `cuda/13.3`, `hpcx/2.50` (and `2.51`), `nvhpc/26.9`,
`nvhpc-openmpi/26.5`. Note bare `module load cuda` resolves to `cuda/13.4`
(the default), not `13.3`.

Start job scripts with `module purge`.

## MPI: pick a stack, then match the launcher to it

The two stacks are mutually exclusive in Lmod — loading one swaps the
other out — and **they take different launchers**:

| Stack | MPI | Launch with |
|---|---|---|
| `hpcx/2.50` | OpenMPI 5 / UCX | `srun` |
| `gcc/14` + `nvhpc/26.5` + `nvhpc-openmpi/26.5` | OpenMPI 4 / UCX | `mpirun` |

On the NVHPC stack, `srun --mpi=pmix` **aborts before `MPI_Init`** and is
unsupported. Set `spec.launcher` to match the stack you loaded.

Sharp edges worth knowing before you debug one of them:

- Don't load the `cuda` module or set `NVHPC_CUDA_HOME` alongside the
  NVHPC stack — it breaks `mpirun`.
- Plain `-lmpi` fails ("cannot find -lmpi"); pass MPI include and library
  paths explicitly.
- `mpicc -cuda` doesn't work (CUDA 13.2 device-header conflict). Compile
  with `nvcc` using `nvc++` as host compiler, or `nvc++` directly.
- Call `cudaSetDevice()` and `cudaFree(0)` **before** `MPI_Init`, or the
  job aborts with "cannot find remote protocol".
- Slurm's TaskProlog injects the UCX settings CUDA-aware MPI needs — don't
  unset them.
- NVSHMEM applications need `NVSHMEM_IBGDA_NIC_HANDLER=cpu_host_memory` or
  they can hang after `cuda_nvshmem_init`. Plain CUDA-aware MPI doesn't.

GPU target is Blackwell: `-arch=sm_100` (nvcc) or `-gpu=cc100` (NVHPC).

## Where files go

- `/home/hps1/<user>` — small; config and source only.
- `/projects/hps1/<project>` — Lustre, persistent, shared with the
  project. Datasets, results, SIF images.
- `$SLURM_SCRATCH` (`/scratch/<jobid>`) — node-local NVMe, **deleted when
  the job ends**. Copy results out before the job exits.

Inside a job `$TMPDIR` is `$SLURM_SCRATCH/tmp`. Don't write to `/tmp`.

## Containers

    srun --container-image=nvcr.io#nvidia/<image:tag> \
         --container-mounts=<host>:<container> <cmd>     # Pyxis/Enroot
    apptainer exec --nv <image.sif> <cmd>                # Apptainer

Images must be aarch64. Keep SIF files in `/projects/hps1/<project>`.

## Reading sbatch's output before declaring failure

ROQUO prints each message twice — Japanese then English — and prints
**warnings with an `error:` prefix**. `sbatch: error: [ROQUO-W003] …` is a
warning that the request was rounded up to a node plan; that is normal.
Decide success from the exit status and the returned job ID, not from the
word "error" appearing.

The one to recognize is **`ROQUO-E201`: not enough billing points.** The
charging group is out of allocation, sbatch refuses the job, and the last
line is the unhelpful `Batch job submission failed: Unspecified error` —
so read the whole stderr. No command reports the balance (it's in the
Portal), so the useful response is to tell the user their project is out
of points and offer to charge a different one via `attributes.account`,
not to retry or to adjust the job.

## Email

`--mail-user` needs a full address containing `@` and `--mail-type` must
be set too; a bare username silently sends nothing.
