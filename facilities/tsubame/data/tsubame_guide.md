# TSUBAME4.0

TSUBAME4 is Science Tokyo's GPU-first system. Its 240 compute nodes each have
two 96-core AMD EPYC 9654 processors, 768 GiB of memory, four NVIDIA H100 GPUs,
and local NVMe. It uses Altair Grid Engine.

## The important scheduling model

TSUBAME jobs are sized by a fixed **resource type**, not by independently
choosing nodes, cores, memory, and GPUs. For example, `node_f=2` requests two
full units (192 cores and four H100s per unit), while `gpu_1=1` requests one GPU
with eight CPU cores and 96 GB. A job uses one resource type throughout.

| type | cores | memory (GB) | GPUs |
|---|---:|---:|---:|
| `node_f` | 192 | 768 | 4 |
| `node_h` | 96 | 384 | 2 |
| `node_q` | 48 | 192 | 1 |
| `node_o` | 24 | 96 | 0.5 (MIG) |
| `gpu_1` | 8 | 96 | 1 |
| `gpu_h` | 4 | 48 | 0.5 (MIG) |
| `cpu_160`, `cpu_80`, `cpu_40`, `cpu_16`, `cpu_8`, `cpu_4` | as named | proportional | 0 |

Set the type with `attributes.custom_attributes.resource_type`; it defaults to
`node_f`. `resources.node_count` is the number of those units. Do not also set
generic GPU or memory fields: the type already fixes them. Wall time is limited
to 24 hours. Normal jobs leave `queue_name` blank; `prior` is the documented
subscription queue.

## Groups, points, and trial jobs

Normal compute is charged in TSUBAME points to a group supplied to `qsub -g`.
Use `get_projects` to list the current user's groups and query point balances
live because they change. `TSUBAME_GROUP` overrides `defaults.group` in the user
configuration.

No group means a free trial run: at most two resource units, three minutes, and
priority `-5`. This is useful for confirming that a program launches. Priorities
`-4` and `-3` cost more points and require a charged group.

## Software and launching

Software is provided through environment modules. Query versions live. CUDA and
the NVIDIA HPC SDK support GPU work; Intel oneAPI and Open MPI are also common.
If a script inherits the submission environment with `-V`, run `module purge`
before loading the job's modules. `LD_LIBRARY_PATH` and `LD_PRELOAD` are not
forwarded by `-V`, so set them in the script when needed.

The resource request does not launch MPI for you. Put an explicit matching
launcher in `launcher`: Intel MPI commonly uses `mpiexec.hydra -ppn ... -n ...`,
while Open MPI uses `mpirun -npernode ... -n ...`. Set
`cpu_cores_per_process` so the generated script exports `OMP_NUM_THREADS`, or
set it explicitly in `environment`.

Apptainer jobs automatically bind `/gs`, `/apps`, and `/home`; GPU resource
types also receive `--nv`.

## Storage and job output

Use `/home/<group>/<user>` for small persistent files and
`/work/<group>/<user>` for ordinary work. Purchased group storage is under
`/gs/fs` and `/gs/bs`. `/local` is fast node-local scratch and is erased when
the allocation ends, so copy results back before exit.

Live jobs appear in `qstat`; completed records move to `qacct`. Default output
files are normally `<job-name>.o<job-id>` and `<job-name>.e<job-id>` in the
submission directory. Check those, the point balance, resource type, wall-time,
modules, and thread count when diagnosing a failure.

## Validation status

This port was prepared without TSUBAME access. Its dialect comes
from the separate Tsubame4-Agent implementation, but the hub's SSH path,
scheduler commands, parsers, and tiny job workflow still need fresh live
validation before this integration is marked tested.
