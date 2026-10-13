# TGCC Irene

Irene is a CPU-first supercomputer at CEA's TGCC. Its scheduler is Slurm
underneath, but users work through TGCC Bridge: batch scripts contain `#MSUB`
directives, `ccc_msub` submits them, and parallel programs launch with
`ccc_mprun`.

## Partitions

The normal target is `rome`, recorded as 2,286 AMD Rome nodes with 128 cores
and about 228 GiB per node. Use the specialized partitions only when the
workload needs them:

| partition | recorded shape | purpose |
|---|---|---|
| `rome` | 128 CPU cores/node | ordinary CPU, MPI, and hybrid production |
| `xlarge` | 112 cores, about 3 TiB, one P100 | single-node large-memory work |
| `v100` | 40 cores and four V100 GPUs/node | multi-GPU work |
| `v100l` / `v100l-os` | 36 cores and one V100/node | GPU work with more memory per GPU |
| `v100xl` | 72 cores, about 2.9 TiB, one V100 | large-memory GPU work |

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

`resources.process_count` becomes total tasks (`-n`),
`cpu_cores_per_process` becomes cores per task (`-c`), `node_count` becomes
`-N`, and `exclusive_node_use` becomes `-x`. Durations are rendered as total
seconds for `-T`. Set custom `qos` when the current `ccc_mqinfo` output shows
that it is appropriate.

For a parallel or threaded job, the backend supplies `ccc_mprun` when needed.
The submission directory is `${BRIDGE_MSUB_PWD}`. Default output names are
`irene_<job-id>.o` and `irene_<job-id>.e`.

## GPU allocation

Bridge allocates GPUs indirectly through cores per task. The relevant live
ratio is cores per node divided by GPUs per node (`CpN/GpN` in
`ccc_mpinfo`). A job-total `resources.gpus` can be translated when GPUs divide
evenly across its tasks; otherwise state `cpu_cores_per_process` explicitly
after checking the live ratio. GPU code still launches with `ccc_mprun`.

## Projects, status, and accounting

`ccc_compuse` lists project/partition associations and fair-share standing;
the backend verifies the chosen combination again immediately before
submission. `ccc_mpp -u $USER` shows live jobs, while `ccc_macct <job-id>`
provides finished-job accounting. `ccc_mdel` cancels jobs and `ccc_malter -T`
changes a queued or running job's time limit.

TGCC discourages scheduler polling faster than roughly one or two aggregate
queries per minute and prohibits `watch` on scheduler commands. Completed jobs
are therefore queried by ID rather than aggressively polled.

## Storage

HOME is small and backed up. SCRATCH is fast Lustre with a purge policy, WORK
is persistent but not backed up, and STORE is an HSM-backed archive. Bridge's
mandatory `-m` declaration controls which of these are visible to a job. TMP
and SHM are allocation-lifetime temporary spaces. Use `ccc_quota` for current
quotas and `ccc_will_purge` to preview purge candidates.

## Software and containers

The `ccc` module supplies the site environment. Data modules define variables
such as `CCCSCRATCHDIR`, `CCCWORKDIR`, and `CCCSTOREDIR`. Open MPI and Wi4MPI
are the commonly supervised MPI paths; query `module avail` for current
versions. TGCC containers use pcocc and run in batch as
`ccc_mprun -C <image> -- <command>`.

## Validation status

The separate IreneAgent migration was checked through offline rendering and
synthetic parser equivalence, not a live TGCC connection. This hub port also
has not submitted a real Irene job. Its SSH/passfile path, current Bridge
output, project parser, resource parser, and tiny job workflow must all be
checked live before the integration is marked tested.
