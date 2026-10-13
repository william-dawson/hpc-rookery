# AGENTS.md

Read [`PORTING.md`](PORTING.md) before making changes here — it's the
canonical guide for onboarding a new facility. This file covers design
rules and repo facts that apply across the whole repo, not the porting
procedure itself.

## What this repo is

One shared MCP-owning plugin (`plugins/hpc/`) plus one skill-only plugin per
facility (`plugins/hpc-<slug>/`), one MCP server process, every onboarded
facility reachable through one generic, facility-parametrized tool surface.

**This is `william-dawson/hpc-rookery`.** It began as the `unified-hub`
branch of `william-dawson/hpc-agent-core` and was split out into its own
repository; that branch remains there as the archive of this project's
development history, which this repo does not carry.

A rookery is a colony of nests, which is the architecture: many facilities,
one place. It is the unified form of what `hpc-agent-core` does per
machine. That project publishes a PyPI library which one-repo-per-machine
plugins (`Rikyu-Agent`, `Hokusai-Agent`, `RCCS-CloudAgent`, `Fugaku-Agent`,
...) each depend on; this repo absorbs the engine and every machine into a
single repo and a single server. Those per-machine repos are independent of
this one and continue to work.

Two consequences worth knowing before you change anything here:

- The `hpc_agent_core` package vendored here is **not** API-compatible with
  the `hpc-agent-core` published on PyPI — every entry point takes a
  `facility` argument. Don't port a change between them by copying;
  re-derive it.
- Because this repo ships a package *directory* named `hpc_agent_core`,
  installing it shadows the PyPI `hpc-agent-core` when both land in one
  environment. The repo name no longer hints at that, so it is easy to trip
  over. The plugin's `.mcp.json` uses `uv tool run --from git+...@main`,
  which is isolated, so this only bites if you hand-install both into the
  same venv.

## Design rules

- **Every tool takes an explicit `facility` slug as its first argument.**
  There is no default facility, no "current" facility, no global state
  naming one. An agent must always know or discover (`get_facilities()`)
  which facility it's calling.
- **A facility PR touches exactly one directory: `facilities/<slug>/`.**
  See PORTING.md §11 for the full list of what a facility PR does *not*
  need to touch. If a change seems to require editing `hpc_agent_core/` or
  `hpc_mcp/`, that's a signal to reconsider the approach, not a green light
  to edit them — those files serve every facility at once.
- **Clarity over cleverness.** A little facility-specific code in one
  `facility.py` is fine — don't force every dialect difference through a
  maximally generic mechanism if a straightforward subclass override reads
  better (see `facilities/rccs_cloud/facility.py`'s `CloudSlurmBackend` for
  the pattern).
- **Agent scratch goes under `~/agent/`, never the home-directory root.**
  `~/agent/jobs/` already holds rendered job scripts (visible-directory
  bias: agent artifacts live somewhere the user can audit). Uploads, source
  trees, and run directories extend the same idea — they belong under
  `~/agent/work/`. The skill templates tell agents this; tool behavior stays
  path-explicit and doesn't silently reroot.
- **The MCP server must never fail to start.** Per-facility config is read
  lazily, at tool-call time, never at import time.
- **Never write to stdout in server code** — MCP stdio transport uses it
  for JSON-RPC; log to stderr only. `remotemanager`'s progress output is
  redirected by `middleware.py`.

## This repo must never publish `hpc_agent_core` to PyPI

`william-dawson/hpc-agent-core` publishes the real `hpc-agent-core` library
on a released tag. **This repo must not.** The `hpc_agent_core` package
here is a divergent fork of that engine, and publishing it would either
create a confusing second package or — far worse — ship an
API-incompatible `hpc_agent_core` to everyone depending on the real one.

Splitting out of that repository removed two of the barriers that used to
make this impossible, so the remaining ones matter more, not less:

- there is **no publish workflow here**. Don't add one. (`hpc-agent-core`
  has its own, triggered by `release: published`; it lives in that
  repository and nothing here can fire it.)
- `.github/workflows/ci.yml` grants only `contents: write`. PyPI trusted
  publishing requires `id-token: write`, so no step in this workflow can
  authenticate to PyPI even if one were added.
- the distribution is named `hpc-rookery`, so it could not overwrite
  `hpc-agent-core` on the index in any case.

If this project is ever published deliberately, it goes out as
`hpc-rookery` and never as `hpc-agent-core`.

## Repo map

```
hpc_agent_core/        The generic engine (SSH middleware, models, scheduler
                        backends, docs RAG, doctor, serving, the facility
                        registry in config.py).
facilities/             One directory per onboarded facility, plus
                        registry.py (facility slug -> SchedulerBackend).
                        Each facility's skill_notes/ holds its real,
                        hand-written skill content (see PORTING.md §7).
hpc_mcp/                The unified server entry points; importing this
                        package registers every facility.
plugins/hpc/            The base Codex plugin: .mcp.json and only the
                        shared hpc-facilities discovery skill.
plugins/hpc-<slug>/     Generated skill-only Codex plugin for one facility.
templates/skills/       Shared per-workflow skill templates (the mechanics
                        every facility has identically) — not per-facility.
scripts/                render_facility_tables.py (facility table codegen),
                        render_skills.py (per-facility skill codegen), and
                        render_plugins.py (marketplace/manifest codegen).
tests/live_smoke.py     Live, facility-agnostic smoke test.
```

## Facilities onboarded so far

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

## Outstanding code-review work

Review carried over from the `unified-hub` branch this repo was split
from (2026-09-01); the commit range it covered is not in this history. Each item says whether it was
reproduced or is still a reading of the code — don't downgrade an
unverified one without checking it, and don't re-verify one marked
**verified** from scratch.

Two of these are only visible with an *empty* `~/.hpc-agent/`. A developer
machine has config for its own clusters, so both the CI failure and the
unconfigured-tool behaviour pass locally and fail in CI. Reproduce with:

```bash
HOME=$(mktemp -d) .venv/bin/python tests/notebook_client.py
```

### P1

- **The `fs_rm` refusal test can delete the test runner's own files.**
  `tests/conformance.py:1032` sets `CELL2026_HOST=localhost` and calls the
  real `fs_rm` over `["", " ", ".", "..", "/", "~", "~/", "*", "$HOME",
  ".//"]`. `middleware.is_local_host("localhost")` is true, so this runs in
  a bare local shell on the machine running the tests — no SSH, no cluster.
  The `_RM_REFUSED` guard stops all ten today, but this test exists to catch
  a regression *in that guard*, and the moment it regresses the test runs
  `rm -r -- ~` against a real home directory instead of failing. The test's
  only safety net is the code under test. Point it at an unreachable
  non-local host, or patch `hpc_mcp.hpc_server.run_command`.
  **Verified:** a canary file passed to `fs_rm("cell2026", ...)` under
  `CELL2026_HOST=localhost` was really deleted from the local filesystem.

- **The configuration gate also blocks the tools that need no cluster.**
  A late `unified-hub` change wrapped every facility-scoped tool in
  `require_facility_configuration`. That is right for anything that opens
  SSH, but `get_facility` reads a packaged JSON file and the three docs
  tools read a packaged index; neither can "present an unconfigured
  facility as ready". Consequences: `tests/notebook_client.py` fails in CI
  (red for three runs); the `<slug>-reference` skill becomes circular,
  since its whole job is `search_docs` + `get_facility` and both now demand
  config a new user does not have; and the conformance check
  `no-config tools still answer (never-fail invariant)` — added by
  earlier to guarantee an agent can orient a user *before* setup — was
  deleted rather than satisfied. Keep the gate on cluster-bound tools, drop
  it from `get_facility` and the docs tools, and restore the invariant check.
  **Verified:** against the real MCP server with an empty HOME,
  `get_facilities` works while `get_facility` and `search_docs` both return
  "is not configured yet".

### P2

- **Miyabi loses `PBS_O_WORKDIR` to line wrapping.** `_parse_blocks`
  (`facilities/miyabi/compute.py`) keeps only lines containing `" = "`, so
  PBS's tab-indented continuation lines are silently dropped. `qstat -f`
  wraps attribute values at ~80 columns, and `PBS_O_WORKDIR` sorts *after*
  `PBS_O_PATH` inside `Variable_List`, so it falls past the first wrap and
  `_pbs_workdir` returns `""`. Use `qstat -f -w`, or append continuation
  lines to the previous key in `_parse_blocks`.
  **Verified offline** (parsed value truncates mid-`PBS_O_LOGNAME`);
  **not verified live** — the multiplexed master had expired, and
  re-checking needs the user's one-time code.

- **`live_smoke.py`'s new Miyabi workdir assertion may fail the `--job`
  tier.** `assert workdir.startswith("/")` runs after the job reaches a
  terminal state, where `get_statuses` can fall through to `_parse_history`,
  whose `meta_data` has no `workdir` key at all. With the wrapping bug above
  this asserts on `""`, and the miyabi `candidates` list collapses to one
  unusable path. **Not verified** — blocked on the same live access.

- **The universal staging bullet contradicts Fugaku's own quota warning.**
  In `plugins/hpc-fugaku/skills/fugaku-submitting-jobs/SKILL.md`, line 64
  says jobs run from the group data area and *not* `$HOME`, because home is
  a 20 GiB area whose quota large outputs "can exhaust mid-run"; line 107 —
  from `templates/skills/submitting-jobs.md.tmpl` — says to stage run
  directories under `~/agent/work/`, which is in home. The universal bullet
  is the more prescriptive of the two, so an agent follows it into exactly
  the failure the facility note warns about. Give the template bullet an
  "unless the facility notes say otherwise" carve-out, or let
  `{{FACILITY_NOTES}}` override it. **Verified** in the rendered skill.

- **cell2026's demo aborts on a correctly configured machine.** The demo
  skill calls `get_projects` "to prove SSH is actually reachable" and says
  to stop if it errors, but cell2026's `get_projects` now unconditionally
  raises `NotImplementedError` (changed from `return []`).
  Fugaku's `skill_notes/demo.md` was updated for this same mismatch;
  cell2026's was not. **Verified** — the call raises; note the skill's stop
  condition says "isn't configured" while the error says "does not
  support", so the abort is likely but not certain.

- **CI's fork-PR message sends contributors into a loop.** The step runs
  three generators (`.github/workflows/ci.yml:48-50`) but the error at
  line 65 names only `render_facility_tables.py` and `render_skills.py`. A
  fork contributor follows it verbatim, never runs `render_plugins.py`, and
  fails again on the same step with the same message. **Verified** by
  reading the workflow.

### P3

- **`rccs_cloud`'s embeddings are stale relative to its chunks.** The
  MPICH guide edit regenerated `chunks.json` (last commit 2026-08-30) but
  not `embeddings.npy` (2026-08-18). The shapes still match, so nothing
  raises; semantic search just ranks on the old OpenMPI text. Re-run the
  ingest and commit the `.npy`. **Verified** from git dates.
- **`rccs_cloud` prose still says OpenMPI.** `skill_notes/submitting-jobs.md`
  now names `mpi/mpich-x86_64` but the sentence still reads "launch with
  `mpirun` (OpenMPI) instead", and the following paragraph's hostfile/PMI
  reasoning is OpenMPI-specific. Re-check against MPICH's Hydra.
- **`plugins/hpc/.mcp.json` is hand-maintained; the generator owns
  `mcp.json`.** The harnesses load the file the generator does not own, so
  a branch or entry-point change updates one and leaves the other pointing
  at the old ref. Generate both, or derive one from the other.
- **Orphaned generated-skill directories are no longer detected.**
  The check was removed wholesale so hand-authored custom skills
  would not be flagged. Generated and hand-written skills are
  indistinguishable on disk today, which is why it had to go rather than be
  refined; treating only `<slug>-<workflow>` directories as managed (or
  adding a frontmatter marker) would restore it. `render_plugins.py` also
  never removes a stale `plugins/hpc-<slug>/`.
- **`render_plugins.py`'s `manifest_version` never bumps, and reads only
  the Codex manifest.** Regenerating after a description change rewrites
  the manifest without a version bump, so clients cache stale skills; and a
  version bumped in `.claude-plugin/plugin.json` is overwritten with
  Codex's value on the next render. This conflicts with the repo
  convention that every plugin edit bumps the version.
- **`_parse_group_point` calls `int()` unguarded.** Four CSV cells are
  converted without a `try`, and `_group_point_or_none` catches only
  `RuntimeError`, so one odd row would take down `get_projects` for every
  group. **Checked live:** Fugaku emits clean integers for all of
  `ra000009`, `ra250029`, `hp250291`, and `trial` correctly has no
  `GROUP_POINT` row at all — so this is robustness, not a live defect.

### Housekeeping

- **`live_smoke.py` still aborts the whole run on an unreachable facility.**
  The agreed change — skip it and report the reason, since no one person
  has access to every machine — was never implemented; a later commit touched
  that file for the Miyabi workdir assertion instead.

After fixing these, rerun `tests/conformance.py`, `tests/notebook_client.py`
(also under an empty `HOME`), all three generated-output checks,
`git diff --check`, and the wheel-data check.

## Tool coverage

See [`IRI_CHECKLIST.md`](IRI_CHECKLIST.md) — one checklist for the whole
repo (not per-facility), since every facility shares the same tool set.
