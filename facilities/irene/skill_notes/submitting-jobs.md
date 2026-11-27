Default ordinary CPU/MPI work to `rome`. Use `xlarge` for large single-node
memory and the `v100` family only for GPU-capable software. Valid partitions
are `rome`, `xlarge`, `v100`, `v100l`, `v100l-os` and `v100xl`.

## Three mandatory site choices

Every Irene job needs a partition (`queue_name`), a TGCC project (`account`),
and filesystems (`custom_attributes.filesystems`, normally `scratch,work`).
Bridge rejects a job missing any of them, and without `-m` a compute node
cannot reach scratch, work or store at all.

**Do not submit on a configured default account.** `defaults.account` is a
convenience for remembering a project, not permission to spend it. Every
submission must carry an explicit `attributes.account`: if the user has not
named one, call `get_projects(facility="{{SLUG}}")` and ask which association
to charge. A project is only valid on the partitions `ccc_compuse` lists for
it, and the backend rechecks that pair at submission time.

## Mapping a JobSpec onto Bridge

`process_count` is total tasks (`-n`), `cpu_cores_per_process` is cores per
task (`-c`), `node_count` is `-N`, `exclusive_node_use` is `-x`, and
`duration` is rendered as seconds for `-T`. The launcher is `ccc_mprun`, which
the backend supplies for multi-task work.

A plain MPI job, once the user has chosen a project:

```json
{
  "name": "irene-mpi",
  "executable": "./a.out",
  "launcher": "ccc_mprun",
  "resources": {"process_count": 32},
  "attributes": {"queue_name": "rome", "duration": 1800,
                 "account": "gen12345",
                 "custom_attributes": {"filesystems": "scratch,work"}}
}
```

Hybrid MPI/OpenMP — ask for tasks with `process_count`, cores per task with
`cpu_cores_per_process`, and set `OMP_NUM_THREADS` to match:

```json
{
  "name": "irene-hybrid",
  "executable": "./a.out",
  "launcher": "ccc_mprun",
  "environment": {"OMP_NUM_THREADS": "4"},
  "resources": {"process_count": 8, "cpu_cores_per_process": 4},
  "attributes": {"queue_name": "rome", "duration": 1800,
                 "account": "gen12345",
                 "custom_attributes": {"filesystems": "scratch,work"}}
}
```

Set `custom_attributes.qos` only when the current `ccc_mqinfo` output shows it
is appropriate, and pass raw Slurm options through `custom_attributes` as
Bridge's `-E` when something has no Bridge equivalent.

## GPUs come from cores, not a GPU flag

Bridge has no GPU count option: a GPU is allocated indirectly by reserving
cores per task, at a ratio of cores per node divided by GPUs per node — the
`CpN` and `GpN` columns of `ccc_mpinfo`. On a 128-core, 4-GPU node that is 32
cores per GPU, so `-c 32` gets one GPU and `-c 64` gets two. A job-total
`resources.gpus` can be translated when GPUs divide evenly across tasks;
otherwise check the live ratio with `get_resources` and set
`cpu_cores_per_process` yourself. GPU code still launches with `ccc_mprun`.

## Containers

Use `container.image` with a pcocc image name — not an Apptainer or Docker
URI. The backend renders `ccc_mprun -C <image> -- <cmd>`.

Preview the rendered `#MSUB` script and ask permission before submitting.
