`get_job_status` reads the full `qstat -fx` record — including finished
jobs, since ALCF keeps about two weeks of history, and the exit status of a
finished job. The **`message` field comes from PBS's comment attribute**,
which is where every "why isn't it running" answer lives (insufficient
nodes, filesystem down, held for too many failed attempts, deletion
notices). Read it before diagnosing anything else.

Job output files: `<name>.o<seq>` and `<name>.e<seq>` in the directory the
job was submitted from — take `meta_data.workdir` from the status record
(usually `~/agent/jobs`) rather than assuming the home root, and read them
with `fs_tail` while running or `fs_view` once finished. `meta_data.output_path`
and `meta_data.error_path` name the exact files; `workdir` keeps working for
finished jobs too, since it falls back to the output directory when PBS
history no longer carries the submission environment.

Recent jobs (`get_job_statuses` with an empty id list) come from
`qselect`/`qstat` with full untruncated ids; the two-week window is the
ceiling. A few states worth decoding:

- A `preemptable` job reported `failed` with a comment about deletion at
  the scheduler's request was **preempted**, not crashed — and because the
  backend renders `-r y`, it requeues and will run again once the demand job
  finishes. Say that, don't declare data loss.
- A job you cancelled via `cancel_job` reports `canceled` immediately; if
  polled again before PBS finishes the deletion it may briefly show as
  `failed` with a nonzero exit status — the deletion, not the application.
- An id that returns `unknown` with a note about the routing queue means
  the job fit no execution queue and was dropped after `qsub` returned:
  check node count and walltime against `get_facility`'s queue limits
  before resubmitting.

`get_resources` returns one row per queue (job counts, from `qstat -Q`) each
carrying the machine-wide node pool (`allocated`/`idle`/`other`/`total` from
`pbsnodes`) — Crux queues share one node pool, so idle nodes mean any queue
can start. `get_drained_nodes` maps `pbsnodes -l` for down nodes.

`update_job` maps onto `qalter` (name, walltime, project, node count — and
walltime can even be lowered on a *running* job) and `qmove` (queue or
reservation changes, queued jobs only). Anything else in the spec is
reported back as not applied.
