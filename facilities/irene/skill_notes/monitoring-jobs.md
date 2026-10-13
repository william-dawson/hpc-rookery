Use `get_job_status` for a specific job. Live jobs come from
`ccc_mpp -u $USER`; completed jobs fall back to `ccc_macct <job-id>`. The
recent-jobs tool is only the live queue because Bridge has no date-window
history query.

Default output files are `irene_<job-id>.o` and `irene_<job-id>.e` in the
submission directory. Inspect those along with native accounting before
diagnosing a failure. Respect TGCC's policy: do not use `watch`, and keep
aggregate scheduler polling to roughly one or two queries per minute. Confirm
before cancellation; only time-limit updates are verified through `ccc_malter`.
