Choose between two genuinely different schedulers. `helix`, `kinase`,
`all.q`, and `gpu` route to Grid Engine; `beta`, `serine`, and `all` route to
Slurm. Omitting the selector defaults to Grid Engine `all.q`. Host selectors
are translated to the real queue plus a host constraint.

Grid Engine is the managed GPU path: request 1-2 GPUs and let the generated
script set `CUDA_VISIBLE_DEVICES` from `$SGE_HGR_gpu`. Do not set it yourself.
Choose a recorded `parallel_env`, and use no more than 32 slots for SMP/OpenMP.

Slurm has no GRES, GPU isolation, accounting, or usable memory tracking. A
one-GPU request only adds container `--nv`; it does not reserve the device.
Coordinate before heavy GPU work. Never add `--gres` or `--mem`. There is no
module system and no account on either side. Preview the selected scheduler's
script and ask permission before submission.
