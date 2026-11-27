naur's Slurm has **no working accounting** (`sacct` fails with a refused
connection), which limits what monitoring can show:

- `get_job_status` reads `squeue` while a job is pending or running, then
  `scontrol show job` for about five minutes after it ends. Once Slurm
  forgets the job, the status becomes UNKNOWN / "not found" — that is
  expected, not a failure. Read the job's stdout/stderr with `fs_tail`
  instead.
- `get_job_statuses` with an empty id list shows only the current live
  queue; there is no multi-day history.
- `get_resources` and `get_drained_nodes` work (sinfo), but they report the
  whole Slurm cluster: `prado`, `shannon` and `backus` are other machines.
  Only the `naur` row matters here, and a down sibling node (e.g. `backus`)
  does not affect naur jobs. `get_projects` and the allocation tools are
  unsupported.

So check a job promptly after it finishes if the exit code matters, and
always point the user at the output files.

Common naur failures:

- `Requested node configuration is not available` at submit — a memory
  request (never allowed here), more than one GPU, more than 72 CPUs, or
  more than one node.
- `No devices found` / CUDA finds no GPU — the job did not set `gpus=1`.
  Slurm hides the GPU from jobs that did not request it.
- GPU job pending with reason `Resources` — another job holds the single
  GPU; it starts when that job ends.
- CPU job pending with reason `Resources` — other jobs hold the cores; lower
  the request or wait.
- `nvcc` / `nvc` / `mpirun: command not found` — add `module load cuda-13.2`
  or `module load nvhpc/26.9` to `pre_launch`.
- `Exec format error` — an x86 binary was brought to this Arm host; rebuild
  it on naur.
- Out-of-memory kills with no Slurm message — memory is not limited per job,
  so another job may have exhausted the node. Ask the user before inspecting
  with `free`/`top` (remote-command workflow).
