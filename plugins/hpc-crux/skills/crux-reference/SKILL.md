---
name: crux-reference
description: Use to answer questions about Crux (ALCF) itself — hardware, partitions, storage, software, policies, or where to get help. Ground answers in the bundled guide and live tool output rather than prior knowledge.
---

# Crux (ALCF) reference

**Do not answer questions about this machine from memory.** Ground every
answer in the bundled guide or live tool output. The orientation facts at
the bottom of this skill are a fallback for when the tools are
unavailable — not the authoritative source.

## Workflow

1. `search_docs(facility="crux", query=...)` on the `hpc-docs` server,
   with the user's question. Cite the section breadcrumb it returns (e.g.
   "Running jobs"), not a URL.
2. If results look incomplete,
   `list_doc_sections(facility="crux")` shows the full table of
   contents and `read_doc_section(facility="crux", breadcrumb=...)`
   reads one section in full.
3. **For anything that changes over time — queue occupancy, node counts,
   installed software versions, your project's balance — check live state
   instead**, since the guide deliberately doesn't freeze these:
   `get_facility(facility="crux")` for static facts,
   `get_resources(facility="crux")` for occupancy,
   `get_projects(facility="crux")` for accounts, or
   `run_command_on_cluster(facility="crux", command="module avail")`.
4. If the guide doesn't cover it and no tool answers it, say so plainly
   rather than guessing.

**Search results carry no "Source:" URL unless this facility registered
one, and most don't. That's deliberate — never invent a URL to send the
user to.**

## Facility-specific reference

The bundled guide was written from ALCF's public documentation and the port
is live-validated (2026-11-02), but recorded queue limits, module contents,
and quota numbers can drift as ALCF adjusts the machine: refresh them live
rather than quoting the guide as current.

Live refresh commands (each needs the remote-command permission workflow):
`qstat -Q` / `qstat -Qf <queue>` for queue limits and state, `qstat -was1
<jobid>` for a job's comment on one line, `pbsnodes -avSj` for node health,
`module avail` for software, `myquota` / `myprojectquotas` for storage,
`sbank-list-allocations -r crux` for balances.

Machine status (maintenance, outages): status.alcf.anl.gov. Accounts,
projects, and the graphical sbank views: my.alcf.anl.gov. People problems:
support@alcf.anl.gov. Search results here cite ALCF's user guides
(docs.alcf.anl.gov/crux/) — a stable public site, unlike most facilities
here — so passing that URL along is fine.

## Keeping the guide fresh

The docs index is built from this facility's bundled guide
(`facilities/<dir>/data/`), an original hand-written write-up — never
re-scraped from a live site. If it goes stale, edit the guide and rebuild:
`python -m hpc_mcp.ingest crux` (it falls back to a BM25-only index
when no embedding key is configured), then commit the regenerated
`docs_index/`.
