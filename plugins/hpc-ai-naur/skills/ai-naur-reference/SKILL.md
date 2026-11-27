---
name: ai-naur-reference
description: Use to answer questions about ai-Naur (Naur GB300 node) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# ai-Naur (Naur GB300 node) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="ai-naur", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="ai-naur")` shows the full table of
   contents and `read_doc_section(facility="ai-naur", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="ai-naur")` for static facts,
   `get_resources(facility="ai-naur")` for occupancy,
   `get_projects(facility="ai-naur")` for accounts, or
   `run_command_on_cluster(facility="ai-naur", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Ground naur answers in the bundled guide and `get_facility`: one aarch64
node, 72 Neoverse-V2 cores (one thread each), ~744 GiB, one NVIDIA GB300
(~251 GiB, compute capability 10.3) requested as `--gres=gpu:1` and hidden
from jobs that do not request it, the `naur` partition without time limit,
no memory requests, no working Slurm accounting, NVIDIA HPC SDK 26.9
(`module load nvhpc/26.9`) and CUDA 13.2 (`module load cuda-13.2`), no
GROMACS and no Singularity/Apptainer.

naur shares its Slurm with three other machines (`prado`, `shannon`,
`backus`). Questions about those are outside this facility; say so rather
than answering from naur's facts.

These facts were read live on 2026-11-27. Software versions can change; when
a version matters, offer to confirm it live (remote-command workflow).

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest ai-naur` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
