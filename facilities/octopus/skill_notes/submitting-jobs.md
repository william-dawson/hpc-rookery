Octopus is GPU-only and dual-vendor. Choose the software target first:

- NVIDIA CUDA/NVHPC -> `h200` (up to 8h) or `h200-long`.
- AMD ROCm -> `mi300x` (up to 8h) or `mi300x-long`.

Every current partition is recorded as allowing single-node jobs with 1-8
GPUs, 192 CPU cores, and 2,317,610 MiB usable memory. With that enforced
one-node shape, `resources.gpus` renders as `--gres=gpu:N`. A partial spec
defaults to one H200 GPU. Containers receive `--nv` or `--rocm`
automatically from the partition.

Normally omit `attributes.account`; Slurm applies the user's
`DefaultAccount`. If the user needs a different project, call
`get_projects(facility="{{SLUG}}")` and use one of the returned associations.
Never copy an account name from an example.

The source port was checked offline but not against live Octopus. Run a tiny
H200 and MI300X job when access returns before treating the integration as
live-validated.
