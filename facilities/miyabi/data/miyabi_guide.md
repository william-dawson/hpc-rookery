# Miyabi orientation

This is the practical guide for driving JCAHPC Miyabi through the unified HPC
agent. It was migrated from the separate Miyabi-Agent guide, which was built
from login-node inspection and real smoke jobs on 2026-07-13. The hub port
could not be rechecked live because Miyabi access was unavailable. Treat
dated queue limits and module versions as orientation, then refresh them with
the commands below when access returns.

## Connection model

Run the agent and MCP processes **on a Miyabi login node**, with:

```json
{
  "ssh": {"host": "localhost"},
  "defaults": {"group": "<your-project-group>"}
}
```

`localhost` means direct local execution. It does not start SSH and does not
bypass Miyabi's interactive two-factor login. Remote SSH automation is not a
supported configuration. Every PBS job also needs the user's own project
group; never copy a group identifier from another person's example.

## System shape

Miyabi combines three resource families behind PBS Professional:

| Family | Stable shape | Queue suffix |
|---|---|---|
| Miyabi-G | 1,120 GH200 nodes: 72-core NVIDIA Grace CPU plus one 96 GB H100 | `-g` |
| Miyabi-G MIG | Partitioned H100 service; a `2g.24gb` instance was smoke-tested | `-mig` |
| Miyabi-C | 190 CPU nodes: two 56-core Intel Xeon Max 9480 CPUs, 128 GiB | `-c` |

The systems use a 200 Gbps InfiniBand NDR fabric. `/home` and `/work` are
Lustre filesystems. The login node is not a representative compute node: the
inspected login node had Grace CPUs but no visible H100.

## Queues and current limits

Known submission queues are:

- Full GPU: `debug-g`, `short-g`, `regular-g`, `interact-g`, `coupler-g`.
- MIG: `debug-mig`, `short-mig`, `regular-mig`, `interact-mig`.
- CPU: `debug-c`, `short-c`, `regular-c`, `interact-c`, `coupler-c`.
- Pre/post-processing: `prepost`.

There is no safe default across those families. Before choosing, query live
state and the account's current limits:

```sh
qstat --rsc -x
qstat --rscuse
qstat --limit
qstat --scal
```

In the 2026-07 observation, debug queues allowed 30 minutes; short queues
allowed 8 hours; regular queues generally allowed up to 48 hours, with lower
limits at the largest node counts. Those are dated observations, not values
to hardcode into a new job without checking.

## PBS job shape

Miyabi requires all three of these:

```sh
#PBS -q <queue>
#PBS -W group_list=<your-project-group>
#PBS -l select=<chunks>:mpiprocs=<processes-per-chunk>
```

`JobSpec.resources.node_count` becomes the PBS select/chunk count.
`processes_per_node` becomes `mpiprocs`, and `cpu_cores_per_process` becomes
`ompthreads`. A byte-valued `memory` request is rounded upward to GiB and
rendered as `mem=<N>gb`. `process_count` is also accepted when it divides
evenly across the requested chunks.

On full-GPU queues, each select chunk is one full GPU node. On MIG queues,
each chunk is one MIG instance. The queue selects the accelerator; there is
no separate PBS GPU flag. A `resources.gpus` value may be omitted, or must
equal `node_count` so the specification cannot imply a different allocation.

PBS does not automatically enter the submission directory. Generated scripts
explicitly `cd "$PBS_O_WORKDIR"`, or enter `spec.directory` when supplied.
Output is merged by default and normally appears under the submission
directory with PBS's job-name/job-sequence naming.

## Modules and applications

Miyabi's Environment Modules tree is hierarchical and architecture-specific:

- Miyabi-G/login uses the `LNG` hierarchy. The NVIDIA `nvidia/25.9` and
  `nv-hpcx/25.9` stack was smoke-tested.
- Miyabi-C uses the `MC` hierarchy. `gcc/11.4.1` and `ompi/4.1.6` were
  smoke-tested for OpenMP and one-/two-node MPI.

`module avail` is context-sensitive: loading a compiler reveals libraries
built for it, and loading MPI reveals another layer. A sensible inspection is
`module purge`, `module avail`, load the parent compiler/toolkit, then run
`module avail` again. Do not assume a module visible on Miyabi-G exists on
Miyabi-C. Query versions live rather than freezing the 2026-07 inventory.

## Storage, quota, and tokens

- `/home/<user>` is for configuration and small files. The inspected account
  reported a 50 GiB limit.
- `/work/<group>` is project work storage.
- `/work/<group>/<user>` is the natural location for job inputs and outputs.

Refresh account-specific values with:

```sh
show_quota -g <your-project-group> -v
show_token -g <your-project-group>
```

These values are per project and user, so the guide deliberately contains no
real group name, balance, or expiry to reuse.

## Monitoring and diagnosis

Useful commands exposed by Miyabi's wrapper layer include:

- `qstat -f <jobid>` for full live job details and exit status once retained.
- `qstat -H --hday 2 --hnum 100` for short history (at most three days).
- `qdel <jobid>` to cancel.
- `tracejob <jobid>` for server, scheduler, and accounting events.
- `qps <jobid>` and `qsar` for a running job's processes and utilization.
- `qstat --nodeuse`, `--miguse`, or `--rscuse` for occupancy.

The compact `qstat -H` history says `FINISH` but does not expose application
exit status. Treat that as scheduler completion, then inspect output or
`tracejob` before claiming the application succeeded. `qalter` was not usable
through the site's user wrapper during live inspection; cancel and resubmit
instead of assuming a queued job can be edited.

## Evidence from the earlier live port

The separate Miyabi-Agent port completed these small jobs on 2026-07-13:

- Miyabi-C GCC OpenMP with four threads.
- Miyabi-C Open MPI on one node and across two nodes.
- A full Miyabi-G GH200 node running a CUDA managed-memory vector addition.
- One `2g.24gb` MIG instance running the same CUDA test.

That evidence supports the PBS dialect implemented here. It does not replace
a new hub-level doctor, read-only smoke test, and tiny real job when access is
restored.
