Start by emphasizing that Miyabi is the exception to the laptop-to-cluster
model: Miyabi is normally reached over a multiplexed SSH connection the user
authenticated once with a one-time code (`host` = that ssh alias), or
directly on a login node with `host=localhost`.

Keep the demo read-only unless the user asks for a job. Show static facts,
live occupancy, and a docs search for `PBS select mpiprocs ompthreads`. Any
`hostname` or raw PBS command must follow the remote-command skill: preview
the exact command, ask permission, wait, then recap the result.
