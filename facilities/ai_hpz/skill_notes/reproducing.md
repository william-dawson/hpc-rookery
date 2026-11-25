Because hpz has no Slurm accounting, a job's final state disappears from
`scontrol` shortly after it ends. When recording a workflow, capture the job
status as soon as it reaches a terminal state and also record the output
file contents (`fs_tail`) so the replay does not depend on scheduler history.
Record the GROMACS command line and thread counts used.
