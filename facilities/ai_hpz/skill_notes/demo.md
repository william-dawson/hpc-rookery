**Connectivity check on hpz:** `get_projects` is unsupported here (no Slurm
accounting) and always errors with "does not support". Use
`get_resources(facility="{{SLUG}}")` instead to prove SSH works; only stop if
*that* fails.

Lead with what makes hpz different: a single workstation, one `debug`
partition, a single GPU (Quadro RTX 5000) that jobs reserve with `gpus=1`, and GROMACS
2026 with CUDA as the main workload. Show `get_facility` facts and a docs
search such as "GROMACS GPU mdrun threads". Keep the demo read-only unless
the user asks for a job.

If a job is requested, preview a tiny CPU job (e.g. `hostname` with
`cpu_cores_per_process=1`, `duration=300`) and ask before submitting. Offer a
short `gmx --version` job with `gpus=1` as the GROMACS/GPU check.
