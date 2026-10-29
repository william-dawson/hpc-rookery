---
name: roquo-reproducing
description: Use when the user asks to make a result on ROQUO (RIKEN R-CCS) reproducible, shareable, or turned into a notebook/script — or proactively suggest it after a chunk of exploratory job/file work that produced something worth preserving. Builds a Jupyter notebook that replays the real workflow via hpc_agent_core.client, not a hand-copied SSH script.
user-invocable: true
---

# Turning a ROQUO (RIKEN R-CCS) session into a reproducible notebook

Build a linear Jupyter notebook that reproduces what you and the user just
did, by calling the same MCP tool surface you've been using, via
`hpc_agent_core.client`.

## Your two capabilities

1. **The MCP tools already registered in this session** (`get_resources`,
   `submit_job`, `fs_download`, ...) — use these normally for the task
   itself, exactly as always.
2. **Python code inside the notebook file you produce**, using
   `hpc_agent_core.client`. This is the only place that code runs.

## Connecting — copy this exactly

```python
from hpc_agent_core.client import connect_sync, pinned_params

CACHE_DIR = "./.hpc_cache/<short-name-for-this-notebook>"
hpc = connect_sync(
    pinned_params(
        "https://github.com/william-dawson/hpc-rookery.git",
        "hpc-mcp",
        ref="main",
    ),
    mode="lazy",
    cache_dir=CACHE_DIR,
)
```

There is no `subdirectory=` argument — this repo's Python project lives at
its own root.

## Every call passes `facility="roquo"` explicitly

```python
job = hpc.submit_job(facility="roquo", spec={...})   # whatever the real spec was
status = hpc.wait_for_job(job["job_id"], facility="roquo")
result = hpc.fs_download(facility="roquo", remote_path="...", local_path="./downloads/result.json")

hpc.close()
```

No `await`, no `async with` anywhere — `connect_sync` gives plain blocking
calls. `wait_for_job` and `fs_download` already cache correctly on their
own (terminal poll result only; real downloaded bytes) — call them exactly
like this, no extra logic needed around them.

## Caching modes

| mode | behavior | use it for |
|---|---|---|
| `live` | always hits the real cluster | the first real run, to validate |
| `lazy` | cache hit if present, else live | iterating on later cells |
| `replay` | cache only, zero SSH | sharing the finished notebook |

**The account must be in the notebook.** A reproducible ROQUO notebook has
to pass `attributes.account` explicitly. Leaving it out doesn't fail — the
job runs against a restrictive default account and its output lands owned
by the wrong group — so a notebook that omits it reproduces *something*,
just not the run the user meant. Treat the project as a parameter of the
notebook, set once near the top, not a detail buried in one cell.

**Pin the partition too.** `roquo` and `work` are different architectures,
so a notebook that relies on the default partition silently becomes
non-reproducible the day someone changes it. Name it.

**Don't reproduce through `$SLURM_SCRATCH`.** Node-local scratch is
deleted when the job ends, so any step that writes results there and reads
them in a later cell will work once interactively and then fail. Stage
through `/projects/hps1/<project>` for anything a later cell reads.

**Module loads belong in the job, not the session.** Modules only load on
compute nodes, so a notebook cell that runs `module load` over
`run_command_on_cluster` (which executes on a login node) will not set up
what the job sees. Put module loads in `pre_launch` or the executable
itself.

## Where the notebook file goes

The user's own project directory, or wherever they say. It is a new file
for their work — not something written into any plugin installation or
repository.

## Steps, in order

1. **Write the minimal clean sequence of calls that produces the user's
   actual result** — not a transcript of the whole conversation.
2. **Alternate cells**: one markdown cell stating what happens next, one
   code cell that does it.
3. **Execute the code for real first**, and copy the actual captured
   stdout/return values into the notebook's saved cell outputs. The
   outputs you save must be what really printed — never text you expect it
   to produce.
4. **Run once with `mode="live"` from an empty `CACHE_DIR`** (see the
   billing note above before doing this). Then copy that resulting cache
   directory to sit next to the notebook file, and tell the user to commit
   both together if they're versioning this.
5. **If a partition/GPU choice isn't given or obvious, check
   `get_resources(facility="roquo")`** and pick from that — don't guess.
