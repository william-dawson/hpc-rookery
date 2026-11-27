Because naur has no working Slurm accounting, a job's final state disappears
from `scontrol` about five minutes after it ends. When recording a workflow,
capture the job status as soon as it reaches a terminal state and also
record the output file contents (`fs_tail`) so the replay does not depend on
scheduler history. Record the `module load` lines used: results built with
the HPC SDK's CUDA 13.3 and the system CUDA 13.2 are not interchangeable.
Note in the notebook that the host is aarch64, so the recorded build steps
do not replay on an x86 machine.
