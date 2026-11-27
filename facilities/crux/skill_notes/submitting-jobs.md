Crux runs PBS Professional and allocates **whole nodes** — each one with
128 physical cores (256 hardware threads) and 256 GB, no GPUs anywhere.

Three things are mandatory on every job and the backend fills or checks them
all: the project (`#PBS -A`, from the user's configured default or
`spec.attributes.account`), the walltime, and the `-l filesystems` directive
(default `home:eagle`; set `custom_attributes.filesystems` to `"home"` or
`"eagle"` alone when the job touches only one — a job waits while any
filesystem it names is down). The select line is rendered for you as
`select=<node_count>:system=crux` with `place=scatter`; don't try to request
partial nodes, memory slices, or GPUs — there is nothing smaller than a
node here, and GPU fields are rejected with an error.

Queue choice (from the bundled guide's table):

- `debug` — 1–4 nodes, up to 2 h; the right place for short tests, but only
  one running job per user.
- `workq-route` — the production default (1–176 nodes, up to 24 h) when you
  leave `queue_name` blank.
- `preemptable` — up to 72 h and 10 nodes, but any job here can be killed
  without warning whenever demand work needs the nodes. The backend renders
  `#PBS -r y` automatically so a killed job reruns — still, never put work
  here that can't survive a restart from scratch.
- `demand` — only after ALCF grants the user access (email support).
- Reservations are **queues**: pass the reservation's queue name (check with
  `pbs_rstat` first, via the remote-command skill) as
  `attributes.reservation_id`, not `queue_name`.

Two Crux-specific traps the offline validation exists for: a job whose node
count or walltime doesn't fit its queue is *accepted by the routing queue
and then silently dropped* — you get a job id that never shows up in qstat.
And `OMP_NUM_THREADS` starts at 256 on compute nodes, so any threaded code
must set it explicitly (e.g. in `spec.environment`).

Parallelism is decided by the launcher, not the scheduler: with N nodes,
rank placement comes from your `mpiexec` line (`-n` total ranks, `--ppn`
per node, `--depth` + `--cpu-bind` for pinning, `--env` for variables) —
put it in `launcher` or write it into `executable`. PBS doesn't read the
spec's process fields, so say what you want mpiexec to do, not what you want
PBS to do.

Working directory and output: the backend submits from `~/agent/jobs`, so a
job with no `spec.directory` runs there and its stdout/stderr land beside
its script as `<name>.o<seq>` / `<name>.e<seq>` (the site forces streamed
output). For real work, stage inputs/outputs under
`/eagle/projects/<project>/...` — heavy I/O doesn't belong in the 50 GB
home area — or under `~/agent/work/<name>/` for small things. Containers
aren't supported on Crux yet (Apptainer is planned, not present); build
natively with the `PrgEnv-*` modules and `cc`/`CC`/`ftn` wrappers, or a
`python3 -m venv`. Outbound internet needs the site proxy
(`http://proxy.alcf.anl.gov:3128`) exported in the job.
