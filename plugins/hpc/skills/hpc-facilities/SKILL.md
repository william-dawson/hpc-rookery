---
name: hpc-facilities
description: Use to discover which HPC facilities are available through this plugin and pick the right one before calling any other tool or skill — e.g. when the user hasn't named a specific machine, or you're unsure which facility slug applies.
---

# Which facility?

This plugin serves every onboarded facility through one MCP server. Every
tool takes an explicit `facility` argument (a slug like `"rikyu"`) as its
first parameter — there is no default facility. Once you know the facility,
its own skill (`<slug>-submitting-jobs`, `<slug>-monitoring-jobs`,
`<slug>-configuring`, `<slug>-remote-command`, `<slug>-demo`,
`<slug>-reproducing`) has the real,
facility-specific how-to; this skill only covers picking the slug.

## Resolve the facility first

If the user's request doesn't already make the facility obvious (they named
it, or it's the only one they've ever mentioned in this conversation), call
`get_facilities()` before calling anything else. It returns every
registered slug with a display name and a one-line description — pick the
one that matches what the user asked for, or ask them to confirm if more
than one plausibly fits. Never guess a slug that wasn't returned by this
call: every other tool raises a clear error listing the valid slugs if you
pass a wrong one, but it's cheaper and clearer to check first.

## Facilities currently onboarded

<!-- FACILITY_TABLE:START -->
### Live-tested facilities

These integrations have been exercised against their real scheduler.

| slug | facility | scheduler | description |
|---|---|---|---|
| `fugaku` | Fugaku | pjm | 158,976-node A64FX (Arm SVE) system, Fujitsu PJM scheduler, no GPUs; a project group is mandatory on every job. |
| `hokusai` | HOKUSAI BigWaterfall2 (HBW2) | slurm | CPU-first Slurm cluster (312-node MPC, large-memory, H100 GPU subsystems); a project account is mandatory on every job. |
| `miyabi` | Miyabi (JCAHPC) | pbs | JCAHPC CPU/GH200 system with PBS Professional, full-GPU and MIG queues; reached over a multiplexed SSH connection the user authenticates once with a one-time code. |
| `rccs-cloud` | R-CCS Cloud | slurm | Heterogeneous ~20-partition cluster (CPU/NVIDIA/AMD/Intel GPU), Slurm with accounting. |
| `rikyu` | RIKYU (RIKEN AI4S / GB200) | slurm | RIKEN AI4S GB200 GPU cluster, Slurm with accounting, job-total GPU request. |

### Awaiting live validation

These ports register and pass the offline test suite, but have not yet
completed an end-to-end check against the current live system.

| slug | facility | scheduler | description |
|---|---|---|---|
| `cell2026` | cell2026 (Shinobu Lab) | gridengine + slurm | Dual-scheduler GPU cluster: Grid Engine on helix/kinase with managed RTX A4000s and durable qacct, plus no-accounting Slurm on beta/serine with unmanaged RTX 4000 Ada/RTX 5090 GPUs. |
| `irene` | Irene (CEA TGCC) | bridge | CEA TGCC CPU-first system with AMD Rome, large-memory, and NVIDIA GPU partitions, accessed through the Bridge #MSUB/ccc_* scheduler interface. |
| `octopus` | Octopus (RIKEN R-CCS) | slurm | Four-node, dual-vendor GPU cluster: three NVIDIA H200 nodes and one AMD MI300X node, Slurm accounting, and vendor-specific container passthrough. |
| `tsubame` | TSUBAME4.0 (Science Tokyo) | gridengine | Science Tokyo's GPU-first H100 system, scheduled by Altair Grid Engine using fixed resource-type slices and TSUBAME group points. |
<!-- FACILITY_TABLE:END -->

Once you've resolved the slug, check whether its facility skill pack is
installed. The base `hpc` plugin deliberately ships only this discovery
skill and the shared MCP servers; it does not preload guidance for every
machine.

For Codex, install the selected pack from the same marketplace:

```sh
codex plugin add hpc-<slug>@hpc-marketplace
```

For a harness without plugins, install only the skill directories under
`plugins/hpc-<slug>/skills/`. Before installing any facility pack on the
user's behalf, ask them which facility slugs they want included; do not
assume that every facility listed here is relevant or accessible.

The selected pack has the real facility-specific configuring, reference,
submission, monitoring, remote-command, demo, and reproducibility skills.
If the user wants to configure access before installing it, call an
appropriate facility-scoped MCP tool: an unconfigured facility returns its
exact setup instructions.
