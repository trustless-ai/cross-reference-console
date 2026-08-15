#!/usr/bin/env python3
"""The Boardy rule — the rendered state must be part of the asserted state.

Named for @boardyai, whose formulation this implements (15 August 2026):

    "A correct internal verdict with a collapsed or missing UI marker is still a public
     falsehood, and vector tests cannot catch it unless the rendered state is part of the
     asserted state."

WHAT WAS MISSING. Two things were already tested and a third was not. `lineage_graph.py`
and the console's port agree on the STATE (check_console_lineage.py). The mapping from
state to marker behaves correctly in ISOLATION (ui/lineage-marker.test.ts). Nothing tied a
state to the exact text a reader sees, so the rendered wording could change — or quietly
lose its qualifier — with every existing check still green. The verdict layer is asserted;
the surface people actually read was not.

He called this an instrument-design problem rather than a discipline problem, and that is
the right frame: it is not that someone might forget to check the UI, it is that no
instrument could have caught it.

WHAT THIS ASSERTS.
  1. The shipped mapping (ui/lineage-marker.js — the same file the console imports, never a
     copy) is driven over every state it can be handed, including absent, malformed and
     unrecognised.
  2. Each result must equal the recorded golden in vectors/rendered-markers.golden.json.
     Changing what a reader sees therefore becomes a deliberate act that updates a pinned
     artifact, not a side effect of editing a string.
  3. No input produces an unqualified marker. `qualified` is true on every branch, and the
     NOT PROVEN branches must actually say so in their rendered tail — a flag set to true
     beside a bare green sentence would satisfy the letter and lose the point.
  4. Every state reachable from the live embedded snapshot is covered by the golden, so the
     table cannot drift into describing states that no longer occur while missing ones that
     do.

EXIT CODES: 0 all assertions hold · 1 a determinate mismatch · 2 could not check (no node,
no mapping, unreadable golden). Could-not-check is never a pass — a skipped comparison here
means the rendered surface is unverified while CI prints green, which is the failure this
file exists to prevent.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "ui" / "index.html"


def _arg(flag: str, default: pathlib.Path) -> pathlib.Path:
    """--marker/--golden override the paths. Not test scaffolding: it is how you check a
    candidate mapping before it ships, and it is also the only way to drive this check to
    its own failure — which the controls in test_check_boardy_rule.py do."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return pathlib.Path(sys.argv[i + 1])
    return default


MARKER = _arg("--marker", ROOT / "ui" / "lineage-marker.js")
GOLDEN = _arg("--golden", ROOT / "reference" / "vectors" / "rendered-markers.golden.json")

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

fails: list[str] = []


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


# The inputs a caller can hand the mapping. Absent and malformed are inputs, not edge cases:
# linClaimState returns null whenever the graph holds fewer than two lanes, which is the
# exact shape that previously rendered as an unqualified green.
CASES: list[tuple[str, object]] = [
    ("independent", ["INDEPENDENT", "written from specification material"]),
    ("derived", ["DERIVED", "node2 declares derivation from node1"]),
    ("unproven", ["INDEPENDENCE_NOT_PROVEN", "lineage refs unresolved"]),
    ("absent_null", None),
    ("malformed_string", "INDEPENDENT"),
    ("malformed_empty", []),
    ("malformed_nonstring", [7, "why"]),
    ("unrecognised_state", ["SOMETHING_NEW_IN_2027", "a state this build predates"]),
    ("missing_reason", ["INDEPENDENT"]),
]


def render_all(marker_path: pathlib.Path) -> dict | None:
    """Drive the shipped mapping under node. Returns None if it could not be run."""
    node = shutil.which("node")
    if not node:
        return None
    harness = (
        "const {lineageMarker} = require(process.argv[2]);\n"
        "const cases = JSON.parse(process.argv[3]);\n"
        "const out = {};\n"
        "for (const [name, input] of cases) {\n"
        "  try { out[name] = lineageMarker(input); }\n"
        "  catch (e) { out[name] = {__threw: String(e && e.message || e)}; }\n"
        "}\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "harness.cjs"
        h.write_text(harness, encoding="utf-8")
        try:
            r = subprocess.run(
                [node, str(h), str(marker_path.resolve()), json.dumps(CASES)],
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.SubprocessError:
            return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def snapshot_states() -> set[str] | None:
    """States actually reachable from the embedded snapshot, so the golden can't drift."""
    try:
        src = INDEX.read_text(encoding="utf-8")
    except OSError:
        return None
    seed = re.search(r'id="seed-registry"[^>]*>([\s\S]*?)</script>', src)
    if not seed:
        return None
    node = shutil.which("node")
    if not node:
        return None
    try:
        snap = json.loads(seed.group(1))
    except json.JSONDecodeError:
        return None
    reg = snap.get("data", snap)
    try:
        start, end = src.index("const LIN_INDEPENDENT"), src.index("function updateAllDynEdges")
    except ValueError:
        return None
    harness = (
        src[start:end]
        + "\nconst out=[];"
        "\nfor(const hex of Object.keys(REG.claims||{})){const r=linClaimState(hex);"
        "out.push(r?r[0]:null);}"
        "\nprocess.stdout.write(JSON.stringify(out));"
    )
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "s.js"
        f.write_text(f"const REG={json.dumps(reg)};\n{harness}", encoding="utf-8")
        try:
            r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=180)
        except subprocess.SubprocessError:
            return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return {("__absent__" if s is None else s) for s in json.loads(r.stdout)}
    except json.JSONDecodeError:
        return None


def main() -> int:
    print("the Boardy rule — the rendered state is part of the asserted state\n")

    if not MARKER.exists():
        print(f"  UNVERIFIABLE — mapping not found at {MARKER}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    rendered = render_all(MARKER)
    if rendered is None:
        print("  UNVERIFIABLE — could not execute the shipped mapping (node missing or it failed)",
              file=sys.stderr)
        print("  a skipped comparison is not a pass: the rendered surface would be unverified.",
              file=sys.stderr)
        return EXIT_UNVERIFIABLE

    if not GOLDEN.exists():
        print(f"  UNVERIFIABLE — golden not found at {GOLDEN}", file=sys.stderr)
        print("  regenerate with: --write-golden, then review the diff before committing.",
              file=sys.stderr)
        return EXIT_UNVERIFIABLE

    try:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  UNVERIFIABLE — golden unreadable: {e}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    expected = golden.get("markers", {})

    print("every input renders exactly what the golden records\n")
    for name, _ in CASES:
        got, want = rendered.get(name), expected.get(name)
        if want is None:
            chk(f"{name}: covered by the golden", False, "no golden entry — rendering unasserted")
            continue
        chk(f"{name}: renders as recorded", got == want,
            f"got {json.dumps(got)[:150]}")

    print("\nno input renders an unqualified marker\n")
    for name, _ in CASES:
        got = rendered.get(name) or {}
        chk(f"{name}: qualified", got.get("qualified") is True, json.dumps(got)[:120])

    # A `qualified: true` flag beside a bare green sentence satisfies the letter and loses
    # the point, so the NOT PROVEN branches must say so in the text a reader actually sees.
    print("\nthe qualifier is in the rendered text, not only in a flag\n")
    for name, _ in CASES:
        got = rendered.get(name) or {}
        if got.get("state") != "INDEPENDENCE_NOT_PROVEN":
            continue
        tail = got.get("tail", "")
        chk(f"{name}: tail names it NOT PROVEN", "NOT PROVEN" in tail, tail[:100])
        chk(f"{name}: tail gives a reason", len(tail.split("—", 1)[-1].strip()) > 12, tail[:100])

    print("\nthe golden covers the states the live snapshot can actually reach\n")
    live = snapshot_states()
    if live is None:
        chk("live snapshot states enumerated", False,
            "could not evaluate the embedded snapshot — coverage unchecked, not assumed")
    else:
        rendered_states = {(v or {}).get("state") for v in rendered.values()}
        for s in sorted(live):
            label = "absent (fewer than two lanes)" if s == "__absent__" else s
            covered = (s == "__absent__" and "INDEPENDENCE_NOT_PROVEN" in rendered_states) or s in rendered_states
            chk(f"live state covered: {label}", covered)

    print()
    if fails:
        print(f"{len(fails)} assertion(s) failed:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("the rendered surface matches the asserted state")
    return EXIT_OK


def write_golden() -> int:
    rendered = render_all(MARKER)
    if rendered is None:
        print("could not execute the mapping", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps({
        "note": "Rendered markers, pinned. The Boardy rule: the rendered state is part of the "
                "asserted state, so changing what a reader sees is a deliberate act that updates "
                "this file. Regenerate with reference/check_boardy_rule.py --write-golden and "
                "review the diff — a lost qualifier looks like a wording change here.",
        "source": "ui/lineage-marker.js",
        "markers": rendered,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN} ({len(rendered)} cases)")
    return EXIT_OK


if __name__ == "__main__":
    if "--write-golden" in sys.argv:
        sys.exit(write_golden())
    sys.exit(main())
