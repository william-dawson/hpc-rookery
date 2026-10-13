Octopus has Slurm accounting: `get_job_status` and recent history use `sacct`,
while queued jobs gain a live `squeue` wait reason. `get_resources` reports
partition occupancy, and `get_drained_nodes` reports unavailable nodes.

For failures, first compare partition and toolchain: CUDA belongs on `h200*`
and ROCm on `mi300x*`. `TIMEOUT` on a non-long partition points to its
matching `-long` queue; GPU-less containers should show `--nv` for H200 or
`--rocm` for MI300X in the retained script. Raw `nvidia-smi`, `rocm-smi`, or
job-step commands require the remote-command preview and permission workflow.
