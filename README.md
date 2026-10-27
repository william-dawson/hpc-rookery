# HPC Rookery

HPC Agent Hub is a small shared plugin plus optional facility skill packs for
working with multiple supercomputers. From
your own computer, an AI coding agent can connect to a supported facility,
inspect and transfer files, compile software, submit and monitor batch jobs,
and search a guide written for that machine. It works with MCP-capable agent
harnesses such as Claude Code, Codex, OpenCode, and Cline.

https://github.com/user-attachments/assets/770e1f11-01c7-48f3-8c89-70efc3722e95

The plugin starts two MCP servers: `hpc-mcp` provides facility information,
filesystem operations, and scheduler tools; `hpc-docs-mcp` searches the
bundled machine guides. Every operation names its target explicitly — for
example, `submit_job(facility="rikyu", ...)` or
`search_docs(facility="fugaku", ...)`. The agent calls `get_facilities()`
when it does not already know which machine you mean.

Supported facilities are grouped by their current validation status. An
offline-only port is useful for review and script generation, but should not
be treated as operationally proven until its live checks pass.

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
| `roquo` | ROQUO (RIKEN R-CCS) | slurm | GB200 GPU system with aarch64 compute nodes and x86_64 login/work nodes, Slurm with accounting, --gres=gpu:N and QOS-tiered wall times. |
| `tsubame` | TSUBAME4.0 (Science Tokyo) | gridengine | Science Tokyo's GPU-first H100 system, scheduled by Altair Grid Engine using fixed resource-type slices and TSUBAME group points. |
<!-- FACILITY_TABLE:END -->

## Install

Clone or download this repository, open its directory in your coding agent,
then tell the agent:

> Install the plugins and skill files associated with this repository.

**Agent instruction:** before installing any facility skills, ask the user
which facility slugs they want. For example: “Which facility skill packs
should I include? Choose from `rikyu`, `fugaku`, `hokusai`, `miyabi`,
`rccs-cloud`, `cell2026`, `irene`, `octopus`, and `tsubame`.” Do not install
all facility packs by default, and do not infer access from the facility
catalog. The user may name more than one facility, or choose none yet.

### Codex plugins

Install the base plugin once. It owns the shared `hpc` and `hpc-docs` MCP
servers and the facility-discovery skill:

```sh
codex plugin add hpc@hpc-marketplace
```

Then install one skill-only pack per facility the user selected:

```sh
codex plugin add hpc-rikyu@hpc-marketplace
codex plugin add hpc-fugaku@hpc-marketplace
```

The facility packs do not register MCP servers, so they never duplicate or
conflict with the base plugin. Their names are always `hpc-<slug>`.

### Claude Code and OpenPlugin compatibility

Every package uses the same root `skills/` layout and also includes the
native manifests expected by Codex (`.codex-plugin/plugin.json`) and Claude
Code (`.claude-plugin/plugin.json`). The repository supplies a Claude Code
marketplace at `.claude-plugin/marketplace.json`. Each package additionally
has a portable OpenPlugin `plugin.json`; the base `hpc` package has its
portable `mcp.json`. In every harness, install `hpc` first and only the
facility packs the user selected.

### Manual installation for any MCP-capable harness

If the harness does not support plugins, register `hpc-mcp` and
`hpc-docs-mcp` using its normal stdio-MCP configuration. From an editable
checkout, point them at `.venv/bin/hpc-mcp` and `.venv/bin/hpc-docs-mcp`
(after installing this project into that environment). Then install only the
selected skill directories:

```text
plugins/hpc/skills/                    # shared hpc-facilities skill
plugins/hpc-<selected-slug>/skills/    # one selected facility pack
```

The Python package requires Python 3.10 or newer; the supplied plugin
launcher uses [`uv`](https://docs.astral.sh/uv/).

## Configure

Each cluster has its own settings file at `~/.hpc-agent/<name>.json` — one
file per machine, all in one directory. The minimum is an ssh host:

```json
{
  "ssh": {"host": "rikyu"}
}
```

- `ssh.host` is a `~/.ssh/config` alias, a `user@hostname`, or
  `"localhost"` if the agent is running directly on that cluster's own
  front-end node (no ssh at all). `RIKYU_HOST` overrides the file.
- For a remote host, use an SSH alias with OpenSSH connection multiplexing
  (`ControlMaster auto`, a `ControlPath`, and `ControlPersist 30m`). This
  reuses one authenticated connection for repeated agent calls, reducing
  login-node authentication load and making operations faster. The
  configuring skill can add the exact SSH config block after showing it and
  receiving confirmation; `ControlMaster no` is an explicit opt-out.
- Some machines need more. Fugaku requires a project group on every job,
  HOKUSAI requires a project account. **You don't have to look any of this
  up**: any tool call that can't reach a cluster replies with that
  machine's own setup instructions, including the exact json to write and
  where to get an ssh key registered.
- For documentation search, add `"embedding": {"api_key": "..."}`. Without
  a key — or off the RIKEN network — docs search falls back to keyword
  matching over the same content, so it still works.

You can also just ask the agent to do it: every cluster has a
`<name>-configuring` skill that walks through this and writes the file for
you.

Then check everything is reachable. The simplest way is to ask the agent to
run the doctor. From this checkout, you can install an editable environment
and run it directly:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/hpc-doctor rikyu
```

Replace `rikyu` with the facility you configured. Every line should read
`✓`, except possibly the embedding endpoint — that one falls back to keyword
search and is not blocking. Running the doctor without a facility name checks
all integrations, which is only useful if you can access all of them.

## Make the work reproducible

An agent session is a good way to figure something out, but the result
should not live only in the conversation. When you have a workflow worth
keeping, tell the agent:

> Turn what we just did into a reproducible notebook.

Every cluster has a reproducing skill for this. The agent writes a short,
linear Jupyter notebook that calls the same tools it used during the
session, runs it once for real, and caches the results (including downloaded
files). Later you can run it live again, reuse the cache while editing, or
replay the whole notebook offline without a cluster account. Keep the
notebook and its `.hpc_cache/` directory together if you want to share or
commit the result.

## Adding a cluster you have access to?

This project is an exercise in Specification Driven Development. As we
know, clusters are not standardized. Each one offers a unique combination
of hardware and software. Interactions with the cluster are also not
standardized. For example, two clusters may expose slurm as the job
scheduler, yet the way the queues are set up, the required arguments, the
complementary commands for things like budgeting, are all unique. And some
machines are not slurm at all — Fugaku runs Fujitsu's PJM, with a
different command for every operation.

AI coding provides an alternative approach. Our goal is a comprehensive
**specification** for cluster interactions, such that one can use vibe
coding to automatically generate support for a new cluster. That
specification is [`PORTING.md`](PORTING.md).

To add a machine:

- Download the documentation related to the cluster.
- Start a coding agent in this repository.
- Tell it: “Given the documentation about machine X in folder Y and the
  porting guide `PORTING.md`, add X to this repository.”

The coding agent will make all the design decisions and implement all the
cluster specific code. It adds exactly one `facilities/<name>/` directory:
the machine's facts, a guide written in its own words, the code that
teaches the shared scheduler backend that machine's dialect, and the skill
notes that turn hard-won operational knowledge — which mpi launcher
actually works, which queue silently rejects a job an hour later — into
something the agent knows before it makes the mistake.

Most handwritten machine behavior stays in that facility directory. Shared
generated tables, skills, and conformance tests make the result visible and
check it against the same interface as every existing facility.

### Tool surface: the IRI Facility API

The mcp tool surface mirrors the [IRI Facility
API](https://api.alcf.anl.gov/openapi.json) (the DOE standard this family
targets — not vendored here; fetch it fresh when checking coverage).
[`IRI_CHECKLIST.md`](IRI_CHECKLIST.md) records what is implemented, what
deviates and why, and what is deliberately left out. Because there is one
tool surface shared by every cluster, those verdicts are real and
repo-wide rather than a per-machine template.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e .

.venv/bin/python tests/conformance.py             # offline, every cluster
.venv/bin/python tests/notebook_client.py         # offline, notebook client/cache over MCP
.venv/bin/python tests/live_smoke.py              # read-only, needs ssh
.venv/bin/python tests/live_smoke.py --job rikyu  # + submits a real job
```

Some files are generated from each cluster's `facility.json` and
`skill_notes/`: the validation tables above, one skill file per cluster per
workflow, facility-pack manifests, and the marketplace entries. Regenerate
them after changing those inputs; CI checks that the committed output is
current.

```bash
python scripts/render_facility_tables.py   # after editing facility.json
python scripts/render_skills.py            # after editing skill_notes/
python scripts/render_plugins.py           # after adding a facility
```

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
