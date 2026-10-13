"""Assert a built wheel actually contains every facility's runtime data.

Each facility reads its guide, facts JSON and docs index through
Path(__file__).parent/"data". That resolves fine in an editable install and
ships nothing in a wheel unless declared as package-data — so this check
exists because the first wheel built from this repo contained zero data
files, which would have made the documented `uv tool run --from git+...`
install produce a server where get_facility and search_docs failed on every
facility, with local testing looking perfectly healthy.

    python scripts/check_wheel_data.py          # builds a wheel and checks it
"""
import glob
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("_guide.md", "chunks.json", "_config.json", "facility.json")


def main() -> int:
    facilities = sorted(p.parent.name for p in (ROOT / "facilities").glob("*/facility.json"))
    if not facilities:
        print("no facilities found — nothing to check")
        return 1

    with tempfile.TemporaryDirectory() as out:
        subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", out, str(ROOT)],
                       check=True, stdout=subprocess.DEVNULL)
        wheel = sorted(glob.glob(f"{out}/*.whl"))[-1]
        names = zipfile.ZipFile(wheel).namelist()

    failed = False
    for needle in REQUIRED:
        hits = [n for n in names if needle in n]
        if len(hits) < len(facilities):
            print(f"✗ {needle}: {len(hits)} file(s), expected {len(facilities)} "
                  f"(one per facility) — this data would not install")
            failed = True
        else:
            print(f"✓ {needle}: {len(hits)} file(s)")
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    for egg in ROOT.glob("*.egg-info"):
        shutil.rmtree(egg, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
