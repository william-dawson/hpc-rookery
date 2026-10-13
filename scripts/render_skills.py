"""Render one SKILL.md per (facility, workflow) from a shared template plus
that facility's own hand-written notes — the placeholder mechanism for the
genuinely universal parts of a skill (tool names, caching-mode tables,
"show before you run"), while every facility's real cluster-specific
knowhow (GPU dialect, module tables, MPI gotchas, failure modes, SSH portal
name) stays freely-authored prose in its own file, not squeezed into a
rigid multi-slot template.

    python scripts/render_skills.py            # rewrite in place
    python scripts/render_skills.py --check     # exit 1 if stale (CI)

Inputs (per facility, from facilities/<dir>/):
  facility.json           slug, display_name (also used by
                           render_facility_tables.py)
  skill_notes/<workflow>.md   freely-authored markdown dropped verbatim into
                           that workflow's {{FACILITY_NOTES}} placeholder.
                           Optional — a missing file falls back to a short
                           generic pointer at get_facility/search_docs, so a
                           facility PR can add real notes incrementally.

Inputs (shared, from templates/skills/):
  <workflow>.md.tmpl       one per workflow (configuring, submitting-jobs,
                           monitoring-jobs, demo, reproducing). Editing a
                           template is a deliberate, cross-cutting change
                           that affects every facility at once — not
                           something a single facility's PR should need to
                           touch; see PORTING.md.

Output: plugins/hpc-<slug>/skills/<slug>-<workflow>/SKILL.md, one directory
per (facility, workflow) pair.  ``plugins/hpc`` stays small: it owns the
shared MCP servers and the one universal discovery skill, while a user only
installs a facility pack after choosing that facility. A facility PR that
adds/edits skill_notes/*.md must re-run this (no --check) and commit the
result; CI's --check run catches a PR that forgot to. Plugin skill folders
may also contain hand-authored custom skills; this renderer never treats
those as stale or tries to manage them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import hpc_mcp  # noqa: E402,F401 -- import registers every facility
from hpc_agent_core import config as _config  # noqa: E402

TEMPLATES_DIR = ROOT / "templates" / "skills"
PLUGINS_DIR = ROOT / "plugins"

_FALLBACK_NOTES = (
    "_No facility-specific notes yet for this workflow — see "
    "`get_facility(facility=\"{slug}\")` and `search_docs(facility=\"{slug}\", "
    "query=...)` on the `hpc-docs` server for details._"
)


def load_facilities() -> list[dict]:
    facs = []
    for manifest in sorted((ROOT / "facilities").glob("*/facility.json")):
        data = json.loads(manifest.read_text())
        data["_dir"] = manifest.parent
        facs.append(data)
    return sorted(facs, key=lambda f: f["slug"])


def skills_dir(fac: dict) -> Path:
    """The isolated skill-pack directory for one facility."""
    return PLUGINS_DIR / f"hpc-{fac['slug']}" / "skills"


def render_one(template_text: str, fac: dict, workflow: str) -> str:
    slug = fac["slug"]
    env_prefix = slug.upper().replace("-", "_")
    notes_path = fac["_dir"] / "skill_notes" / f"{workflow}.md"
    notes = notes_path.read_text().rstrip() if notes_path.exists() else _FALLBACK_NOTES.format(slug=slug)
    # {{FACILITY_NOTES}} is substituted FIRST, before the scalar placeholders
    # below — so {{SLUG}}/{{DISPLAY_NAME}}/{{ENV_PREFIX}}/{{CONFIG_STEM}}
    # also resolve if a facility's own skill_notes/*.md writes them (natural
    # for DRY-ness, e.g. `facility="{{SLUG}}"` instead of a hardcoded slug).
    # Reversing this order would silently leave those tokens unreplaced
    # inside notes content, since the scalar pass would already be done by
    # the time notes text enters the string.
    # CONFIG_EXAMPLE and SETUP_HELP come from the live registration rather
    # than facility.json, so the configuring skill shows byte-for-byte the
    # same JSON and prerequisites that an unconfigured tool call returns at
    # runtime (config.setup_instructions). Hardcoding them in the template
    # is how those two drift apart.
    registered = _config.get_facility(slug)
    config_example = json.dumps(registered.config_example, indent=2)
    setup_help = registered.setup_help or (
        "_No machine-specific setup notes registered for this facility._"
    )

    text = template_text.replace("{{FACILITY_NOTES}}", notes)
    text = text.replace("{{CONFIG_EXAMPLE}}", config_example)
    text = text.replace("{{SETUP_HELP}}", setup_help)
    text = text.replace("{{SLUG}}", slug)
    text = text.replace("{{DISPLAY_NAME}}", fac["display_name"])
    text = text.replace("{{ENV_PREFIX}}", env_prefix)
    text = text.replace("{{CONFIG_STEM}}", env_prefix.lower())
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                         help="Exit 1 if any generated skill would change, without writing.")
    args = parser.parse_args()

    facilities = load_facilities()
    templates = sorted(TEMPLATES_DIR.glob("*.md.tmpl"))
    if not templates:
        print(f"No templates found under {TEMPLATES_DIR}", file=sys.stderr)
        return 1

    stale = []
    written = []

    # Facility-unique skills: a workflow only one machine has, with no
    # shared template to render from. Fugaku's build guidance is the
    # motivating case — cross-compiling for A64FX is a real workflow there
    # and meaningless everywhere else, so adding a `build` template would
    # give every other facility an empty skill. These are copied verbatim
    # from facilities/<slug>/skills/<name>/SKILL.md, with the same scalar
    # placeholders substituted so they can still say facility="{{SLUG}}".
    for fac in facilities:
        facility_skills = skills_dir(fac)
        for skill_dir in sorted((fac["_dir"] / "skills").glob("*/")):
            source = skill_dir / "SKILL.md"
            if not source.exists():
                continue
            out_dir = facility_skills / f"{fac['slug']}-{skill_dir.name.rstrip('/')}"
            out_path = out_dir / "SKILL.md"
            rendered = render_one(source.read_text(), fac, "__unique__")
            if out_path.exists() and out_path.read_text() == rendered:
                continue
            stale.append(out_path)
            if not args.check:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(rendered)
                written.append(out_path)

    for template_path in templates:
        workflow = template_path.name.removesuffix(".md.tmpl")
        template_text = template_path.read_text()
        for fac in facilities:
            facility_skills = skills_dir(fac)
            out_dir = facility_skills / f"{fac['slug']}-{workflow}"
            out_path = out_dir / "SKILL.md"
            rendered = render_one(template_text, fac, workflow)
            current = out_path.read_text() if out_path.exists() else None
            if current == rendered:
                continue
            stale.append(out_path)
            if not args.check:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(rendered)
                written.append(out_path)

    rel = [str(p.relative_to(ROOT)) for p in stale]
    if args.check:
        if rel:
            print("Generated skills are stale:", *rel, sep="\n  ")
            print("\nRun: python scripts/render_skills.py")
            return 1
        print(f"Generated skills up to date ({len(facilities)} facilities x {len(templates)} workflows).")
        return 0

    print(f"Rendered {len(written)} skill file(s) across {len(facilities)} facilities.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
