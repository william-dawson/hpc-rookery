---
name: cell2026-reference
description: Use to answer questions about cell2026 (Shinobu Lab) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# cell2026 (Shinobu Lab) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="cell2026", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="cell2026")` shows the full table of
   contents and `read_doc_section(facility="cell2026", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="cell2026")` for static facts,
   `get_resources(facility="cell2026")` for occupancy,
   `get_projects(facility="cell2026")` for accounts, or
   `run_command_on_cluster(facility="cell2026", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Lead with the dual-scheduler distinction. Use the bundled guide for recorded
host/GPU behavior and `get_resources` for current Slurm and Grid Engine state.
There is no public documentation site, module system, or scheduler account.
Current GPU use or a scheduler-specific explanation may require a focused live
command after following the remote-command permission workflow. State that the
hub port awaits a fresh live test even though the original implementation was
successfully exercised in June 2026.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest cell2026` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
