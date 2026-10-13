---
name: irene-reference
description: Use to answer questions about Irene (CEA TGCC) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# Irene (CEA TGCC) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="irene", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="irene")` shows the full table of
   contents and `read_doc_section(facility="irene", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="irene")` for static facts,
   `get_resources(facility="irene")` for occupancy,
   `get_projects(facility="irene")` for accounts, or
   `run_command_on_cluster(facility="irene", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

Search the bundled Irene guide first. Use `get_facility` for recorded hardware,
`get_resources` for current `ccc_mpinfo` output, and `get_projects` for live
project/partition associations. Current QoS, consumption, module versions, and
quota require focused live checks with `ccc_mqinfo`, `ccc_myproject`,
`module avail`, or `ccc_quota` after following the remote-command permission
workflow. State that this hub port still awaits live TGCC validation whenever
the answer depends on current operations.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest irene` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
