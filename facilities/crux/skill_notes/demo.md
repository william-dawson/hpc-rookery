Start by explaining the connection model: Crux is normally reached over a
multiplexed SSH master the user authenticated once with their one-time
passcode (`host` = that ssh alias), or directly on an access node with
`host=localhost`. If the master has expired, the demo's SSH-dependent steps
will fail with permission denied — have the user re-run `ssh -MNf crux`
rather than asking for the passcode.

`get_projects` is the natural "prove the connection works" call here: it
runs sbank on the login node and returns the user's chargeable ALCF projects
with their remaining node-hour balances — worth showing as a table.

For the Step 6 test job, a one-node `debug` job is right (the queue exists
for exactly this): 1 node, 10 minutes, the user's configured account,
`executable="echo"` with a marker argument. Note that `workq-route` would
also work but may queue behind production work; `debug` has at most one
running job per user, so a previous demo job must be finished first.

The port is live-validated (2026-11-02: doctor, read-only smoke, and real
one-node debug jobs end to end) — but if any step behaves in a way the
skill notes didn't predict, report the mismatch rather than improvising an
explanation.
