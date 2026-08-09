#!/usr/bin/env python3
"""The console's join step must name the in-force Cell schema.

Why this check exists, precisely: `ui/index.html` told every newcomer to sign a
`crc.cell.v1` Cell for the entire life of v2. Nobody wrote a wrong value — the
line was correct the day it was typed and became wrong when `CELL-v2.md` landed,
with no commit touching it and nothing failing. It was found by reading the
published page, not by any test.

That is the same failure mode as a container image path pointing at a renamed
org: a value that is not derived from the thing it describes, and so cannot
notice when that thing moves. The fix is to derive it (`ui/embed_snapshot.py`
stamps the marker at build time) and then to check the derivation here, so a
hand-edit or a stale build cannot quietly reintroduce it.

The in-force version is computed the same way `check_sunset.py` and
`gen_in_force.py` compute it — from the CELL-vN.md files present — so the three
cannot disagree about what is in force.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "ui" / "index.html"
MARKER = re.compile(r'<b id="in-force-schema">(crc\.cell\.v\d+)</b>')


def in_force_schema() -> str:
    """Highest CELL-vN.md present. Identical rule to check_sunset/gen_in_force."""
    versions = [int(m.group(1)) for p in ROOT.iterdir()
                if (m := re.fullmatch(r"CELL-v(\d+)\.md", p.name))]
    if not versions:
        print("FAIL  no CELL-vN.md files found — cannot derive the in-force schema")
        raise SystemExit(1)
    return f"crc.cell.v{max(versions)}"


def main() -> int:
    want = in_force_schema()

    if not INDEX.exists():
        print(f"FAIL  {INDEX.relative_to(ROOT)} does not exist")
        return 1

    html = INDEX.read_text(encoding="utf-8", errors="replace")
    found = MARKER.findall(html)

    # Absent marker is a failure, not a skip. If the element is renamed or
    # dropped, the build's stamping step silently becomes a no-op — the check
    # that quietly stops checking is the one worth guarding hardest.
    if not found:
        print("FAIL  the <b id=\"in-force-schema\"> marker is missing from "
              f"{INDEX.relative_to(ROOT)}.\n"
              "      Without it ui/embed_snapshot.py cannot stamp the schema and\n"
              "      the join step drifts unnoticed. Restore the marker.")
        return 1

    if len(found) > 1:
        print(f"FAIL  {len(found)} in-force-schema markers — expected exactly 1. "
              "Two places to update is how one of them goes stale.")
        return 1

    got = found[0]
    if got != want:
        print(f"FAIL  the console tells newcomers to sign {got}, but {want} is in force.\n"
              f"      Run: python3 ui/embed_snapshot.py")
        return 1

    print(f"ok    console join step names {got} — matches the in-force schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
