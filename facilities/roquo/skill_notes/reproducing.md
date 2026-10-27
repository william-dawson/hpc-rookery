**The account must be in the notebook.** A reproducible ROQUO notebook has
to pass `attributes.account` explicitly. Leaving it out doesn't fail — the
job runs against a restrictive default account and its output lands owned
by the wrong group — so a notebook that omits it reproduces *something*,
just not the run the user meant. Treat the project as a parameter of the
notebook, set once near the top, not a detail buried in one cell.

**Pin the partition too.** `roquo` and `work` are different architectures,
so a notebook that relies on the default partition silently becomes
non-reproducible the day someone changes it. Name it.

**Don't reproduce through `$SLURM_SCRATCH`.** Node-local scratch is
deleted when the job ends, so any step that writes results there and reads
them in a later cell will work once interactively and then fail. Stage
through `/projects/hps1/<project>` for anything a later cell reads.

**Module loads belong in the job, not the session.** Modules only load on
compute nodes, so a notebook cell that runs `module load` over
`run_command_on_cluster` (which executes on a login node) will not set up
what the job sees. Put module loads in `pre_launch` or the executable
itself.
