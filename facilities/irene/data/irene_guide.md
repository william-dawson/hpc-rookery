# TGCC Irene

Irene is a CPU-first supercomputer at CEA's TGCC. Its scheduler is Slurm
underneath, but users work through TGCC Bridge: batch scripts contain `#MSUB`
directives, `ccc_msub` submits them, and parallel programs launch with
`ccc_mprun`.

Live values — queue occupancy, installed module versions, project
consumption — should be read from the machine rather than from this guide.
The site documentation this was written from is dated 2026-04-27; hardware
facts are stable, but partitions, quotas, QoS limits and accounting are
operational data that moves.

## Partitions

The normal target is `rome`, recorded as 2,286 AMD Rome nodes with 128 cores
and about 228 GiB per node. Use the specialized partitions only when the
workload needs them:

| partition | recorded shape | purpose |
|---|---|---|
| `rome` | 128 CPU cores/node, ~228 GiB | ordinary CPU, MPI, and hybrid production |
| `xlarge` | 112 cores, about 3 TiB, one P100 | single-node large-memory work |
| `v100` | 40 cores and four V100 GPUs/node | multi-GPU work |
| `v100l` / `v100l-os` | 36 cores and one V100/node | GPU work with more memory per GPU |
| `v100xl` | 72 cores, about 2.9 TiB, one V100 | large-memory GPU work |

`xlarge` has five nodes, `v100` thirty-two, `v100l` thirty, and `v100xl`
two — so the specialized partitions are small and contended. Default to
CPU/MPI on `rome`; reach for a GPU partition only when the code actually
offloads to NVIDIA GPUs, and for `xlarge` only when the bottleneck is memory
inside one node.

These shapes came from the source port and still need a live refresh with
`ccc_mpinfo`.

## Every job needs three site choices

An Irene job must declare:

- `attributes.queue_name`, rendered as `#MSUB -q`; a partial request defaults
  to `rome`.
- `attributes.account`, rendered as `#MSUB -A`; use `get_projects` because a
  project is only valid on the partitions listed by `ccc_compuse`.
- `attributes.custom_attributes.filesystems`, rendered as `#MSUB -m`.
  `scratch,work` is the normal default; include `store` only when needed.
  Without `-m`, compute nodes cannot reach scratch, work or store at all.

`resources.process_count` becomes total tasks (`-n`),
`cpu_cores_per_process` becomes cores per task (`-c`), `node_count` becomes
`-N`, and `exclusive_node_use` becomes `-x`. Durations are rendered as total
seconds for `-T`. Set custom `qos` when the current `ccc_mqinfo` output shows
that it is appropriate.

For a parallel or threaded job, the backend supplies `ccc_mprun` when needed.
The submission directory is `${BRIDGE_MSUB_PWD}`. Default output names are
`irene_<job-id>.o` and `irene_<job-id>.e`.

### The underlying directives

Worth knowing when reading someone else's script, or writing one by hand:

| directive | meaning |
|---|---|
| `-r <name>` | job name |
| `-q <partition>` | partition — **mandatory** |
| `-A <project>` | project charged — **mandatory** |
| `-m <filesystems>` | filesystems the job needs — **mandatory** |
| `-n <tasks>` | total parallel tasks |
| `-c <cores>` | cores per task (OpenMP threads, memory, or GPUs) |
| `-N <nodes>` | node count; Bridge usually infers it |
| `-x` | exclusive node use |
| `-T <seconds>` | wall time; defaults to 7200 |
| `-Q <qos>` | QoS, e.g. `normal`, `test`, `long` |
| `-E "<slurm opts>"` | pass raw Slurm options through Bridge |

The documented 7200-second default is rarely what you meant, and an accurate
wall time gets a job backfilled sooner, so set `-T` deliberately.

A plain MPI job looks like this:

```bash
#!/bin/bash
#MSUB -r MyJob_Para
#MSUB -n 32
#MSUB -T 1800
#MSUB -o example_%I.o
#MSUB -e example_%I.e
#MSUB -q rome
#MSUB -A <project>
#MSUB -m scratch,work
set -x
cd ${BRIDGE_MSUB_PWD}
ccc_mprun ./a.out
```

A hybrid MPI/OpenMP job asks for tasks with `-n`, cores per task with `-c`,
and sets `OMP_NUM_THREADS` to match `-c`.

Besides `BRIDGE_MSUB_PWD`, Bridge sets `BRIDGE_MSUB_JOBID`,
`BRIDGE_MSUB_MAXTIME`, `BRIDGE_MSUB_NPROC`, `BRIDGE_MSUB_NCORE` and
`BRIDGE_MSUB_REQNAME` inside a job.

## Connecting and interactive use

SSH details are site- and project-specific: configure an alias such as
`irene` in `~/.ssh/config`, then point `ssh.host` at that alias.

Login nodes are shared. They are for editing, compiling modest code, staging
files, checking queues and submitting jobs. Anything heavier than a laptop
workload belongs in an allocation.

Two interactive modes are documented:

- `ccc_mprun -K -p <partition> -n <tasks> -T <seconds> -A <project>` holds an
  allocation while leaving you on the login node; launch steps inside it with
  `ccc_mprun`.
- `ccc_mprun -s -p <partition> -c <cores> -m <filesystems>` opens a shell on a
  compute node. Single-node only, and the right tool for compiling,
  post-processing and short threaded work.

Remote visualization is `ccc_visu virtual -p <partition>` or
`ccc_visu console -p <partition>`.

## GPU allocation

Bridge allocates GPUs **indirectly, through cores per task** — there is no
GPU count flag. The ratio is cores per node divided by GPUs per node, the
`CpN` and `GpN` columns of `ccc_mpinfo`. On a partition with 128 cores and
four GPUs per node, that is 32 cores per GPU:

- `-n 1 -c 32` → one GPU
- `-n 1 -c 64` → two GPUs
- `-n 4 -c 32` → four GPUs across four tasks

A job-total `resources.gpus` can be translated when GPUs divide evenly across
its tasks; otherwise state `cpu_cores_per_process` explicitly after checking
the live ratio. Load `nvhpc` for NVIDIA compilers and GPU libraries. GPU code
still launches with `ccc_mprun`, and topology-aware binding goes through
Bridge, e.g. `#MSUB -E "--gpu-bind=closest"`.

## Projects, status, and accounting

`ccc_compuse` lists project/partition associations and fair-share standing;
the backend verifies the chosen combination again immediately before
submission. `ccc_myproject` reports project consumption. `ccc_mpp -u $USER`
and `ccc_mstat -u` show live jobs, while `ccc_macct <job-id>` provides
finished-job accounting — memory, steps, elapsed time, state, and energy
where available. `ccc_mdel` cancels jobs and `ccc_malter -T` reduces a queued
or running job's time limit.

Consumption cuts both ways, which is worth telling a user before they sit on
an allocation: under-consumption can get awarded hours reduced for some
project types, while over-consumption lowers priority and can leave jobs
running only as bonus jobs.

TGCC discourages scheduler polling faster than roughly one or two aggregate
queries per minute, and explicitly prohibits `watch` on scheduler or Bridge
commands. Completed jobs are therefore queried by ID rather than aggressively
polled.

## Storage

Bridge's mandatory `-m` declaration controls which of these a job can see.

| space | kind | notes |
|---|---|---|
| HOME | NFS, backed up | small — 5 GB documented. Sources and submit scripts |
| SCRATCH | fast Lustre | 100 TB and 2M inodes per group documented. **Purged** |
| WORK | Lustre, not backed up | shared sources, binaries, working data |
| STORE | Lustre + HSM | archive; prefer large or packed files |
| TMP | local zram | purged after each job |
| SHM | tmpfs, ~half of RAM | allocation lifetime; recommended for small temp files |

SCRATCH purges files not accessed for 60 days and removes empty directories
older than 30 days — so results left there will disappear. `ccc_quota` shows
current quotas and `ccc_will_purge` previews purge candidates.

For STORE's HSM workflows use `ccc_hsm`, `ccc_pack` and `ccc_unpack`. For
files larger than about 10 GB where parallel I/O benefits from striping, use
`lfs setstripe`.

## Software and containers

The `ccc` module supplies the site environment and is mandatory. `datadir/own`
and `dfldatadir/own` define the data-space variables `CCCSCRATCHDIR`,
`CCCWORKDIR` and `CCCSTOREDIR`; shared spaces use `datadir/<space>`,
`dfldatadir/<space>` and `extenv/<space>`.

Open MPI and Wi4MPI are the supervised, recommended MPI paths; Intel MPI and
others are provided best-effort. Compile with `mpicc`, `mpic++`, `mpif77` or
`mpif90` and launch with `ccc_mprun`.

Modules worth knowing: `nvhpc`, `mpi/openmpi`, `mpi/intelmpi`, `mpi/wi4mpi`,
`mkl`, `scalapack`, `fftw3/gnu`, `fftw3/mkl`, plus Python, Julia, profilers,
debuggers and visualization tools. Query `module avail` or
`module help <product>` for current versions — installed products change.

Containers use **pcocc**, not Apptainer or Singularity. Build an OCI image
with Docker or Podman elsewhere, copy it over, and import it:

```bash
pcocc-rs image import docker-archive:my_image.tar my_image
```

Run it locally with `pcocc-rs run my_image -- <cmd>`, or in a batch job
through Bridge with `ccc_mprun -C my_image -- <cmd>`. Cluster data spaces are
mounted by default; extra mounts pass through Bridge as
`-E '--ctr-mount src=<source>,dst=<target>'`.

## Validation status

The separate IreneAgent migration was checked through offline rendering and
synthetic parser equivalence, not a live TGCC connection. This hub port also
has not submitted a real Irene job. Its SSH/passfile path, current Bridge
output, project parser, resource parser, and tiny job workflow must all be
checked live before the integration is marked tested.
