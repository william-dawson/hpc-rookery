---
name: miyabi-reference
description: Use to answer questions about Miyabi (JCAHPC) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# Miyabi (JCAHPC) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="miyabi", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="miyabi")` shows the full table of
   contents and `read_doc_section(facility="miyabi", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="miyabi")` for static facts,
   `get_resources(facility="miyabi")` for occupancy,
   `get_projects(facility="miyabi")` for accounts, or
   `run_command_on_cluster(facility="miyabi", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

The bundled guide is based on live inspection and smoke jobs dated
2026-07-13, but this unified port could not be revalidated because Miyabi was
unavailable. Say so when a dated fact matters.

Refresh queue limits with `qstat --rsc -x`/`qstat --limit`, modules with
`module -t avail`, storage with `show_quota`, and compute tokens with
`show_token`. Those live commands require the remote-command permission
workflow. Miyabi-G uses the `LNG` module hierarchy; Miyabi-C uses `MC`.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest miyabi` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
