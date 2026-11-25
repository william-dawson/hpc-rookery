hpz is a single workstation with one Slurm partition, `debug` (the default,
no time limit). A partial spec gets `queue_name="debug"` filled in; any other
partition is rejected. Keep `node_count=1` and never set `attributes.account`
— Slurm here has no accounting.

**Resources are shared per job.** Slurm allocates cores and memory per job,
24 CPUs (12 cores × 2 threads) and 192,117 MiB in total. Request what the job
actually uses (`cpu_cores_per_process`, `memory`) so other users' jobs can run
alongside.

**The GPU is a Slurm GRES.** There is one Quadro RTX 5000 (16 GiB, sm_75).
Set `resources.gpus=1` for any job that uses it; it renders as
`--gres=gpu:1`, reserves the GPU (a second GPU job pends with `Resources`)
and sets `CUDA_VISIBLE_DEVICES=0`. `gpus` above 1 is rejected. Slurm does
not hide the GPU from jobs that did not request it, so never run GPU code
with `gpus` unset — it would collide with the job that holds the
reservation.

**No containers.** There is no Singularity/Apptainer, so `spec.container` is
rejected. Use the host software.

### GROMACS (the main workload)

GROMACS 2026.3, mixed precision, CUDA (sm_75), AVX-512, **thread-MPI only**
— there is no `gmx_mpi`. Never wrap it in `mpirun` or `srun -n N`; run one
process and size threads with `-ntmpi`/`-ntomp`.

Recommended single-GPU shape: `gpus=1`, `processes_per_node=1`,
`cpu_cores_per_process=8` (up to 24), and

```
pre_launch: source /usr/local/gromacs/bin/GMXRC
executable: gmx
arguments:  ["mdrun", "-deffnm", "md", "-ntmpi", "1",
             "-ntomp", "8", "-nb", "gpu", "-pme", "gpu",
             "-bonded", "gpu", "-update", "gpu"]
```

Keep `-ntomp` equal to `cpu_cores_per_process`. Add `-pin on` only if the
job asked for all 24 CPUs; otherwise concurrent jobs pin onto the same cores.
`gmx grompp` preprocessing is quick and can run in the same job before
`mdrun` (use `pre_launch`), or as its own short CPU-only job.

### Compilers and CUDA

The NVIDIA HPC SDK 24.5 (with CUDA 12.4) is not on the default module path:

```
pre_launch: module use /opt/nvidia/hpc_sdk/modulefiles && module load nvhpc/24.5
```

Other variants: `nvhpc-nompi`, `nvhpc-hpcx`, `nvhpc-hpcx-cuda12`,
`nvhpc-openmpi3`, `nvhpc-byo-compiler` (all 24.5). There is no
`/usr/local/cuda`. System Open MPI 4.1.6 is at `/usr/bin/mpirun`.

Stage inputs and run directories under `~/agent/work/<run>/` and set
`spec.directory` to it. The disk (~1.8 TB) is shared with the OS; remind the
user to delete large trajectories they no longer need.

**Paths:** a relative `stdout_path`/`stderr_path` is resolved by Slurm from
`spec.directory`, not from home. With `directory="agent/work/run1"`, write
`stdout_path="run1.out"` (lands in that directory), not
`"agent/work/run1/run1.out"` (would land in `agent/work/run1/agent/work/...`).
Without `stdout_path`, output goes to `slurm-<jobid>.out` in the directory.
