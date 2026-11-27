Search the bundled Irene guide first. Use `get_facility` for recorded
hardware — it carries the per-subsystem node counts, CPU models, memory per
node and core, the compiler and application inventories, and the TGCC portal
and support pointers.

Prefer a live query whenever the answer depends on current operations:

| question | live source |
|---|---|
| partition occupancy, CpN/GpN ratios | `get_resources` (`ccc_mpinfo`) |
| current QoS limits | `ccc_mqinfo` |
| project associations and fair-share | `get_projects` (`ccc_compuse`) |
| project consumption | `ccc_myproject` |
| installed software versions | `module avail <name>` |
| quotas and purge candidates | `ccc_quota`, `ccc_will_purge` |

Raw commands follow the remote-command skill's preview-and-permission
workflow.

## Facts that come up repeatedly

- Irene is CPU-first. `rome` is the default: 2,286 AMD Rome nodes, 128
  cores and about 228 GiB each.
- The public interface is **Bridge, not raw Slurm**: `#MSUB` directives,
  `ccc_msub` to submit, `ccc_mprun` to launch.
- `-q` (partition), `-A` (project) and `-m` (filesystems) are all mandatory.
- GPUs are allocated through cores per task, not a GPU flag.
- Containers are **pcocc**, not Apptainer or Singularity.
- SCRATCH is purged — 60 days since last access, and empty directories after
  30. Results left there will vanish.
- Do not use `watch` on scheduler commands.

State that this hub port still awaits live TGCC validation whenever the answer
depends on current operations rather than recorded hardware.
