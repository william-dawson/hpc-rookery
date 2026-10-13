Miyabi's live view is `qstat -f <jobid>`. Its compact history is
`qstat -H --hday 2 --hnum 100` and retains at most three days. A history state
of `FINISH` proves the scheduler lifecycle ended, not that the application
succeeded; inspect the merged output or ask permission to run
`tracejob <jobid>` before reporting success.

`get_resources(facility="{{SLUG}}")` parses the site-specific
`qstat --rscuse` table. `qalter` was inaccessible in the earlier live port,
so `update_job` is intentionally unsupported: cancel and resubmit instead.
