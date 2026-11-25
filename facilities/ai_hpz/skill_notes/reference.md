Ground hpz answers in the bundled guide and `get_facility`: one node, 24
Slurm CPUs (Xeon Gold 6136, 12 cores × 2 threads), ~187 GiB, one Quadro RTX
5000 (16 GiB, sm_75) requested as `--gres=gpu:1`, one `debug` partition without
time limit, Slurm accounting off, GROMACS 2026.3 (thread-MPI, CUDA) in
`/usr/local/gromacs`, NVIDIA HPC SDK 24.5 / CUDA 12.4 via
`module use /opt/nvidia/hpc_sdk/modulefiles`.

These facts were read live on 2026-11-25. Software versions can change; when
a version matters, offer to confirm it live (remote-command workflow).
