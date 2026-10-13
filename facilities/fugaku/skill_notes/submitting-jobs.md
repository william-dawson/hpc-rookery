Fugaku is **A64FX (Arm SVE) and has no GPUs** — never set `resources.gpus`
or `resources.gpu_cores_per_process`; both are rejected outright.

## Workflow

1. **Choose a PJM resource group** for `attributes.queue_name` — there is
   no default, deliberately, because which groups an account may use
   differs per project. `small` (1–384 nodes, up to 72h), `large` (385+
   nodes, up to 24h), `int` (interactive), `f-pt` (priority, see below), or
   a `spot-*` low-priority variant. Confirm the real min/max/default for
   this account with
   `run_command_on_cluster(facility="{{SLUG}}", command="pjacl --rg small")`.
2. **Every job needs a project group.** Set `attributes.account`
   explicitly, or rely on `defaults.group` in the config file (or
   `{{ENV_PREFIX}}_GROUP`) — `submit_job` raises a clear error if neither
   is set. The shared `fugaku` group **cannot submit jobs**. If the
   resolved group is `trial` (the "Startup Project" every new account
   gets), only the `spot-*` resource groups work — `small`/`large`/`int`
   are rejected. Check `run_command_on_cluster(facility="{{SLUG}}",
   command="id")` for the account's real project groups before assuming
   `small` is available.
3. **Set `resources.node_count`.** For MPI work also set
   `resources.processes_per_node` (renders as PJM's
   `--mpi "max-proc-per-node=N"`) or `resources.process_count` for a total
   rank count. An `mpiexec -n <N>` launcher is added automatically whenever
   more than one task is requested — don't add it yourself unless you need
   non-default `mpiexec` flags (set `launcher` explicitly to override).
4. **Declare second-layer storage.** If the job touches anything outside
   `$HOME` — a group data volume, or Spack — set
   `attributes.custom_attributes["gfscache_volume"]` (e.g. `"/vol0004"`)
   or rely on the configured default. Without it `pjsub` rejects the job.

   **Declare exactly one volume.** A comma-separated value such as
   `/vol0002,/vol0004` is accepted by `pjsub` at submission, queues
   normally, and then fails the pre-execution gate check minutes later:
   state `ERR`, `REASON : GATE CHECK`, **no output file and no exit code**.
   That silent, delayed failure is why it is worth catching — `submit_job`
   now rejects a comma-containing value up front.

   Verified live across eight jobs, varying one thing at a time: every job
   carrying the comma value failed (at 5 *and* 10 minute elapse limits, so
   wall time is irrelevant), and every job with a single volume or none
   ran to completion (at 5, 6, 9 and 10 minutes). The `small-s5` sub-group
   that appears in `pjstat -s` is a red herring — successful jobs run in
   it too.

   The correct syntax for declaring **more than one** volume is not
   documented in the bundled guide or in `pjsub --help`; both only ever
   show a single `/vol000N`. Ask RIKEN rather than guessing a separator.
5. **Leave `stdout_path`/`stderr_path` unset** — PJM has no flag for
   redirecting them. Output always lands at `<name>.<job_id>.out`/`.err` in
   the submission directory. Set `spec.directory` if you want it elsewhere.

## Jobs run from the group data area, not `$HOME`

Point `directory` at something under `/vol0n0m/data/<groupname>/` for
every job. Home (`/home/<user>`) is a 20 GiB per-user area meant for
code and scripts; the group data area carries ~5 TiB per group and is
the intended job-execution space. Large outputs (matrix files, result
archives) can exhaust the home quota mid-run. `pjsub`'s submit-time
directory check also prefers the data area — the plugin passes
`--no-check-directory` automatically, so running from home *works*.
That is not the same as right.

Read the concrete path live instead of guessing the volume number:
`accountd -E` on the login node lists the account's project groups,
their `/vol0X0X/data/<group>/` paths, and quota usage.

## The standard A64FX layout

4 ranks per node (`processes_per_node: 4`) with 12 OpenMP threads per rank
(`OMP_NUM_THREADS=12` in `environment`), fully using the 48 cores per node.

## f-pt costs Fugaku Points

**`f-pt` is a priority queue that consumes Fugaku Points — it is not
free.** Confirm with the user before using it, and check the selected
project's remaining balance with `get_project_allocations(facility="{{SLUG}}",
project_id="<group>")`. Use it only for deliberate fast-turnaround
validation; revert to `small` for production runs.

Use `small` with a short `elapse` for validation jobs.
