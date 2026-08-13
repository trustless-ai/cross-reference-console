#!/usr/bin/env python3
"""The console's lineage answer must equal the reference implementation's.

`ui/index.html` carries a hand-ported copy of `lineage_graph.py` so the page
works with no server. Two implementations of one rule is exactly the situation
this whole repo exists to be suspicious about: the port can drift, and the
direction it drifts is predictable — toward the flattering answer, because
INDEPENDENT is the state that makes the matrix look strongest.

So this does not test the port against a fixture. It runs both implementations
over the *same embedded snapshot* and requires they agree per claim. A drift
that made the page say INDEPENDENT where the reference says
INDEPENDENCE_NOT_PROVEN fails here, which is the only failure mode worth CI time.

It also checks the surface: the edge line must actually consume the state. A
correct `linClaimState` that nothing calls renders the same reassuring sentence
as no implementation at all.
"""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lineage_graph import build_graph, pair_state  # noqa: E402
from lineage_graph import DERIVED, INDEPENDENT, NOT_PROVEN  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "ui" / "index.html"

fails = []


def chk(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


def claim_state_py(cells):
    """Worst state across GREEN pairs — the same collapse the port performs."""
    g = build_graph(cells)
    keys = sorted(g)
    if len(keys) < 2:
        return None
    worst = INDEPENDENT
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            st, _ = pair_state(g, keys[i], keys[j])
            if st == NOT_PROVEN:
                worst = NOT_PROVEN
            elif st == DERIVED and worst == INDEPENDENT:
                worst = DERIVED
    return worst


def main() -> int:
    src = INDEX.read_text()

    print("console lineage port — surface\n")
    # The state must be consumed by the renderer, not merely computed.
    edge_fn = re.search(r"function updateDynEdge\([\s\S]*?\n  \}", src)
    chk("updateDynEdge exists", edge_fn is not None)
    if edge_fn:
        body = edge_fn.group(0)
        chk("edge renderer calls linClaimState", "linClaimState(" in body)
        chk("edge renderer delegates to lineageMarker", "lineageMarker(" in body)
        # The regression this file did not previously catch. The old renderer wrapped the
        # whole marker in `if (lin) { ... }`, and linClaimState returns None with fewer
        # than two lanes — so an edge that held rendered with no qualifier at all. Asking
        # "can it render NOT PROVEN" was satisfied by the string being present in a branch
        # that never ran for the absent case.
        chk("renderer does not guard the marker on a possibly-absent state",
            "if(lin)" not in body.replace(" ", ""))

        # The states themselves now live in the extracted mapping, which is the thing a
        # conformance gate can call. Behaviour is asserted in ui/lineage-marker.test.ts;
        # what is checked here is that the mapping still covers every state and still
        # refuses to render DERIVED as a plain green.
        marker_src = (ROOT / "ui" / "lineage-marker.js").read_text(encoding="utf-8")
        for state in ("INDEPENDENT", "DERIVED", "NOT PROVEN"):
            chk(f"lineage marker can render {state}", state in marker_src)
        chk("DERIVED does not render as a plain green match",
            "'match'" in marker_src and "removeClass" in marker_src)
        chk("absent state is handled explicitly, not by omission",
            "lin === null" in marker_src and "unproven(" in marker_src)

    print("\ncross-implementation agreement on the embedded snapshot\n")
    node = shutil.which("node")
    if not node:
        # Could-not-check is never a pass. A skipped comparison here would mean
        # the port is unverified while CI prints green, which is the exact
        # failure this file was written to prevent.
        print("  FAIL  node not available — the port could not be compared")
        print("        (this is a COULD-NOT-CHECK, deliberately not a skip)")
        return 1

    seed = re.search(r'id="seed-registry"[^>]*>([\s\S]*?)</script>', src)
    chk("embedded snapshot found", seed is not None)
    if not seed:
        return 1
    snap = json.loads(seed.group(1))
    reg = snap.get("data", snap)

    start, end = src.index("const LIN_INDEPENDENT"), src.index("function updateAllDynEdges")
    harness = (src[start:end] +
               "\nconst out={};"
               "\nfor(const hex of Object.keys(REG.claims)){const r=linClaimState(hex);"
               "out[hex]=r?r[0]:null;}"
               "\nprocess.stdout.write(JSON.stringify(out));")
    js = f"const REG={json.dumps(reg)};\n{harness}"
    # Via a temp file, NOT `node -e`. The embedded snapshot pushes this payload
    # past 75 KB, and Windows caps a command line at 32,767 bytes — so `-e` fails
    # deterministically there. A verifier the second party cannot run is a
    # verifier that quietly becomes single-party.
    with tempfile.TemporaryDirectory() as td:
        script = pathlib.Path(td, "lineage_port.js")
        script.write_text(js, encoding="utf-8")
        r = subprocess.run([node, str(script)], capture_output=True, text=True,
                           timeout=60)
    chk("port evaluates without error", r.returncode == 0, r.stderr.strip()[:200])
    if r.returncode != 0:
        return 1
    got = json.loads(r.stdout)

    for hex_id in sorted(reg["claims"]):
        cells = [(nid, c) for nid, c in (reg.get("cells", {}).get(hex_id) or {}).items()
                 if (c.get("result") or (c.get("proof_payload") or {}).get("result")) == "GREEN"]
        want = claim_state_py([(n, c.get("proof_payload", c)) for n, c in cells])
        chk(f"{hex_id[:10]}…  port={got.get(hex_id)}  reference={want}",
            got.get(hex_id) == want)

    print()
    print("all green — console lineage port agrees with the reference"
          if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
