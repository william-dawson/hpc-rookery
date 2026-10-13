---
name: tsubame-reference
description: Use to answer questions about TSUBAME4.0 (Science Tokyo) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# TSUBAME4.0 (Science Tokyo) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="tsubame", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="tsubame")` shows the full table of
   contents and `read_doc_section(facility="tsubame", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="tsubame")` for static facts,
   `get_resources(facility="tsubame")` for occupancy,
   `get_projects(facility="tsubame")` for accounts, or
   `run_command_on_cluster(facility="tsubame", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Lead with TSUBAME's resource-type model: `node_f`, smaller GPU/MIG slices, or a
CPU-only type. Read the bundled facts for stable recorded shapes, and use
`search_docs(facility="tsubame")` for the guide. Query live commands for
changing facts such as installed module versions, queue occupancy, group point
balances, and storage quota. State that the hub port has not yet been live
revalidated when accuracy depends on the current system.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest tsubame` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
