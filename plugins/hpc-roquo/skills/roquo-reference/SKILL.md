---
name: roquo-reference
description: Use to answer questions about ROQUO (RIKEN R-CCS) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# ROQUO (RIKEN R-CCS) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="roquo", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="roquo")` shows the full table of
   contents and `read_doc_section(facility="roquo", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="roquo")` for static facts,
   `get_resources(facility="roquo")` for occupancy,
   `get_projects(facility="roquo")` for accounts, or
   `run_command_on_cluster(facility="roquo", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

## Provenance — read this before quoting a number

ROQUO's bundled guide was written from the operator's online manual, and
**this port has not been validated against the live system.** Nothing here
has been confirmed by running it. Treat specifics — quotas especially,
which the manual itself marks TBD — as a starting point, and prefer a live
query (`get_resources`, `run_command_on_cluster`) over quoting the guide
when the answer matters.

The manual lives at `https://portal.roquo.qc.r-ccs.riken.jp/manual/en/`
and is the authority; say so if the user needs certainty.

## The facts most likely to be asked

- **Two architectures.** Login and `work` nodes are x86_64; GPU compute
  nodes are aarch64. This explains most "it worked yesterday on the login
  node" reports.
- **Two partitions**: `roquo` (135 GB200 nodes, 4 GPUs each, 8 racks) and
  `work` (5 x86_64 CPU-only nodes). The per-rack partitions were removed
  on 2026-10-13.
- **GPU dialect**: `--gres=gpu:N`, per node, N ≤ 4 — not RIKYU's job-total
  `--gpus=N`.
- **GPU generation**: GB200/Blackwell, compute capability 10.0
  (`sm_100` / `cc100`).
- **Storage**: `/home/hps1/<user>` (small), `/projects/hps1/<project>`
  (Lustre, persistent, shared), `$SLURM_SCRATCH` (node-local, deleted at
  job end).
- **Quotas**: not published — read them with
  `lfs quota -h -u $USER /home/hps1` and `lfs df -h /projects/hps1`.

## Where to look things up

`search_docs(facility="roquo", query=...)` searches the bundled guide,
which covers login, partitions, GPU plans, QOS, storage, modules, MPI,
containers and failure modes. `get_facility(facility="roquo")` returns
the same facts as structured data, including the ROQUO-E* error-code table
and the per-QOS wall-time limits.

Both work without SSH configured, so they're the right tools for
orientation before the user has access.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest roquo` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
