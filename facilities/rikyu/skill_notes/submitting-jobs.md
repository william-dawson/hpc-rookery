## Workflow

1. **Pick a GPU count first** — RIKYU has a single `gpu` partition; you
   don't choose a partition per GPU count, you request the total GPUs for
   the job and Slurm places it. Use `get_facility(facility="rikyu")` for
   the exact table, but the rule: only **1, 2, 3, 4, 8, 12, or 16** GPUs
   are accepted (1-4 fit on one node; 8/12/16 span 2/3/4 nodes at 4
   GPUs/node). Each GPU brings 36 CPU cores and ~400GB combined memory —
   ask for more GPUs to get more of both, don't try to raise `--mem`
   independently. `submit_job` rejects any other count with a clear error
   before it ever reaches Slurm.
2. **Stage any needed files** with `fs_upload(facility="rikyu", ...)` /
   `fs_mkdir(facility="rikyu", ...)` (paths are relative to the home
   directory unless absolute).
3. **Submit with a JobSpec** via `submit_job(facility="rikyu", spec=...)`.
   Example (2-GPU job, single node — leave `node_count` at its default so
   Slurm derives placement from `gpus`):
   ```json
   {
     "name": "train-vit",
     "executable": "module load nvhpc-hpcx && mpirun -np 2 python train.py",
     "directory": "/home/<user>/experiments/vit",
     "resources": {"gpus": 2, "processes_per_node": 2},
     "attributes": {"duration": "12:00:00", "queue_name": "gpu"}
   }
   ```
   Leave `attributes.queue_name` blank if you like — RIKYU's only
   partition, `gpu`, is filled in automatically.
4. **Verify**: `get_job_status(facility="rikyu", job_id=...)` right after
   submission. `queued` with a `message` explains any wait. Once it runs, read
   `<workdir>/slurm-<job_id>.out` with `fs_tail` — take `workdir` from the
   status record rather than assuming `$HOME`.

## MPI launch: use mpirun, not srun

Verified live: `srun` fails to launch MPI ranks on RIKYU — `MPI_Init`
aborts with an internal-runtime failure, even though `srun --mpi=list`
shows `pmi2`/`pmix` plugins registered. Launch MPI programs with `mpirun`
instead, after loading an MPI-capable module (`nvhpc-hpcx` or
`nvhpc-hpcx-cuda13`, not `nvhpc-nompi`):
`module load nvhpc-hpcx && mpirun -np <n> ./a.out`.

**Set `resources.processes_per_node` to match your rank count** — `mpirun`
reads available task slots from the Slurm allocation, and a job that only
requests GPUs without also setting `processes_per_node` gets just 1 slot,
so `mpirun -np 2` (or more) fails with "not enough slots" before it even
starts. This is unrelated to the `srun` issue above; both single-node and
real multi-node `mpirun` launches work correctly once slots are sized
right — verified live with a real 2-node, 8-rank job (`gpus: 8,
processes_per_node: 4`), no hostfile or extra setup needed. (`srun` itself
is still fine for non-MPI use — interactive `salloc`/`srun --pty`, or
attaching to a running job with `srun --overlap --jobid <id>` for
diagnostics like `nvidia-smi`; the failure is specifically MPI rank
bootstrap.)

## NCCL collectives need NUMA-bound ranks (silently 60x slow otherwise)

Verified live on a 2-node, 8-GPU job (4 ranks/node, one GPU per rank,
`nvhpc-hpcx-cuda13/26.5`, NCCL 2.29.3): the same `ncclAllReduce` of a
9.5 MB device buffer measures **0.17 ms (96 GB/s bus) with `mpirun
--bind-to numa --map-by numa`, but 12 ms (1.4 GB/s) unbound or with
`--bind-to core`** — a 60x cliff with no error, no warning, and a
plausible-looking result either way. Plain `MPI_Send`/`Recv` on the same
buffers moves 95.7 GB/s in both cases, so this is NCCL-specific.

Mechanism: NCCL pairs each GPU with each rank's *nearest* NIC using the
rank's CPU affinity data. GB200 nodes have two Grace sockets (GPU0/1 on
socket 0, GPU2/3 on socket 1, one CX-7 NIC per GPU); unbound ranks give
NCCL no usable affinity ("Affinity for GPU 2 is empty, ignoring" in
`NCCL_DEBUG=INFO`), it mispairs the rails, and the inter-node collective
stalls on one shared NIC. `--bind-to core` is just as bad — it packs ranks
onto one socket's cores regardless of their GPU. `--bind-to numa
--map-by numa` puts each rank on its own GPU's socket, and is the fix.

**Every NCCL job on RIKYU should launch with**

```sh
mpirun -n <np> --bind-to numa --map-by numa --mca fcoll individual ./app
```

(`--mca fcoll individual` is a separate, unrelated requirement for
MPI-IO reads into managed memory on this stack — see the SALMON notes.)

Two more limits found in the same campaign, both fail-
silently-capable:

- **Multi-rank-per-GPU under MPS works on NCCL 2.30+ — measured.** Two
  MPI ranks (e.g. multi-walker QMC) sharing one GPU via MPS cannot share
  one NCCL communicator on NCCL 2.29 (this stack's
  `nvhpc-hpcx-cuda13/26.5`): `ncclCommInitRank` fails with
  `NCCL WARN Duplicate GPU detected` / `ncclInvalidUsage`. **NCCL 2.30+
  fixes this with `NCCL_MULTI_RANK_GPU_ENABLE=1`** (experimental, off by
  default) — verified live on RIKYU with `nvhpc-hpcx-cuda13/26.9`
  (NCCL 2.31.2), 2 MPS clients per GPU across 2 nodes, 9.5 MB allreduce:
  **0.327 ms / 54.5 GB/s**, result exact, against 0.142 ms / 117 GB/s at
  1 rank per GPU — i.e. clean bandwidth sharing, no deadlock in the wild,
  and 18x faster than `MPI_Allreduce` on the same ranks (5.9 ms). Without
  the flag the same build fails `ncclCommInitRank` exactly as 2.29 does,
  so the flag is the switch, not a version gamble. Working config:

  ```sh
  export NCCL_MULTI_RANK_GPU_ENABLE=1
  export NCCL_MAX_CTAS=4          # bound the collective's SM footprint
  export NCCL_NVLS_ENABLE=0       # NVLS is unavailable to duplicate-GPU ranks
  ```

  Caveats from NVIDIA + our runs: defaults are sized for ~2 ranks/GPU (more
  co-tenants need `NCCL_MAX_CTAS` retuning — e.g. 1 at 8 ranks/GPU); two
  ranks' NCCL kernels on one GPU can deadlock waiting on each other's SM
  residency (if a multi-rank run hangs, try `NCCL_NET_GDR_LEVEL=LOC` —
  performance cost, troubleshooting only); no published data claims MPS
  makes the collective itself *faster* than 1-rank-per-GPU — the win is
  letting a many-ranks-per-GPU app use NCCL at all. The version-independent
  fallback remains one communicator per GPU with a local reduce stage
  (reduce co-tenants, collective over one rank per GPU, broadcast back).
- **Do not pin ranks to NICs with per-rank `UCX_NET_DEVICES`.** The
  GB200 tuning guide's per-rank `UCX_NET_DEVICES=mlx5_<i>:1` recipe
  makes inter-node CUDA sends fail outright on this stack
  (`UCX ERROR cannot find remote protocol ... tag_send from cuda/GPU0`
  → `ucp_ep_create failed: Destination is unreachable`, HPC-X 2.50).
  Leave `UCX_NET_DEVICES` unset; NCCL's own affinity-based pairing works
  correctly once ranks are NUMA-bound.

## RIKYU conventions

- **Time limits**: max 96h regardless of GPU count; confirm the current
  default with `get_facility` if the user omits `duration`. Format
  `HH:MM:SS` or `D-HH:MM:SS`.
- **Modules** (put `module load …` at the start of `executable`): `nvhpc`
  standard; `nvhpc-hpcx` (or `nvhpc-hpcx-cuda13`) for multi-node MPI over
  InfiniBand; `nvhpc-nompi` when the user manages MPI; `nvhpc-byo-compiler`
  to use the system GCC instead.
- **Spack** provides prebuilt applications (not compilers) —
  `. /shared/software/spack-1.2.0/share/spack/setup-env.sh && spack load
  <package>` before running, e.g. `quantum-espresso`, `gromacs`, `lammps`.
  Loading a Spack package does not request GPUs by itself — the JobSpec's
  `gpus` still has to ask for them.
- **Architecture is aarch64** (Grace CPUs, B200 GPUs). x86_64 binaries,
  containers, and Python wheels will not run — check before suggesting pip
  installs of compiled packages.
- **Node-local scratch**: `/tmp` on the compute node, 1.5TB per requested
  GPU, xfs, auto-deleted when the job ends. Stage datasets/checkpoints
  there for I/O-heavy work and copy results back to `/home/<user>` or the
  group area (`/data1/<group>`) before the script exits.
- **Interactive sessions**: `salloc`/`srun --pty` hold allocations open —
  use `run_command_on_cluster` only for short non-interactive checks;
  prefer batch jobs.

## RIKYU-specific don'ts

- Don't launch MPI ranks with `srun` — `MPI_Init` fails; use `mpirun` instead.
- Don't submit an MPI job without setting `resources.processes_per_node` —
  `mpirun` will fail with "not enough slots" even though the job runs fine.

## Always set the project account

Put `"account": "<project>"` in `attributes` on every job. RIKYU rejects a
job from a multi-project user that omits it:

> `[AI4S] You belong to multiple projects, so the project to be charged
> must be specified explicitly.`

It is optional only for someone in exactly one project, and harmless there,
so set it unconditionally instead of deciding. `get_projects(facility="rikyu")`
lists the user's projects (the `rkp*` groups); if they have several and
haven't said which to charge, ask rather than picking one — it is a billing
decision at 300 yen/GPU-hour. `RIKYU_ACCOUNT` or `defaults.account` in
`~/.hpc-agent/rikyu.json` supplies it automatically when set.
