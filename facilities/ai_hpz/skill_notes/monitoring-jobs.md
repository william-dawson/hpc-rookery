hpz's Slurm has **no accounting**, which limits what monitoring can show:

- `get_job_status` reads `squeue` while a job is pending or running, then
  `scontrol show job` for a short time after it ends. Once Slurm forgets the
  job, the status becomes UNKNOWN / "not found" — that is expected, not a
  failure. Read the job's stdout/stderr with `fs_tail` instead.
- `get_job_statuses` with an empty id list shows only the current live
  queue; there is no multi-day history.
- `get_resources` and `get_drained_nodes` work (sinfo). `get_projects` and the
  allocation tools are unsupported.

So check a job promptly after it finishes if the exit code matters, and
always point the user at the output files.

Common hpz failures:

- GPU job pending with reason `Resources` — another job holds the single
  GPU; it starts when that job ends.
- `Requested node configuration is not available` at submit — more than
  one GPU, or more CPUs/memory than the node has.
- GROMACS GPU out-of-memory or very slow — some job is using the GPU
  without having requested it (Slurm does not block that). Ask the user
  before inspecting with `nvidia-smi` (remote-command workflow).
- Pending with reason `Resources` — other jobs hold the CPUs/memory; lower
  the request or wait.
- `gmx: command not found` / `nvcc: command not found` — add
  `source /usr/local/gromacs/bin/GMXRC` or the HPC SDK `module use`/`module
  load` lines to `pre_launch`.
