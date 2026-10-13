# cell2026

cell2026 is a small GPU cluster with two schedulers operating side by side.
Grid Engine manages `helix` and `kinase`; Slurm manages `beta` and `serine`.
This is not merely two syntaxes for the same queue: GPU assignment and job
history differ materially between them.

## Choosing a side

| selector | scheduler and real queue | CPU | GPU | history |
|---|---|---:|---|---|
| `helix` | Grid Engine `all.q`, pinned to helix | 32 cores | 2 × RTX A4000 | durable per-ID `qacct` |
| `kinase` | Grid Engine `all.q`, pinned to kinase | 32 cores | 2 × RTX A4000 | durable per-ID `qacct` |
| `all.q` / `gpu` | Grid Engine `all.q`, either host | 32 cores/host | 2 × RTX A4000/host | durable |
| `beta` | Slurm `all`, `--nodelist=beta` | 8 cores | 1 × RTX 4000 Ada | ephemeral |
| `serine` | Slurm `all`, `--nodelist=serine` | 8 cores | 1 × RTX 5090 | ephemeral |
| `all` | Slurm `all`, either host | 8 cores/host | one unmanaged GPU/host | ephemeral |

With no selector, the hub uses Grid Engine `all.q`. An explicit
`attributes.scheduler` can select Slurm or Grid Engine, but it must agree with
any queue selector.

## Grid Engine GPUs

Set job-total `resources.gpus` to 1 or 2. Grid Engine renders `-l gpu=N` and
allocates RSMAP device indexes through `$SGE_HGR_gpu`. The scheduler does not
set `CUDA_VISIBLE_DEVICES` or provide cgroup isolation, so the generated script
translates the assigned indexes itself:

```bash
export CUDA_VISIBLE_DEVICES="$(echo "$SGE_HGR_gpu" | tr ' ' ',')"
```

Do not override this environment variable in the JobSpec. `helix` and
`kinase` have 32 cores each. Choose the Grid Engine parallel environment with
`attributes.parallel_env`: recorded choices include `smp`, `OpenMP`, and the
`mpi` family. The recorded wall-time ceiling is five days.

## Slurm GPUs

Slurm has no GPU GRES and rejects `--gres=gpu:N`. It also has unusable memory
tracking (`RealMemory=1`), so the backend emits neither GPU nor memory flags.
The single GPU is visible to every job placed on that host and is not reserved
or isolated. On a container job, `resources.gpus=1` only enables Singularity
`--nv`; users still need to coordinate GPU use. Use `beta` or `serine` when a
specific GPU generation is required.

Slurm accounting is disabled. Live jobs appear in `squeue`, and a completed
job remains in `scontrol` only briefly before its status disappears. Save
stdout and stderr under `/work` when a durable record matters.

## Job IDs and recent status

The two schedulers can issue overlapping numeric IDs. After submission, the
hub records the ID-to-scheduler mapping locally under
`~/.hpc-agent/cell2026-registry/`. This registry is a routing and recency index,
not scheduler accounting. A missing entry makes status and cancellation query
both schedulers; a collision is reported as ambiguous rather than guessed.

Grid Engine's `qacct -o $USER -d N` on this installation returns an owner
summary, not per-job history, although `qacct -j <id>` is durable. The local
registry is therefore necessary to find recently submitted IDs after they
leave the live queues.

## Software and storage

There is no environment module system. Use binaries already on `PATH`, a
user-installed virtual/conda environment, or a container. Singularity is the
preferred batch runtime and receives `--nv` for GPU-enabled container jobs.
Docker is installed but is not the normal multi-user batch path.

Keep small scripts and environment definitions under shared `/home`; use
`/work` for datasets, checkpoints, and large outputs. No project/account is
required on either scheduler.

## Validation status

The original dual-scheduler implementation was exercised live on 2026-06-26:
a Slurm CPU job and Grid Engine GPU job completed, output was confirmed, the
GPU device translation worked, qacct history persisted, and registry routing
distinguished the jobs. The later core migration and this hub integration were
not rerun live. Treat those earlier results as strong evidence, but keep this
port in awaiting-live-validation until both current scheduler paths pass again.
