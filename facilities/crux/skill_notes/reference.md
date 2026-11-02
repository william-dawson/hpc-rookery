The bundled guide was written from ALCF's public documentation and the port
is live-validated (2026-11-02), but recorded queue limits, module contents,
and quota numbers can drift as ALCF adjusts the machine: refresh them live
rather than quoting the guide as current.

Live refresh commands (each needs the remote-command permission workflow):
`qstat -Q` / `qstat -Qf <queue>` for queue limits and state, `qstat -was1
<jobid>` for a job's comment on one line, `pbsnodes -avSj` for node health,
`module avail` for software, `myquota` / `myprojectquotas` for storage,
`sbank-list-allocations -r crux` for balances.

Machine status (maintenance, outages): status.alcf.anl.gov. Accounts,
projects, and the graphical sbank views: my.alcf.anl.gov. People problems:
support@alcf.anl.gov. Search results here cite ALCF's user guides
(docs.alcf.anl.gov/crux/) — a stable public site, unlike most facilities
here — so passing that URL along is fine.
