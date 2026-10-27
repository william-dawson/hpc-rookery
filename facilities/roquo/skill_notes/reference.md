## Provenance — read this before quoting a number

ROQUO's bundled guide was written from the operator's online manual, and
**this port has not been validated against the live system.** Nothing here
has been confirmed by running it. Treat specifics — quotas especially,
which the manual itself marks TBD — as a starting point, and prefer a live
query (`get_resources`, `run_command_on_cluster`) over quoting the guide
when the answer matters.

The manual lives at `https://portal.roquo.qc.r-ccs.riken.jp/manual/en/`
and is the authority; say so if the user needs certainty.

## The facts most likely to be asked

- **Two architectures.** Login and `work` nodes are x86_64; GPU compute
  nodes are aarch64. This explains most "it worked yesterday on the login
  node" reports.
- **Two partitions**: `roquo` (135 GB200 nodes, 4 GPUs each, 8 racks) and
  `work` (5 x86_64 CPU-only nodes). The per-rack partitions were removed
  on 2026-10-13.
- **GPU dialect**: `--gres=gpu:N`, per node, N ≤ 4 — not RIKYU's job-total
  `--gpus=N`.
- **GPU generation**: GB200/Blackwell, compute capability 10.0
  (`sm_100` / `cc100`).
- **Storage**: `/home/hps1/<user>` (small), `/projects/hps1/<project>`
  (Lustre, persistent, shared), `$SLURM_SCRATCH` (node-local, deleted at
  job end).
- **Quotas**: not published — read them with
  `lfs quota -h -u $USER /home/hps1` and `lfs df -h /projects/hps1`.

## Where to look things up

`search_docs(facility="{{SLUG}}", query=...)` searches the bundled guide,
which covers login, partitions, GPU plans, QOS, storage, modules, MPI,
containers and failure modes. `get_facility(facility="{{SLUG}}")` returns
the same facts as structured data, including the ROQUO-E* error-code table
and the per-QOS wall-time limits.

Both work without SSH configured, so they're the right tools for
orientation before the user has access.
