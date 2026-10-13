---
name: octopus-reference
description: Use to answer questions about Octopus (RIKEN R-CCS) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# Octopus (RIKEN R-CCS) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="octopus", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="octopus")` shows the full table of
   contents and `read_doc_section(facility="octopus", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="octopus")` for static facts,
   `get_resources(facility="octopus")` for occupancy,
   `get_projects(facility="octopus")` for accounts, or
   `run_command_on_cluster(facility="octopus", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Ground Octopus-specific answers in the bundled guide. It records three
eight-GPU H200 nodes, one eight-GPU MI300X node, 192 CPU cores and about
2.3 TB usable memory per node, four vendor-specific partitions, and shared
Lustre storage.

The separate Octopus-Agent migration and this hub port lacked live SSH
access. Say so when a dated partition, module, storage, or accounting fact
matters, and use typed live tools where possible. Any raw module or scheduler
inspection follows the remote-command permission workflow.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest octopus` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
