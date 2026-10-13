# Octopus orientation

Octopus is RIKEN R-CCS's small dual-vendor GPU cluster: three NVIDIA H200
nodes and one AMD MI300X node under Slurm. This guide was migrated from the
separate Octopus-Agent repository. That port was checked offline against its
earlier renderer, but this hub integration could not be exercised on the
live cluster. Treat queue, module, and storage values as recorded facts to
refresh when access returns.

## Connection and accounting

Connect to the management node through the SSH alias or hostname issued for
your account. The agent needs non-interactive key authentication; it cannot
answer a password prompt. When the agent itself runs on an Octopus front end,
configure `ssh.host` as `localhost`.

Slurm accounting is enabled. Every user has a server-side `DefaultAccount`,
so most jobs should omit `attributes.account`. Users with several projects
can call `get_projects` and select one of their own associations. No real
account identifier is bundled here because it would belong to somebody else.

## Hardware and partitions

Each node has 192 x86_64 CPU cores, about 2.3 TB of usable memory, and eight
GPUs. The partition determines the GPU vendor:

| Partition | Nodes in pool | Accelerator | Recorded time limit |
|---|---:|---|---|
| `h200` | 3 | NVIDIA H200, 8/node | 8 hours |
| `h200-long` | 3 | NVIDIA H200, 8/node | unlimited |
| `mi300x` | 1 | AMD MI300X, 8/node | 8 hours |
| `mi300x-long` | 1 | AMD MI300X, 8/node | unlimited |

The `-long` names address the same hardware with a different time policy;
they are not separate capacity. The recorded partition inventory limits a
job to one node. The hub enforces that dated limit until a live Slurm query
proves it should be widened.

There is no cross-vendor execution layer. A CUDA build belongs on `h200` or
`h200-long`; a ROCm build belongs on `mi300x` or `mi300x-long`. Choose the
partition from the software stack, not merely from current idle capacity.

## Job resource shape

GPU requests use untyped, partition-scoped GRES:

```text
#SBATCH --partition=h200
#SBATCH --gres=gpu:2
```

The partition supplies the type; do not render `gpu:h200` or `gpu:mi300x` in
the request. A job may request one through eight GPUs. A partial JobSpec
defaults to partition `h200` and one GPU.

The hub currently accepts one node, up to 192 requested CPU cores, and up to
2,317,610 MiB of memory. The non-long partitions reject durations beyond
eight hours before submission. These validations come from the bundled
inventory and need a live refresh if administrators change the partitions.

## Modules and containers

Octopus uses Tcl environment-modules, not Lmod. Module contents and versions
change, so inspect them live rather than treating this dated inventory as an
installation promise:

- H200 work uses CUDA or NVIDIA HPC SDK; Open MPI is also recorded.
- MI300X work uses ROCm.
- Singularity and Go are vendor-neutral entries in the recorded tree.

Load the matching toolchain in the submitted script. A CUDA binary will not
become a ROCm binary by moving queues, or vice versa.

For a `JobSpec.container`, the shared Slurm backend selects GPU passthrough
from the partition: `--nv` on H200 and `--rocm` on MI300X. A container that
starts but sees no accelerator usually indicates a partition/toolchain or
passthrough mismatch.

## Storage

The recorded storage model is one shared Lustre filesystem rooted at
`/lustre`, with homes under `/lustre/home/<user>`. There is no recorded
node-local scratch tier. Inputs, outputs, and job scripts therefore remain
on the shared filesystem across both GPU pools.

## Monitoring and failures

Slurm accounting provides durable history through `sacct`; live wait reasons
come from `squeue`, current partition occupancy from `sinfo`, and drained
nodes from `sinfo -R`. Common signals are:

- `OUT_OF_MEMORY`: reduce memory use or request a larger valid resource
  share.
- `TIMEOUT`: reduce the run or move from an eight-hour partition to its
  matching `-long` partition.
- CUDA/ROCm library or device errors: confirm the submitted partition matches
  the workload's build.
- A container with no visible GPU: inspect the retained script and verify
  `--nv` versus `--rocm` follows the partition.
- Account or QOS rejection: query the user's real project associations and
  allocation rather than guessing another value.

When access returns, run the hub doctor, read-only live smoke suite, one tiny
H200 job, and one tiny MI300X job. Confirm submission, status, output,
account omission, GRES allocation, and vendor-specific container rendering.
