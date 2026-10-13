---
name: miyabi-reproducing
description: Use when the user asks to make a result on Miyabi (JCAHPC) reproducible, shareable, or turned into a notebook/script — or proactively suggest it after a chunk of exploratory job/file work that produced something worth preserving. Builds a Jupyter notebook that replays the real workflow via hpc_agent_core.client, not a hand-copied SSH script.
user-invocable: true
---

# Turning a Miyabi (JCAHPC) session into a reproducible notebook

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

## Every call passes `facility="miyabi"` explicitly

```python
job = hpc.submit_job(facility="miyabi", spec={...})   # whatever the real spec was
status = hpc.wait_for_job(job["job_id"], facility="miyabi")
result = hpc.fs_download(facility="miyabi", remote_path="...", local_path="./downloads/result.json")

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

The first live recording needs a working connection: either a multiplexed
SSH master that is currently open (`ssh -O check <alias>` says "Master
running") or an agent on a Miyabi login node with `ssh.host=localhost`. A
`mode="live"` run cannot answer a one-time-code prompt, so re-open the master
with `ssh -MNf <alias>` first if it has expired. Once the cache is complete,
`mode="replay"` can replay
the notebook elsewhere without a Miyabi account or local execution. State in
the notebook that the hub port was derived from the live-tested 2026-07-13
Miyabi-Agent implementation and should be revalidated when access returns.

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
   `get_resources(facility="miyabi")`** and pick from that — don't guess.
