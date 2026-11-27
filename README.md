# HPC Rookery

HPC Rookery is a small shared plugin plus optional facility skill packs for
working with multiple supercomputers from AI coding agents such as Codex,
Claude Code, Hermes, Pi, OpenCode, VS Code (GitHub Copilot Chat), etc. From
your own computer, an AI coding agent can connect to a supported facility,
inspect and transfer files, compile software, submit and monitor batch jobs,
and search a guide written for that machine.

https://github.com/user-attachments/assets/770e1f11-01c7-48f3-8c89-70efc3722e95

The facilities below have been live-tested. Ports [awaiting live
validation](#awaiting-live-validation) are listed near the end of this README.

<!-- FACILITY_TABLE:START live -->
### Live-tested facilities

These integrations have been exercised against their real scheduler.

| slug | facility | scheduler | description |
|---|---|---|---|
| `crux` | Crux (ALCF) | pbs | Argonne ALCF Crux: 256-node HPE Cray EX AMD Rome CPU system, PBS Professional with sbank accounting, mandatory project and filesystems directives; reached over a multiplexed SSH connection the user authenticates once with a one-time passcode. |
| `fugaku` | Fugaku | pjm | 158,976-node A64FX (Arm SVE) system, Fujitsu PJM scheduler, no GPUs; a project group is mandatory on every job. |
| `hokusai` | HOKUSAI BigWaterfall2 (HBW2) | slurm | CPU-first Slurm cluster (312-node MPC, large-memory, H100 GPU subsystems); a project account is mandatory on every job. |
| `miyabi` | Miyabi (JCAHPC) | pbs | JCAHPC CPU/GH200 system with PBS Professional, full-GPU and MIG queues; reached over a multiplexed SSH connection the user authenticates once with a one-time code. |
| `rccs-cloud` | R-CCS Cloud | slurm | Heterogeneous ~20-partition cluster (CPU/NVIDIA/AMD/Intel GPU), Slurm with accounting. |
| `rikyu` | RIKYU (RIKEN AI4S / GB200) | slurm | RIKEN AI4S GB200 GPU cluster, Slurm with accounting, job-total GPU request. |
<!-- FACILITY_TABLE:END -->

## Install

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
before adding the plugins.

Install the shared `hpc` plugin first, then choose the facility skill packs
for the machines you use. Each pack is named `hpc-<slug>` and adds skills
without starting extra MCP servers. You can add more packs later.

**Using a fork?** A facility does not have to be merged here to be usable.
Many live in forks, and a fork that has repointed its plugins at itself (see
[Working from a fork](PORTING.md#0b-working-from-a-fork-the-common-case))
installs the same way: replace `william-dawson/hpc-rookery` with the fork's
`owner/hpc-rookery` (and `main` with its branch) in the commands below. A
fork that has not repointed would still run this repository's server, which
does not know its facilities.

### Codex

Register this repository as a marketplace once from your terminal:

```sh
codex plugin marketplace add https://github.com/william-dawson/hpc-rookery
```

Then, inside Codex, open the [plugin browser](https://learn.chatgpt.com/docs/plugins#plugin-browser-in-codex-cli):

```text
/plugins
```

Select `hpc-marketplace`, install `hpc`, and choose only the `hpc-<slug>`
packs for your facilities. Start a new session to use their skills and tools.

### Claude Code

Inside a Claude Code session, add the marketplace:

```text
/plugin marketplace add william-dawson/hpc-rookery
```

Then open the [plugin browser](https://code.claude.com/docs/en/discover-plugins):

```text
/plugin
```

In Discover, select `hpc-marketplace`, install `hpc`, and choose only the
`hpc-<slug>` packs for your facilities.

### Pi

Install once:

```sh
pi install git:github.com/william-dawson/hpc-rookery@main
```

Then, inside Pi, open the facility picker:

```text
/hpc
```

Choose the facilities you use to load their skill packs.

### OpenCode

Install once:

```sh
opencode plugin add 'github:william-dawson/hpc-rookery#main'
```

Then, inside OpenCode, use `/hpc` to list available facilities and select
the ones you use by slug. For example:

```text
/hpc rikyu,tsubame
```

### VS Code (GitHub Copilot Chat)

Open the Command Palette (`Cmd+Shift+P` on macOS, `Ctrl+Shift+P`
elsewhere) and run **Chat: Add Plugin Marketplace**. Enter this repository's
URL and press Enter to confirm:

```text
https://github.com/william-dawson/hpc-rookery
```

Then browse the marketplace's plugins (for example from **Chat: Manage Plugin
Marketplaces**), select `hpc-marketplace`, and click **Install** on `hpc`
first, then on the `hpc-<slug>` packs for your facilities. Once installed, a
plugin shows an **Installed** badge and lives under
`~/.copilot/installed-plugins/hpc-marketplace/`.

### Hermes

Hermes installs each plugin straight from this repository by path (it has no
marketplace step for this repo), so install the shared `hpc` plugin and then
one command per facility you use:

```sh
hermes plugins install william-dawson/hpc-rookery/plugins/hpc --enable
hermes plugins install william-dawson/hpc-rookery/plugins/hpc-<slug> --enable
```

For example, for RIKYU and TSUBAME4.0:

```sh
hermes plugins install william-dawson/hpc-rookery/plugins/hpc --enable
hermes plugins install william-dawson/hpc-rookery/plugins/hpc-rikyu --enable
hermes plugins install william-dawson/hpc-rookery/plugins/hpc-tsubame --enable
```

The `hpc` plugin alone gives you the MCP tools and the facility-discovery
skill but none of the per-facility skills, so don't stop after the first
command. Hermes may show a security-scan caution on the facility packs
because the configuring skill has the agent add an alias to `~/.ssh/config`
and create `~/.ssh/controlmasters` (with your approval) when you set up SSH
access. Start a new session afterwards. To add a facility later, run just
its line; to see what is installed, run `hermes plugins list`.

### Manual installation for any MCP-capable harness

You can ask your agent to install it for you. Open this repository in your
agent and say:

> Install HPC Rookery for this harness. Ask me which facilities I use, then
> set up the MCP servers and the skill packs for those facilities.

If the harness does not support plugins, register `hpc-mcp` and
`hpc-docs-mcp` using its normal stdio-MCP configuration. From an editable
checkout, point them at `.venv/bin/hpc-mcp` and `.venv/bin/hpc-docs-mcp`
(after installing this project into that environment). Then install only the
selected skill directories:

```text
plugins/hpc/skills/                    # shared hpc-facilities skill
plugins/hpc-<selected-slug>/skills/    # one selected facility pack
```

The Python package requires Python 3.10 or newer.

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
- For a remote host, use SSH connection multiplexing to reuse one
  authenticated connection across agent calls, as shown below.
- Some machines need more. Fugaku requires a project group on every job,
  HOKUSAI requires a project account. **You don't have to look any of this
  up**: any tool call that can't reach a cluster replies with that
  machine's own setup instructions, including the exact json to write and
  where to get an ssh key registered.
- For documentation search, add `"embedding": {"api_key": "..."}`. Without
  a key — or off the RIKEN network — docs search falls back to keyword
  matching over the same content, so it still works.

For example, add an alias to `~/.ssh/config`, replacing the hostname and
username with your cluster login details:

```sshconfig
Host rikyu
    HostName login.example.edu
    User your-username
    ControlMaster auto
    ControlPath ~/.ssh/%C
    ControlPersist 30m
```

With `"ssh": {"host": "rikyu"}`, agent calls reuse this connection. Set
`ControlMaster no` to disable multiplexing.

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

To save a workflow, ask the agent:

> Turn what we just did into a reproducible notebook.

The agent writes a Jupyter notebook, runs it, and caches the results and
downloaded files. Keep the notebook and its `.hpc_cache/` directory together
to share or replay the workflow without cluster access.

For example, a one-GPU check on RIKYU looks like this. The agent fills in
the commit, working directory, and project from your session:

```python
from pathlib import Path
from hpc_agent_core.client import connect_sync, pinned_params

hpc = connect_sync(
    pinned_params(
        "https://github.com/william-dawson/hpc-rookery.git",
        "hpc-mcp",
        ref="<commit-used-in-the-session>",
    ),
    mode="live",
    cache_dir="./.hpc_cache/gpu-check",
)
```

```python
workdir = "/home/<user>/agent/work/gpu-check"
hpc.fs_mkdir(facility="rikyu", path=workdir)
job = hpc.submit_job(facility="rikyu", spec={
    "name": "gpu-check",
    "directory": workdir,
    "executable": "nvidia-smi -L > gpus.txt",
    "resources": {"gpus": 1},
    "attributes": {"duration": "00:01:00", "account": "<project>"},
})
status = hpc.wait_for_job(job["job_id"], facility="rikyu")
assert status["status"]["state"] == "completed", status
hpc.fs_download(
    facility="rikyu",
    remote_path=f"{workdir}/gpus.txt",
    local_path="./gpus.txt",
)
hpc.close()
print(Path("gpus.txt").read_text())
```

Use `live` for a fresh run, `lazy` to reuse cached calls while editing, or
`replay` to read only recorded results without submitting jobs. Replay
requires the cache, Python dependencies, and pinned server locally.

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
cluster specific code. It adds exactly one `facilities/<name>/` directory
(in a fork, plus one separate commit that repoints the plugins at the
fork):
the machine's facts, a guide written in its own words, the code that
teaches the shared scheduler backend that machine's dialect, and the skill
notes that turn hard-won operational knowledge — which mpi launcher
actually works, which queue silently rejects a job an hour later — into
something the agent knows before it makes the mistake.

Most handwritten machine behavior stays in that facility directory. Shared
generated tables, skills, and conformance tests make the result visible and
check it against the same interface as every existing facility.

### Fork first, upstream if you like

Most ports start in a fork, because you usually need the machine working now
rather than after review, and some facilities (a single lab's workstation, a
site with its own rules) are better kept in the fork for good. Both are
fine. [`PORTING.md`](PORTING.md#0b-working-from-a-fork-the-common-case) has
the one extra step a fork needs — repointing the plugins so they run the
fork's server — and explains how to keep that step in its own commit, so the
facility commit can still be cherry-picked into a pull request here.

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
.venv/bin/python tests/live_smoke.py --job roquo --free  # + a real job on a free tier
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

<!-- FACILITY_TABLE:START awaiting -->
## Awaiting live validation

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

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
