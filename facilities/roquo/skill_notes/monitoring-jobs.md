## Accounting is available

ROQUO runs Slurm with accounting, so job history is queryable, not just
the live queue. `get_job_status` / `get_job_statuses` work for finished
jobs, and the underlying `sacct -j <jobid> -o
JobID,State,ExitCode,Elapsed,MaxRSS` is what the manual points users at
for a post-mortem.

## Queue reasons that mean something specific here

**`QOSMaxWallDurationPerJobLimit` on a `work` job** — the job asked for
more than 3 days without `qos: long`. It will **never start**. Nothing
rejected it at submit time, so it looks like an ordinary wait. If you see
this reason, stop waiting and resubmit; `submit_job` through this plugin
refuses the combination up front, so a job in this state was almost
certainly submitted by hand.

**A `roquo` job waiting with `--switches=1`** — the topology request waits
up to five minutes for nodes inside one rack before giving up and spanning
racks. A short wait here is normal and self-resolving.

## Finding a job's output

Jobs commonly write to `%x_%j.log` relative to the submission directory.
If a job wrote results to `$SLURM_SCRATCH` (`/scratch/<jobid>`), **they
are gone** — that area is node-local and deleted when the job ends. When a
user can't find output from a completed job, this is the first thing to
check, and the only fix is to resubmit with the copy-out step added.

## Node names

Compute nodes are `qrNNnMM` (rack `qr01`–`qr08`, e.g. `qr01n01`); `work`
nodes are `work01`–`work05`. A node name tells you which partition a job
actually ran on, which matters because the two have different
architectures — if something behaved oddly, confirming it ran on `qr*` vs
`work*` is a fast way to catch an architecture mismatch.

`get_drained_nodes(facility="{{SLUG}}")` reports nodes Slurm has taken out
of service, which is worth checking before concluding a partition is
simply busy.
