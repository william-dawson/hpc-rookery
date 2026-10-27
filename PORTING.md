# Porting Guide: onboarding a new facility onto HPC Rookery

This guide is for an agent (or human) adding a new HPC facility to this
repo's unified MCP server — the multi-facility plugin that lets an agent
submit and monitor batch jobs, manage files, and search documentation for
every onboarded supercomputer through one process. It assumes **no other
context**: you do not need to have seen any other facility's directory to
follow this. Read it in full before writing any code.

**Porting a facility means opening a PR against this repo, not creating a
new repo.** There is one shared MCP-owning base plugin and one skill-only
plugin per facility, all generated from this repository. Your PR adds one
`facilities/<slug>/` directory; nothing else in this repo should need to
change (the server auto-discovers every facility directory, and generators
create its skill pack — see §5 and §7).

## 0. The mental model

`hpc_agent_core/` is the shared, generic engine: SSH execution, PSI/J-style
job data models, Slurm and Grid Engine scheduler backends, a documentation
search pipeline, health checks, and MCP serving glue. `hpc_mcp/` is the
**one, already-written, generic MCP tool surface** — every tool
(`submit_job`, `get_resources`, `fs_ls`, ...) already exists and takes a
`facility` slug as its first argument. **You do not write a tool surface.**
Your job is entirely contained in one new `facilities/<slug>/` directory:
your facility's facts (a config JSON, a hand-written guide), and a small
amount of Python that registers those facts and constructs a scheduler
backend.

Two hard rules:

1. **Everything you need lives in your own `facilities/<slug>/` directory.**
   You may read `hpc_agent_core/` and `hpc_mcp/` freely, but a genuine
   customization is expressed by what you pass into
   `config.register_facility(...)` and which `SchedulerBackend` subclass
   (and hook overrides) you construct — never by editing those shared
   files. If you think you need to edit them, re-read the relevant module's
   docstring; you've likely misunderstood an extension point.
2. **Write the code. Don't generalize it.** Your facility is expected to
   contain real, plain, explicit Python. See the next section.

## 0a. Where does this go? (read this before writing anything)

The single most important rule in this repo:

> **Facility-specific behavior goes in `facilities/<slug>/facility.py`,
> written out explicitly — even when another facility already does
> something that looks similar.**

The base classes stay simple and readable on purpose. They expose hooks;
they do not accumulate knowledge about individual machines. A shared class
that grows a `mandatory_account=True` flag, or a branch on the facility
slug, makes every facility harder to read and every future change riskier.
Two facilities each spelling out their own five readable lines does not.

**Duplication between facilities is explicitly fine.** RIKYU and HBW2 both
resolve a project/account to charge, in similar-looking code, in their own
`facility.py` files. That is the intended outcome, not tech debt to
refactor away — and reading them side by side shows why: they use
different env vars, different config keys, HBW2's account is *always*
mandatory while RIKYU's only matters for users in several projects, and
HBW2 raises where RIKYU deliberately doesn't. A shared "account helper"
would have to hide all four of those differences behind parameters, and
the next facility's variation would add a fifth. The explicit version says
what it does.

Use this table to decide where something belongs:

| What you have | Where it goes |
|---|---|
| A cluster fact (partitions, storage, limits, modules) | `data/<slug>_config.json` |
| Prose an agent needs (dialect gotchas, module tables, failure modes) | `skill_notes/<workflow>.md` (§7) |
| A connection/setting difference (host, embedding endpoint, guide filename, a `remotemanager.Computer` option) | a `register_facility(...)` argument (§5) |
| A scheduler-dialect difference already covered by a knob (GPU flag style, explicit `--nodes`, GPU vendor map) | a `SlurmBackend(...)` constructor argument (§6) |
| Filling in a default the caller omitted (partition, account, anything) | your own `apply_defaults()` override — **write it out** |
| Rejecting a spec the scheduler would reject confusingly | your own `validate_spec()` override — **write it out** |
| Reporting more than the base `get_projects()` returns | your own `get_projects()` override, calling `super()` — **write it out** |
| A tweak to the rendered script itself | your own `render_script()` override, reusing `_header()`/`render_body()` — **write it out** |
| Anything else specific to your machine | a plain function or method in your `facility.py` |

**What does belong upstream** — a much shorter list. Change
`hpc_agent_core/` only when something is true of *every* facility of that
kind, with no per-facility branching, and you can state it without naming
a machine. "sacct trails sbatch by a second or two on Slurm, so fall back
to scontrol" qualifies: it's a property of Slurm, it fixed a real bug on
two facilities independently, and the code mentions no facility. "HBW2
needs an account" does not qualify — it names a machine. When in doubt,
write it in your facility; moving code upstream later is easy and safe,
while pulling a machine-specific branch back out of a shared class after
three facilities depend on it is not.

**Making duplication safe.** The cost of duplication is drift, so this
repo pays for it with a shared conformance test rather than shared code:
`tests/conformance.py` runs the same behavioral assertions against *every*
registered facility (defaults actually get filled in, an unknown facility
errors clearly, a mandatory-field failure names the fix, ...). Add a case
there when your facility establishes a behavior others should also honor —
that's how a genuinely important change propagates, without collapsing
readable per-facility code into a shared abstraction.

## 1. Learn the target machine before writing anything

Answer these from the machine's real, official documentation (see §2 for
how to turn that into your guide) and, if you have SSH access already, by
actually running commands on the login node — a "zero-code smoke path"
(`ssh <host> sinfo`, `sacct --version` or a real `sacct` call, `module
avail`, a real GPU allocation test) is a cheap way to confirm your
assumptions *before* writing a line of port code, not after.

- **Scheduler**: Slurm or Grid Engine? Those two have a ready-made backend
  in core (see §6). Anything else needs its own `SchedulerBackend` subclass
  in your own facility directory, reusing `compute/base.py`'s helpers —
  that is a normal outcome, not a failure: `facilities/fugaku/compute.py`
  does exactly this for Fujitsu's PJM. Keep it in your facility until a
  *second* machine shares the scheduler; only then is there enough evidence
  to promote the dialect to core.
- **Accounting** (Slurm only): does `sacct`/`sacctmgr` actually work, or is
  accounting disabled (`accounting_storage/none`)? Test with a real `sacct`
  call, not just `sacct --version` (the binary can exist and still be
  configured off).
- **GPU request dialect** (Slurm only) — two *independent* questions, both
  must be answered separately:
  - Which flag: `--gpus=N` (a job-total count) or `--gres=gpu:N` (untyped)?
  - Does Slurm derive node count from the GPU count (so `--nodes` can be
    omitted), or must `--nodes` always be set explicitly? Do not assume
    these two questions have a shared answer — a real onboarded facility
    uses the `--gpus=N` flag but always sets `--nodes` explicitly, which is
    *not* the combination you'd get by picking one "style".
  - Single GPU vendor, or more than one (needing a different container
    flag, e.g. `--nv` vs `--rocm`, chosen by partition)?
  - Any partitions that need **no** GPU flag at all (e.g. a unified
    CPU+GPU superchip where the GPU is simply always present)?
- **Grid Engine specifics** (if applicable): is there one real queue with
  node selection done via a host pin (`-l hostname=<host>`) because naming
  a host directly as a queue is rejected? What parallel environment(s)
  (`-pe`) exist? Does `$SGE_HGR_gpu` (or equivalent) need translating to
  `CUDA_VISIBLE_DEVICES` yourself, or is GPU isolation automatic?
- **Storage**: tiers (home/group/scratch), paths, quotas, which are
  node-local vs shared, auto-purge policies. Two questions that are easy
  to miss: *where must a job run from* — is executing out of the home
  area forbidden outright, or merely quota-trapped? — and *what live
  command maps projects to their data-area paths*, so skills can read
  the correct volume at runtime instead of hardcoding one.
- **Software environment**: Lmod/environment-modules? Spack? Containers
  only? Conda/venv only? This shapes your guide, not your code.
- **Login mechanics**: SSH hostname, how a new key gets registered (a web
  portal? emailing an admin? self-service?).
- **Account/project**: is `--account` mandatory, optional with a
  machine-side default, or unused entirely?
- **Connection quirks** (rare): does this facility need a different
  `remotemanager.Computer` option than the shared default (login-shell
  template, bash submitter, `python3`)? Check
  `hpc_agent_core.config.COMPUTER_OPTION_NAMES` for the full set (shell,
  timeout, keyfile, landing_dir, transport, ...) if so.
- **Sensible default queue?** Does this facility have exactly one partition
  (or one obviously-correct default) that `submit_job` should fill in when
  the caller leaves `queue_name` blank, or does it have several
  partition families with no safe default (see §6's `default_queue_name`
  hook)?

## 2. Write your own guide — never point at a live external site

The docs-search pipeline (`rag/ingest.py`) only ever chunks a **local,
hand-written guide file** — it will never git-clone or fetch a remote docs
site for you, and you shouldn't build a mechanism that does either. A past
port that pointed its ingest step at "always re-fetch the live official
site" broke silently when that site moved domains and was restructured,
with nothing to catch it.

Read the machine's real official documentation, then **write your own
guide, in your own words** — a plain-language orientation for someone
driving the machine through the agent, not a paraphrase or copy of the
vendor manual. Deliberately omit:
- generic HPC/Linux background (what a batch scheduler is, what SSH is),
- anything the agent can query live instead of memorizing (`sinfo`,
  `module avail`, current queue occupancy, your billing balance).

Keep it to the stable facts that shape how a job gets described: hardware
shape, the scheduler dialect from §1, storage tiers and quotas, the module/
software story, common failure modes and their fixes. Save it as
`facilities/<slug>/data/<slug>_guide.md`.

If the official site later changes, re-sync by re-reading it and editing
your guide by hand — a deliberate, occasional, human-reviewed step — not by
building an automatic re-fetch.

## 3. Decide whether to cite a URL in search results

If the official docs site is genuinely stable and worth pointing users at,
your guide's search results can cite it (`docs_cite_url` in
`register_facility()`, see §5). If it's unreliable, moved recently, or
you're not confident it'll still be there next month, **leave
`docs_cite_url` blank** (the default) — search results simply won't mention
a URL, and nothing in your plugin should invent one to send a user to.

## 4. Directory layout

```
facilities/<slug>/               # e.g. facilities/rikyu/ — the ONLY directory your PR adds
  __init__.py                      # empty — makes this a Python package
  facility.py                      # §5/§6 — registers config + scheduler backend
  facility.json                    # §7 — small manifest for the generated facility table
  data/
    <slug>_config.json               # static facts: partitions, storage, modules
    <slug>_guide.md                  # §2
    docs_index/                      # generated — see §8
  skill_notes/                     # §7 — real, facility-specific skill content (the important part)
    configuring.md
    submitting-jobs.md
    monitoring-jobs.md
    reference.md
    demo.md
    reproducing.md
  compute.py                       # §6 — ONLY if your scheduler is neither Slurm nor Grid Engine
  skills/                          # §7 — ONLY for a workflow no other facility has
    <name>/SKILL.md
```

Note on hyphens, which bite in three places at once. A slug may contain a
hyphen where that reads naturally (`rccs-cloud`), and that string is what
every tool call passes as `facility`. But:

- the **directory** must be a valid Python identifier, so it uses
  underscores: `facilities/rccs_cloud/`;
- the default **data filenames** are derived from the slug with hyphens
  turned into underscores — slug `rccs-cloud` defaults to
  `rccs_cloud_config.json` and `rccs_cloud_guide.md`, not
  `rccs-cloud_config.json`;
- the **config file** and env-var prefix likewise use the underscore form
  (`~/.hpc-agent/rccs_cloud.json`, `RCCS_CLOUD_HOST`).

`facilities/rccs_cloud/` is a real worked example of all three. If your
existing data files are named something else entirely, don't rename them —
pass `facts_filename=` / `docs_filename=` to `register_facility()` instead,
which is exactly what that facility does (`cloud_config.json`).

Nothing outside `facilities/<slug>/` needs to change. `hpc_mcp/__init__.py`
auto-imports every `facilities/*/facility.py` it finds — that's what
"registering" your facility means, and it's how a new facility PR avoids
touching any shared file.

If your `facility.py` raises on import, your facility is skipped and
reported as unavailable (by `get_facilities` and by `hpc-doctor`) rather
than taking the server down for everyone else — but it is still broken, so
check `hpc-doctor` after adding it.

**Everything under `data/` must match a glob in `pyproject.toml`'s
`[tool.setuptools.package-data]`.** Those files are read at runtime via
`Path(__file__).parent / "data"`, which resolves fine in the editable
install you develop against and ships *nothing* in a wheel unless declared.
The current globs (`data/*.md`, `data/*.json`, `data/docs_index/*`,
`facility.json`) already cover the standard layout — but if you add a file
of another kind, run `python scripts/check_wheel_data.py`, which builds a
real wheel and looks inside it. This is not hypothetical: the first wheel
ever built from this repo contained zero guides and zero docs indexes, so
the documented `uv tool run --from git+...` install produced a server where
`get_facility` and `search_docs` failed on every facility, with local
testing looking perfectly healthy.

## 5. Wire up `facility.py` — config registration

```python
# facilities/<slug>/facility.py
from pathlib import Path

from hpc_agent_core import config

FACILITY = config.register_facility(
    slug="mymachine",                 # the string every tool's `facility` argument expects
    display_name="My Machine (Site)",
    description="One-line summary shown by get_facilities() and rendered "
                 "into the facility table.",
    default_host="mymachine",          # ssh.host fallback: a ~/.ssh/config alias, or user@hostname
    data_dir=Path(__file__).parent / "data",
    embed_base_url="http://llm.ai.r-ccs.riken.jp:11434/v1",  # shared RIKEN endpoint, or your own
    embed_model="bge-m3:567m",
    docs_cite_url="",                  # leave blank unless you decided otherwise in §3

    # --- Required: what an unconfigured user is told (see §5a) ---
    config_example={"ssh": {"host": "mymachine"}},   # + any extra key your machine requires
    setup_help=(
        "How a key gets registered, the real login hostname, and anything\n"
        "else that must be true before the first connection can work."
    ),

    # facts_filename="mymachine_config.json",   # default: "<slug>_config.json" — override
    #                                              only if reusing a differently-named file
    # docs_filename="mymachine_guide.md",       # default: "<slug>_guide.md" — same idea
    # computer_defaults={"shell": "zsh"},       # only if §1's "connection quirks" applies
)
```

Settings resolve environment variable > the user's config file > the
default you gave `register_facility()`. The config file itself lives at
`~/.hpc-agent/<slug-with-underscores>.json` (one common directory shared by
every facility). `ssh.host` also accepts `"localhost"` (or a `127.*`
address) for running directly on the cluster's own front-end/login node
with no SSH at all — `middleware.get_frontend()` is deliberately uncached
specifically so a config file edit (e.g. switching to/from `"localhost"`)
takes effect on the next tool call, not just after a full server restart.

### 5a. `config_example` and `setup_help` — the cold-start path

These two are not optional polish. They are what a user gets when they say
*"I want to use this machine"* and nothing is set up yet.

**Every tool call that needs the cluster returns your facility's full setup
directions when it can't connect** — not a bare SSH error.
`config.setup_instructions()` composes them in one consistent shape for
every facility: what's wrong, the exact file to create, your
`config_example` rendered as copy-pasteable JSON, your `setup_help`, how to
verify, and the name of your `<slug>-configuring` skill. This fires both
when no config file exists *and* when one exists but the connection fails
(a wrong host or an unregistered key needs the same fix, and a bare
"Permission denied" tells a new user nothing about where the setting
lives).

The same two values are rendered into your generated `<slug>-configuring`
skill via `{{CONFIG_EXAMPLE}}`/`{{SETUP_HELP}}` (§7), so the directions a
user reads in the skill and the ones a failing tool prints are the same
text by construction.

Write `setup_help` as a few short imperative lines covering only what's
machine-specific: where a public key gets registered (portal name or URL),
the real login hostname, and any extra config key your machine requires.
`config_example` must include every key needed for a *working* setup — if
your machine requires a project account, put it in the example, because
that JSON is what the user will copy.

What not to put there: anything generic (the config file's location, how to
verify, the skill name) is already supplied around your text. Keep it to
what only you know.

Which tools need configuration, and which don't. Any tool that reaches
the cluster checks for explicit local configuration first and otherwise
returns these setup directions, so a bundled `default_host` can't make an
unconfigured facility look available. The tools that open no connection
deliberately answer anyway: `get_facilities`, `get_facility` (your
packaged facts JSON), `render_job_script` (pure local defaults, validate
and render), and the three docs tools (your packaged index). That is what
lets an agent answer "what partitions does this machine have" and walk a
user through setup *before* they have access — gating those made the
`<slug>-reference` and `<slug>-configuring` skills circular. If you add a
tool, `tests/conformance.py` checks it against an explicit allowlist of
those ungated names, so a cluster-bound tool that skips the guard fails
there.

## 6. Wire up `facility.py` — the scheduler backend

Construct one of the two ready-made backends with the answers from §1, or
subclass `SchedulerBackend` yourself if neither fits. **Match the nearest
real precedent below rather than inventing your own combination from
scratch** — every combination shown here is verified against a real
facility, not guessed:

| Facility shape | Backend construction |
|---|---|
| Slurm, accounting on, job-total `--gpus=N`, single GPU vendor, Slurm derives node count | `SlurmBackend(facility=SLUG, has_accounting=True, gpu_request_style="gpus_total")` |
| Slurm, accounting on, untyped `--gres=gpu:N`, dual GPU vendor, `--nodes` always explicit | `SlurmBackend(facility=SLUG, has_accounting=True, gpu_request_style="gres", gpu_vendor_map={"h200": "--nv", "mi300x": "--rocm"})` |
| Slurm, accounting on, job-total `--gpus=N` **but** `--nodes` always explicit, some partitions need no GPU flag at all | `SlurmBackend(facility=SLUG, has_accounting=True, gpu_request_style="gpus_total", nodes_always_explicit=True, no_gpu_flag_prefixes=frozenset({"qc-gh200", "ng-dgx-m"}))` — see `facilities/rccs_cloud/facility.py` |
| Slurm, accounting **off** (a small/lab-scale machine), untyped `--gres=gpu:N` | `SlurmBackend(facility=SLUG, has_accounting=False, gpu_request_style="gres")` — note: this path degrades `get_recent_statuses` to "current live queue only" and is less battle-tested; verify against a real submitted job, not just `doctor` passing |
| Grid Engine, one real queue, some queue-like names are actually host pins | `GridEngineBackend(facility=SLUG, default_queue="all.q", host_pins={"nodeA", "nodeB"}, queue_aliases={"gpu"})` |

### What a backend must and may implement

If you construct `SlurmBackend`/`GridEngineBackend`, everything below is
already done — you only override what differs. If you subclass
`SchedulerBackend` directly (a scheduler core doesn't ship, like Fugaku's
PJM), the first group is the work.

**Required** — abstract, no default:

| Method | What it does |
|---|---|
| `render_script(spec)` | JobSpec → a batch script for your scheduler |
| `submit(spec)` | write the script on the cluster and submit it; return `{job_id, script_path}` |
| `get_statuses(job_ids)` | normalized `Job` per id |
| `get_recent_statuses(since)` | the user's recent/live jobs |
| `cancel(job_id)` | cancel, return the resulting state |

**Expected in practice** — the default works, but is wrong or unhelpful for
most real machines:

| Method | Default if you skip it | Override when |
|---|---|---|
| `check_scheduler()` | prints "no check defined" and passes | **Almost always.** This is how `hpc-doctor` proves your scheduler is reachable. `SlurmBackend` probes `sinfo --version`; PJM has no version flag on anything, so Fugaku checks its commands are on `PATH` via `doctor.check_commands_on_path()`. Getting this wrong is not cosmetic — a hardcoded Slurm probe once reported "slurm" as *Fugaku's* scheduler, because its login node happens to have Slurm installed for unrelated work. |
| `apply_defaults(spec)` | no-op | Your facility has defaults worth filling into a partial spec — one obvious partition, or a mandatory setting from the **user's** config (see below). Mutates `spec` in place; raising `ValueError` is legitimate when a required field can't be resolved. |
| `validate_spec(spec)` | no-op | The scheduler would reject something confusingly and you can catch it first — an allowed GPU-count list, a field your scheduler simply lacks, a value known to fail late (Fugaku rejects a comma-separated storage volume that `pjsub` accepts and the gate check kills minutes later). |

**Optional** — the default raises a clear "this facility does not support
X" through `SchedulerBackend._unsupported()`, which is the right answer when
your scheduler genuinely lacks the capability. Fugaku leaves four of these
alone precisely because PJM has no `sacctmgr` and no occupancy query:

| Method | Backs the tool |
|---|---|
| `update(job_id, spec)` | `update_job` — apply a JobSpec to a submitted job. Only apply fields the caller actually set (`spec.model_fields_set`); report the rest as not applied rather than dropping them silently |
| `get_projects()` | `get_projects` / `get_project` |
| `get_project_allocations(id)` / `get_user_allocations(id)` | the two allocation tools |
| `get_live_resources()` | `get_resources` / `get_resource` |
| `get_drained_nodes()` | `get_drained_nodes` |

**Facility-specific settings that belong to the *user*, not the machine.**
Some facilities require something the bundled `data/<slug>_config.json`
can't supply because it's a per-user choice — HBW2 requires `--account` on
every job, and which project to bill is the user's decision. Read those
from the user's own config file with `config.file_config(SLUG)` inside
`apply_defaults()`, and raise a `ValueError` naming the fix if the setting
is mandatory and missing. That's better than letting the scheduler reject
the job with its own opaque message. See `facilities/hokusai/facility.py`
for the full worked example (env var > `defaults.account` > a legacy
top-level key, then a clear error).

Complete example (see `facilities/rikyu/facility.py` and
`facilities/hokusai/facility.py` for the real versions this is based on):

```python
# facilities/<slug>/facility.py, continued
import os

from hpc_agent_core import config
from hpc_agent_core.compute.slurm import SlurmBackend
from hpc_agent_core.models import JobSpec
from facilities.registry import register_backend

SLUG = "mymachine"


class MyMachineBackend(SlurmBackend):
    def apply_defaults(self, spec: JobSpec) -> None:
        """Fill this facility's defaults into a partial spec, in place."""
        if not spec.attributes.queue_name:
            spec.attributes.queue_name = "gpu"       # your single obvious default
        # Only if your facility requires a per-user setting:
        if spec.attributes.account is None:
            cfg = config.file_config(SLUG)
            spec.attributes.account = (
                os.environ.get(f"{FACILITY.env_prefix}_ACCOUNT")
                or (cfg.get("defaults") or {}).get("account")
            )
        if not spec.attributes.account:
            raise ValueError(
                "No project named. Every job here is billed to a project, so "
                "--account is mandatory. Set spec.attributes.account, or a "
                f"default under defaults.account in {config.config_path(SLUG)}."
            )

    def validate_spec(self, spec: JobSpec) -> None:
        """Raise ValueError for a constraint the scheduler would only
        reject confusingly. No-op (inherited) if you have nothing to check."""
        # e.g. a fixed set of allowed per-job GPU counts — see Rikyu's real
        # validate_spec for the pattern.


BACKEND = MyMachineBackend(
    facility=SLUG,
    has_accounting=True,
    gpu_request_style="gpus_total",
)
register_backend(SLUG, BACKEND)
```

If your dialect genuinely doesn't fit any row above, don't force it —
subclass `SchedulerBackend` (`hpc_agent_core.compute.base`) directly,
reusing `duration_to_hms`, `to_epoch`, `parse_exit_code`, and `render_body`
from that module. This is a normal, expected outcome for an unusual
facility, not a sign something is missing.

If you need a machine-specific tweak to the *rendered script itself* (not
covered by any constructor knob), override `render_script` the way
`facilities/rccs_cloud/facility.py`'s `CloudSlurmBackend` does (injecting
`source /etc/profile` before the job body) — call the base class's
`_header()`/`render_body()` helpers and add your one extra line, rather
than reimplementing script rendering from scratch.

## 7. The facility manifest and your skills — `facility.json` and `skill_notes/`

### `facility.json` — small, feeds the facility table

A small, separate file the facility-table generator reads (not read by the
running server at all — that's `register_facility()`'s job):

```json
{
  "slug": "mymachine",
  "display_name": "My Machine (Site)",
  "description": "One-line summary — keep this in sync with facility.py's register_facility() call.",
  "scheduler": "slurm",
  "live_validated": false
}
```

Keep `live_validated` false while the port has only offline/rendering tests.
Change it to true only after the current integration has completed the live
doctor, read-only smoke checks, and a real tiny job from §9. The generated
documentation deliberately puts false entries in a separate “Awaiting live
validation” table so users do not mistake an offline port for a proven one.

After adding or editing this file, regenerate the tables it feeds:

```bash
python scripts/render_facility_tables.py
```

This rewrites the block between the `FACILITY_TABLE:START` /
`FACILITY_TABLE:END` HTML-comment marker pair in every file that has one
(README.md, AGENTS.md, the `hpc-facilities` skill). CI checks that generated
output is current; run the generator yourself and commit the result.

(Note for anyone editing *this* file: don't write the two markers next to
each other as a literal matched HTML-comment pair anywhere in this
document, including in a code block — `render_facility_tables.py` finds
marker pairs by scanning every file's raw text, this file included, and
would silently rewrite whatever sits between them.)

### `skill_notes/` — the real content, and the part that matters most

**Skills are not shared or generic across facilities.** Each facility gets
its own real, distinct skill file per workflow —
`plugins/hpc-<slug>/skills/<slug>-submitting-jobs/SKILL.md`,
`<slug>-monitoring-jobs`, `<slug>-configuring`, `<slug>-demo`,
`<slug>-reproducing` — generated by combining a shared template (the
mechanics every facility has identically: tool names, the "show before you
run" rule, the caching-mode table) with **your own freely-authored
markdown** in `facilities/<slug>/skill_notes/<workflow>.md`. The template
supplies the boilerplate; your `skill_notes/` files are where the actual
value of a port lives — GPU request dialect, the module-load table, MPI
launch gotchas (`srun` vs `mpirun`, PMI support, CPU affinity/NUMA
binding), common failure modes and their fixes, the SSH key registration
process. Look at `facilities/rikyu/skill_notes/` and
`facilities/rccs_cloud/skill_notes/` for two real examples of how different
this content is between facilities — RIKYU's is organized around a single
partition's fixed GPU-count table; R-CCS Cloud's is organized around a
~20-partition module table and per-hardware-family gotchas. Don't try to
make your facility's notes fit either one's shape; write what's actually
true and useful for your machine, in whatever structure that takes.

Write these the same way §1 told you to gather the facts — from real
official documentation and, ideally, real verified commands/jobs, not
guesses. A `skill_notes/<workflow>.md` file is optional (a missing one
falls back to a generic "see get_facility/search_docs" stub so a facility
isn't blocked from onboarding before every workflow has real notes), but a
port with genuinely empty `skill_notes/` for `submitting-jobs` is an
unfinished port, not a complete one — that file is normally the single most
valuable thing your PR contributes.

#### Placeholder tokens

A template (`templates/skills/<workflow>.md.tmpl`) is plain markdown with
literal `{{TOKEN}}` placeholders, resolved by simple text substitution
(`scripts/render_skills.py` — no templating engine, no logic, just
string replacement):

| Token | Resolves to |
|---|---|
| `{{FACILITY_NOTES}}` | The full contents of your `skill_notes/<workflow>.md` (or the fallback stub if that file doesn't exist yet). **Template-only** — has no meaning inside a `skill_notes/` file itself; writing it there just passes through as literal text, it is not substituted again. |
| `{{SLUG}}` | The facility's registered slug, e.g. `rikyu`. |
| `{{DISPLAY_NAME}}` | The facility's `display_name` from `facility.json`. |
| `{{ENV_PREFIX}}` | `slug`, uppercased with hyphens turned to underscores, e.g. `rccs-cloud` → `RCCS_CLOUD` — matches the env var prefix `config.py` actually uses. |
| `{{CONFIG_STEM}}` | `{{ENV_PREFIX}}` lowercased — the config filename stem, e.g. `~/.hpc-agent/rccs_cloud.json`. |
| `{{CONFIG_EXAMPLE}}` | Your registered `config_example` as formatted JSON (§5a). **Template-only.** |
| `{{SETUP_HELP}}` | Your registered `setup_help` text (§5a). **Template-only.** |

The last two come from your `register_facility(...)` call rather than from
`facility.json`, deliberately: the same two values are what an unconfigured
tool call returns at runtime, so sourcing the skill from them means the
setup directions a user reads and the ones a failing tool prints cannot
drift apart. Don't hardcode a config example in a template.

**These same four scalar tokens (not `{{FACILITY_NOTES}}`) also work inside
your own `skill_notes/*.md` files**, not just inside a template — the
generator substitutes `{{FACILITY_NOTES}}` into the template first, then
resolves `{{SLUG}}`/`{{DISPLAY_NAME}}`/`{{ENV_PREFIX}}`/`{{CONFIG_STEM}}`
across the *whole* assembled text, your notes included. Use them for
anything that would otherwise mean hardcoding your own slug repeatedly —
e.g. write `` `facility="{{SLUG}}"` `` in an example rather than typing the
literal slug by hand, so the example can't drift out of sync with
`facility.json` if the slug ever changes. (You don't have to use them —
the two facilities onboarded so far wrote the literal slug directly in
every example instead, which is equally correct, just a little more
typing. Either is fine; pick whichever you find more readable.)

After adding or editing anything under `skill_notes/`, regenerate:

```bash
python scripts/render_skills.py
```

CI regenerates `plugins/hpc-<slug>/skills/<slug>-*/SKILL.md` on your pull request
and commits them back, so you don't have to remember. Do run it locally
before you call the port done, though: the generated skill is what the
agent actually reads, and it's worth seeing that your notes land where you
expected.

#### A workflow only your facility has

Some machines have a workflow no other facility does. Fugaku's is
`fugaku-build`: cross-compiling for A64FX is a real, substantial workflow
there and meaningless on an x86 Slurm cluster. Adding a shared `build`
template would give every other facility an empty skill.

For that case, write the whole SKILL.md yourself at
`facilities/<slug>/skills/<name>/SKILL.md`. It is copied verbatim into
`plugins/hpc-<slug>/skills/<slug>-<name>/` by the same generator — no template
involved — with the scalar placeholders (`{{SLUG}}`, `{{DISPLAY_NAME}}`,
`{{ENV_PREFIX}}`, `{{CONFIG_STEM}}`) still substituted, so it can say
`facility="{{SLUG}}"` like any other skill. `{{FACILITY_NOTES}}` has no
meaning here — the whole file is yours.

It still needs YAML frontmatter whose `name:` matches the generated
directory, i.e. `name: {{SLUG}}-<name>`. `tests/conformance.py` enforces
this: Fugaku-Agent's original build skill shipped with no frontmatter at
all — the only skill in that repo missing it — so it had no name or
description for a client to discover it by.

Use this sparingly. If two facilities would want the same workflow, it
belongs in `templates/skills/` instead.

**Do not edit `templates/skills/*.md.tmpl`** as part of a facility PR — a
template is shared across every facility, so changing one is a deliberate,
separate, cross-cutting change (reviewed and tested against every onboarded
facility's rendered output, not just yours), not something to bundle into
onboarding a new machine.

## 8. Build the docs index

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m hpc_mcp.ingest mymachine
```

This writes `facilities/mymachine/data/docs_index/chunks.json` (+
`embeddings.npy` if an embedding key is configured for that facility).
Commit both.

## 9. Validate before calling the port done

```bash
python scripts/render_facility_tables.py          # after editing facility.json
python scripts/render_skills.py                   # after editing skill_notes/
python scripts/check_wheel_data.py                # your data/ really ships in a wheel

.venv/bin/python tests/conformance.py             # offline; the shared per-facility behavioral checks
.venv/bin/python -m hpc_mcp.doctor mymachine      # config, ssh, YOUR scheduler, guide, docs index, embedding
.venv/bin/python tests/live_smoke.py              # read-only tier, every registered facility (live SSH)
.venv/bin/python tests/live_smoke.py --job mymachine   # + submits a real tiny job on your facility
```

You don't strictly have to run the two `render_*` scripts — CI runs them on
your pull request and commits the result back to your branch. Run them
locally anyway if you want to see your skills as the agent will read them
before anyone else does. (A PR from a *fork* can't be written to, so there
CI tells you to run them and commit.)

Run `tests/conformance.py` first — it needs no cluster and catches the
common facility mistakes (a default that overwrites a caller's value, an
apply_defaults that isn't idempotent, a "you must configure X" error too
terse to act on, a missing guide/facts file). Add an entry to
`JOB_DEFAULTS` in `tests/live_smoke.py` so `--job <your-slug>` knows a
known-good tiny spec for your machine; the read-only tier needs nothing
from you (it iterates whatever is registered).

`tests/live_smoke.py` is deliberately short and machine-agnostic already —
it iterates `get_facilities()` for the read-only tier, so your new facility
is exercised automatically the moment it's registered; you don't need to
add facility-specific code there for read-only checks. If you're adding the
job-submission tier for your facility, follow the existing `--job` block's
shape (submit, poll `get_job_status` to a terminal state, read output via
`fs_tail`) rather than inventing a different pattern.

**Even so, a passing `doctor` and passing read-only smoke test are not
proof the port works.** Submit at least one real job — ideally one
requesting a GPU if the facility has any — and confirm you can see it
queue, run, and complete through the agent before considering this port
finished.

Two things that specifically bite on a real submission, both learned the
hard way here:

- **Watch the job to a genuinely terminal state.** A scheduler can accept a
  job, queue it, and reject it minutes later at a pre-execution check —
  Fugaku does exactly this, ending in `ERR` with no output file. Sampling
  the state 45 seconds after submission and seeing "queued" proves nothing,
  and reading it as success cost this repo two wrong diagnoses in a row.
- **Pass the environment through when overriding settings in a test.**
  `StdioServerParameters(env=None)` gives the server subprocess a *minimal*
  environment, not yours — so `MYMACHINE_FOO=bar python tests/live_smoke.py`
  silently does nothing and the server reads the config file instead. That
  invalidated an experiment here and led to a correct conclusion being
  retracted. `tests/live_smoke.py` now passes `env=` explicitly; do the same
  in any ad-hoc script.

## 10. Invariants that must hold, no exceptions

- **The MCP server must never fail to start.** Missing or malformed config
  for one facility is a *tool-call-time* error with a clear message for
  that facility only (e.g. "facility 'mymachine' is not configured — run
  the configuring skill"), never a startup crash, and never something that
  prevents other, correctly-configured facilities from working. Nothing
  above module scope in your `facility.py` should touch the network or read
  the config file eagerly. The loader also catches an import-time exception
  in any one facility so it can't deny the server to the rest — but don't
  rely on that; a facility that only works because of it is broken.
- **Never render an unvalidated string into a batch script.** Scheduler
  headers are line-oriented (`#SBATCH …`, `#PJM …`, `#$ …`), so a newline
  in any field you interpolate ends the directive and starts a script line
  the scheduler will execute. `JobSpec` already rejects control characters
  in every field that reaches a header, and constrains `name` further
  because it also becomes a filename — if you add a field of your own,
  either validate it the same way or `shlex.quote()` it at the render site.
- **A capability your scheduler lacks should raise, not return nothing.**
  Use the default (`SchedulerBackend._unsupported`) rather than returning
  an empty list, so "this machine has no per-project accounting" reads as
  a fact about the machine instead of looking like an empty result.
- **An unknown facility slug fails loudly, listing valid slugs.** Don't
  catch or reinterpret `config.get_facility`'s / `facilities.registry
  .get_backend`'s `ValueError` — let it surface as the tool error.
- **Bias agent-created files into one visible directory.** Job working
  directories, staged uploads, and scratch/demo files default under
  `~/agent/` (the default `jobs_dir="agent/jobs"` already does this) — not
  scattered loose in `$HOME`, and not hidden in a dotfile directory either.
  This is a bias, not a restriction: honor any explicit path the user gives.
- **Show before you run.** Before `submit_job`, `run_command_on_cluster`,
  or `fs_rm` actually does something, show the user what's about to happen
  (the JobSpec, the exact command/script, or the exact path being deleted)
  and a brief explanation. For `run_command_on_cluster`, always ask explicit
  permission for the exact commands shown and wait for the answer; prefer
  several short calls to one long compound shell program, inspect each result
  before continuing, and recap what actually ran and changed afterward (see
  the `remote-command` skill template for the full example). `fs_rm` is the
  strictest of the other two — confirm the path every time, even when the user
  asked for a deletion in general terms, because these filesystems have no
  trash. This applies only to those three consequential tools, not to every
  tool call — see the `demo` skill template for the wording that keeps it from
  over-generalizing into "narrate everything, including read-only calls."
- **Never invent a documentation URL.** If `docs_cite_url` is blank (see
  §3), search results carry no URL — don't add one back in anywhere.

## 11. What you do *not* need to write

The tool surface, the skill *mechanics* (templates), the codegen scripts,
README, and IRI checklist are already generic — a facility PR does **not**
touch:

- `hpc_mcp/hpc_server.py` / `docs_server.py` / `doctor.py` — already handle
  every registered facility generically.
- `templates/skills/*.md.tmpl` — shared across every facility; see §7's
  note on why a template edit is a separate, deliberate change.
- `scripts/*.py` (`render_facility_tables`, `render_skills`,
  `check_wheel_data`) — run them, don't edit them.
- `hpc_agent_core/` — the shared engine. If your facility needs something
  it doesn't offer, re-read §0a: the answer is nearly always a hook
  override or a `register_facility()` argument in your own directory.
- `README.md`'s prose, `IRI_CHECKLIST.md`, `AGENTS.md` — edit only if your
  facility exposes something genuinely new the checklist doesn't cover yet
  (e.g. a scheduler with no `has_accounting`-style project listing).

**You do write** `facilities/<slug>/skill_notes/*.md` (§7) — that's not an
exception to the rule above, it's the actual content of your port. The
generated `plugins/hpc-<slug>/skills/<slug>-*/SKILL.md` files are committed output
of your notes, not something you hand-edit directly (an edit there is
overwritten the next time anyone runs `render_skills.py`) — edit the
`skill_notes/` source instead and regenerate.

`tests/conformance.py` is the one shared file you may **add** to: when your
facility establishes a behavior every facility should honor, put the
assertion there so it applies to machines onboarded later too (§0a,
"making duplication safe"). Don't weaken an existing case to make your
facility pass — if a check doesn't fit your scheduler, that is usually the
check telling you something.

If you find yourself wanting to write a new *tool* or a new server entry
point just for your facility, stop — that's almost always a sign the thing
you need is actually a `SchedulerBackend` hook (§6) or a
`register_facility()` parameter (§5), not a new file.

## 12. Reproducible notebooks

`hpc_agent_core.client` (used by the generated `<slug>-reproducing` skill —
see `templates/skills/reproducing.md.tmpl` for the shared mechanics and
your own `skill_notes/reproducing.md` for anything facility-specific, e.g.
a billing caveat) needs nothing else facility-specific from you:
`pinned_params(...)` points at this one repo regardless of which facility a
given notebook
targets, and every call in the notebook passes `facility="mymachine"`
explicitly like any other tool call. Nothing to add here for a new
facility.
