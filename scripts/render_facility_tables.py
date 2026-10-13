"""Render the "which facilities exist" table into every file that has a
marked placeholder for it, from the single source of truth:
facilities/*/facility.json.

    python scripts/render_facility_tables.py            # rewrite in place
    python scripts/render_facility_tables.py --check     # exit 1 if stale (CI)

Every facility PR that adds/changes a facilities/<slug>/facility.json must
re-run this (no --check) and commit the result — CI's --check run is what
catches a PR that forgot to.

Marked files are found by searching the repo for the marker pair itself
(FACILITY_TABLE:START / FACILITY_TABLE:END as an HTML comment or, in
Python, a plain comment) — no separate list to keep in sync. Add the marker
pair to any new skill/README that needs the table; nothing else to wire up.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = "FACILITY_TABLE:START"
END = "FACILITY_TABLE:END"
_MARKER_BLOCK = re.compile(
    r"(?P<start><!--\s*" + START + r"\s*-->)(?P<body>.*?)(?P<end><!--\s*" + END + r"\s*-->)",
    re.DOTALL,
)


def load_facilities() -> list[dict]:
    facts = []
    for manifest in sorted((ROOT / "facilities").glob("*/facility.json")):
        facts.append(json.loads(manifest.read_text()))
    return sorted(facts, key=lambda f: f["slug"])


def _table(facilities: list[dict]) -> list[str]:
    lines = ["| slug | facility | scheduler | description |",
             "|---|---|---|---|"]
    for f in facilities:
        lines.append(
            f"| `{f['slug']}` | {f['display_name']} | {f['scheduler']} | {f['description']} |"
        )
    return lines


def render_table(facilities: list[dict]) -> str:
    for f in facilities:
        if not isinstance(f.get("live_validated"), bool):
            raise ValueError(
                f"{f['slug']}: facility.json must set live_validated to true or false"
            )

    validated = [f for f in facilities if f["live_validated"]]
    awaiting = [f for f in facilities if not f["live_validated"]]
    lines = [
        "",
        "### Live-tested facilities",
        "",
        "These integrations have been exercised against their real scheduler.",
        "",
        *_table(validated),
        "",
        "### Awaiting live validation",
        "",
        "These ports register and pass the offline test suite, but have not yet",
        "completed an end-to-end check against the current live system.",
        "",
        *_table(awaiting),
        "",
    ]
    return "\n".join(lines)


def files_with_markers() -> list[Path]:
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if START in text and END in text:
            hits.append(path)
    return hits


def render_file(path: Path, table: str) -> str | None:
    text = path.read_text()
    new_text, n = _MARKER_BLOCK.subn(
        lambda m: m.group("start") + table + m.group("end"), text
    )
    if n == 0:
        return None  # markers present as plain text but not as a matched pair (malformed)
    return new_text if new_text != text else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                         help="Exit 1 if any marked file would change, without writing.")
    args = parser.parse_args()

    facilities = load_facilities()
    table = render_table(facilities)
    stale = []
    for path in files_with_markers():
        new_text = render_file(path, table)
        if new_text is None:
            continue
        stale.append(path)
        if not args.check:
            path.write_text(new_text)

    rel = [str(p.relative_to(ROOT)) for p in stale]
    if args.check:
        if rel:
            print("Facility tables are stale in:", *rel, sep="\n  ")
            print("\nRun: python scripts/render_facility_tables.py")
            return 1
        print(f"Facility tables up to date ({len(facilities)} facilities).")
        return 0
    print(f"Rendered {len(facilities)}-facility table into: " + (", ".join(rel) or "(nothing to update)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
