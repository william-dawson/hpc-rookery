Use `get_job_status` for named jobs: live records come from `qstat`, then
completed jobs fall back to `qacct`. `get_recent_jobs` only shows jobs still in
Grid Engine because completed jobs leave `qstat`; explain that limitation.

Default output is normally `<name>.o<job-id>` and `<name>.e<job-id>` in the
submission directory. For queued failures check group points, the resource type,
and the live queue. For runtime failures check `qacct`, output, wall time,
modules, `OMP_NUM_THREADS`, and GPU compatibility. The hub parser still awaits
fresh live TSUBAME validation, so show native evidence when a result is unclear.
