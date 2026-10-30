Use `get_job_status` for a specific job and `get_job_statuses` for several or
for the user's live queue. The backend reads `ccc_mpp -u $USER` for
pending/running jobs and falls back to `ccc_macct <job-id>` for finished ones.
The recent-jobs tool returns only the live queue, because Bridge has no
date-window history query — a finished job must be asked for by ID.

Default output files are `irene_<job-id>.o` and `irene_<job-id>.e` in the
submission directory, unless the spec set explicit stdout/stderr paths.
Inspect those with `fs_tail` or `fs_view` alongside native accounting before
diagnosing a failure.

## Prefer the tools over the raw commands

Each of these has a tool that records the action properly; reach for the raw
command only to see something the tools do not expose.

| Bridge command | use instead |
|---|---|
| `ccc_mpp -u $USER` | `get_job_statuses` |
| `ccc_macct <job-id>` | `get_job_status` on a finished job |
| `ccc_mdel <job-id>` | `cancel_job` |
| `ccc_malter -T <seconds> <job-id>` | `update_job` with a new duration |

`ccc_mstat -u` gives a more detailed live view than `ccc_mpp` and has no tool
equivalent, so it is a reasonable raw query. Only time-limit changes are
verified through `ccc_malter`; confirm with the user before cancelling
anything.

## Polling policy is a site rule, not a preference

TGCC asks for no more than roughly one or two aggregate scheduler queries per
minute and **explicitly prohibits `watch`** on scheduler or Bridge commands.
When waiting on a job, poll by ID at that cadence and say so, rather than
tightening the loop because an answer is slow to arrive.

## Consumption affects scheduling

`ccc_myproject` shows project consumption and `ccc_compuse` fair-share
standing. Both directions have consequences worth telling a user about:
under-consumption can get awarded hours reduced for some project types, while
over-consumption lowers priority and can leave jobs running only as bonus
jobs. If a job is queued far longer than its size suggests, standing is worth
checking before blaming the queue.
