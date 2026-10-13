The local registry routes known job IDs to the scheduler that created them.
Grid Engine checks live `qstat` then durable `qacct -j`; Slurm checks `squeue`
then short-lived `scontrol`. A Slurm job that aged out becomes unknown because
there is no accounting database. A registry miss queries both schedulers and
reports an ID collision as ambiguous.

Grid Engine output defaults under `~/agent/jobs/<name>.o` and `.e`; Slurm
normally uses `slurm-<id>.out` in its work directory. Keep durable Slurm logs
under `/work`. For GE GPU visibility, confirm the generated
`CUDA_VISIBLE_DEVICES` rather than overriding it. Confirm before cancellation,
especially on an unregistered ID because both schedulers may be queried.
