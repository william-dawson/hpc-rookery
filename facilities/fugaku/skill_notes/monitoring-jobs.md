## PJM state codes

`ACC`/`QUE` → queued · `HLD`/`SPD`/`SPP` → held ·
`RNP`/`RUN`/`RNA`/`RNE`/`RNO`/`RSM` → active · `EXT` → completed ·
`CCL` → canceled · `ERR`/`RJT` → failed. The raw code is in
`meta_data.native_state`.

## "completed" does not mean "succeeded"

**`EXT` only means the scheduler finished with the job** — PJM's live
status table has no exit-code column at all, so a failed program still
shows as `completed`. **Always read the job's output before telling the
user it worked.**

## Finding the output — two places, and the obvious one is often empty

PJM writes `<name>.<job_id>.out`/`.err` into the *submission* directory
(`~/agent/jobs/` by default). But **Fujitsu MPI intercepts per-rank stdout
and writes it somewhere else entirely**:
`output.<jobid>/<rank_path>/stdout.<step>.<rank>` inside the job's working
directory. The PJM `.out` file is then often empty or holds only the
scheduler wrapper.

So for an MPI job, find the real output with:

```sh
find . -path "*output.<jobid>*" -name "stdout*" | sort
```

(`$PJM_JOBID` holds the current job ID inside a running job.) Run that via
`run_command_on_cluster(facility="{{SLUG}}", ...)`, then read what it finds
with `fs_view`/`fs_tail`.

## `ERR` before the job ever starts

A job that goes to `ERR` with **no output file and no start date** was
rejected by the pre-execution gate check, not by your program. Get the
reason with:

```
pjstat -s <job_id>
```

and read its `REASON` line. The known cause of `GATE CHECK` here is a
comma-separated `PJM_LLIO_GFSCACHE` value — see
`{{SLUG}}-submitting-jobs`; `submit_job` now rejects that before
submitting. Note `RESOURCE GROUP` may show a sub-group like `small-s5`
rather than the `small` you asked for; that is normal and **not** a
problem — healthy jobs run in it too. `pjstat --history` returns nothing
on this deployment, so `pjstat -s` is the only tool that answers this.

## Quotas and limits

- `run_command_on_cluster(facility="{{SLUG}}", command="pjstat --limit")` —
  concurrent-job and node/core quotas.
- `run_command_on_cluster(facility="{{SLUG}}", command="pjacl --rg <name>")` —
  a resource group's node/elapse limits **for this account**, which is what
  actually governs whether a submission is accepted.

## get_resources is best-effort text here

It returns raw `pjstat --rsc`/`pjshowrsc` output. Those commands did not
return usable per-partition occupancy during this port's live testing, so
treat it as text, not structured data — the resource-group node/time limits
in `get_facility` are the more reliable static reference.

## Changing a queued job

`update_job` can only change the elapse limit (via `pjalter`), and only
while the job is still queued or held. Everything else — resource group,
node count, project group — means cancel and resubmit.
