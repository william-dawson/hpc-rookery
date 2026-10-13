Default ordinary CPU/MPI work to `rome`. Use `xlarge` for large single-node
memory and the `v100` family only for GPU-capable software.

Every Irene job needs a partition (`queue_name`), a TGCC project (`account`),
and filesystems (`custom_attributes.filesystems`, normally `scratch,work`). If
the project was not already chosen in config or by the user, call
`get_projects` and ask which association to charge. The backend rechecks that
project/partition pair through `ccc_compuse` at submission time.

Use `process_count` for total Bridge tasks, `cpu_cores_per_process` for cores
per task, and `ccc_mprun` as the launcher. GPU allocation is derived from the
live CpN/GpN core ratio, so inspect `get_resources` when the shape is not
obvious. Containers use a pcocc image name and render as `ccc_mprun -C`.
Preview the `#MSUB` script and ask permission before submitting.
