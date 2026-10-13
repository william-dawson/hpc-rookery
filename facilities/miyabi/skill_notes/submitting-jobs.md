Miyabi runs PBS Professional. There is no safe queue default: choose among
CPU (`-c`), full GH200 (`-g`), and MIG (`-mig`) queues after checking
`get_resources(facility="{{SLUG}}")` and the current limits in the bundled
guide.

Every job needs `attributes.account`, rendered as
`#PBS -W group_list=<project>`. If the user omits it, the backend reads their
own `defaults.group`/`MIYABI_GROUP`; it never guesses or bundles a real group.

Resource mapping:

- `node_count` -> PBS `select` chunks (nodes on `-c`/`-g`, MIG instances on
  `-mig`).
- `processes_per_node` -> `mpiprocs`.
- `cpu_cores_per_process` -> `ompthreads`.
- `memory` -> per-chunk `mem=<N>gb`.

Full-GPU and MIG allocation is selected by the queue, not a PBS GPU flag.
Leave `resources.gpus=0`, or make it equal `node_count`. Use debug queues only
for short validation jobs. The earlier port smoke-tested C OpenMP, one- and
two-node C MPI, one full G node, and one `2g.24gb` MIG instance on 2026-07-13;
this hub port still needs a new live job when access returns.
