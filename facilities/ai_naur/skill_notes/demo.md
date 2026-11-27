**Connectivity check on naur:** `get_projects` is unsupported here (no
working Slurm accounting) and always errors with "does not support". Use
`get_resources(facility="{{SLUG}}")` instead to prove SSH works; only stop if
*that* fails.

Lead with what makes naur different: an Arm (aarch64) host with 72
Neoverse-V2 cores, ~744 GiB of memory and a single NVIDIA GB300 GPU with
~251 GiB that jobs reserve with `gpus=1`; the NVIDIA HPC SDK 26.9 and CUDA
13.2 as modules. Show `get_facility` facts and a docs search such as
"request the GPU" or "why can't I set memory". Mention that `get_resources`
also lists `prado`, `shannon` and `backus` — other machines in the same
Slurm, not part of this facility. Keep the demo read-only unless the user
asks for a job.

If a job is requested, preview a tiny CPU job (e.g. `hostname` with
`cpu_cores_per_process=1`, `duration=300`, no `memory`) and ask before
submitting. Offer a short `nvidia-smi` job with `gpus=1` as the GPU check.
