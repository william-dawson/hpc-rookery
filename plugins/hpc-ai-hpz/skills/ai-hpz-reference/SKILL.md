---
name: ai-hpz-reference
description: Use to answer questions about ai-hpz (hpz workstation) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# ai-hpz (hpz workstation) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="ai-hpz", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="ai-hpz")` shows the full table of
   contents and `read_doc_section(facility="ai-hpz", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="ai-hpz")` for static facts,
   `get_resources(facility="ai-hpz")` for occupancy,
   `get_projects(facility="ai-hpz")` for accounts, or
   `run_command_on_cluster(facility="ai-hpz", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Ground hpz answers in the bundled guide and `get_facility`: one node, 24
Slurm CPUs (Xeon Gold 6136, 12 cores × 2 threads), ~187 GiB, one Quadro RTX
5000 (16 GiB, sm_75) requested as `--gres=gpu:1`, one `debug` partition without
time limit, Slurm accounting off, GROMACS 2026.3 (thread-MPI, CUDA) in
`/usr/local/gromacs`, NVIDIA HPC SDK 24.5 / CUDA 12.4 via
`module use /opt/nvidia/hpc_sdk/modulefiles`.

These facts were read live on 2026-11-25. Software versions can change; when
a version matters, offer to confirm it live (remote-command workflow).

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest ai-hpz` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
