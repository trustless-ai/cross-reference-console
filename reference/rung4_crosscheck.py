#!/usr/bin/env python3
"""Rung 4 — the live gate-vs-oracle cross-check. Runs the actual gate on each mutant and requires the
gate's observed attribution to equal the oracle's independent Aᵢ* — the executable form of the
shared-labelling failing witness.

The oracle (rung4_oracle.py) is PURE: it imports nothing that can reach the gate. This runner proves
that isolation as a real fact (§1, an AST scan of the oracle's imports — module-level, so an aliased
`from check_served_bytes import classify as g` cannot hide), then imports the oracle and does the gate
comparison here, where the subprocess call legitimately lives. The gate's labels are COMPARED to Aᵢ*,
never fed into it.

EXIT: 0 all comparisons + controls hold · 1 a comparison/control failed · 2 could not run.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rung4_oracle as O  # noqa: E402

SERVED = HERE / "check_served_bytes.py"
ORACLE = HERE / "rung4_oracle.py"
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2


def observed(out: str):
    return [m.group(1).strip() for m in re.finditer(r"^ {4}- (.+)$", out, re.M)]


def run_gate_on(transform, served_src=None):
    """Run the real gate on the mutant applied to the live record. Returns (rc, mapped, unexplained):
    rc — the gate's exit code (a class, not ignored); mapped — blamed labels resolved to invariant ids;
    unexplained — blamed lines matching NO known invariant label. A correct-plus-extra failure must not
    pass, so the caller requires rc == 1 AND mapped == Aᵢ* AND no unexplained lines."""
    with tempfile.TemporaryDirectory() as td:
        pins = pathlib.Path(td) / "pins"
        pins.mkdir()
        for p in O.PINS.glob("*.json"):
            (pins / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        (pins / (O.LIVE + ".json")).write_text(
            json.dumps(transform(O.load_reference()), indent=2) + "\n", encoding="utf-8")
        backup = None
        if served_src is not None:
            backup = SERVED.read_text(encoding="utf-8")
            SERVED.write_text(served_src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, str(SERVED), "--pins", str(pins)],
                               capture_output=True, text=True)
        finally:
            if backup is not None:
                SERVED.write_text(backup, encoding="utf-8")
    blamed = observed(r.stdout + r.stderr)
    labels = {inv: O.label_of(inv) for inv in O.INVARIANTS}
    mapped, unexplained = set(), []
    for line in blamed:
        hit = next((inv for inv, lab in labels.items() if lab in line), None)
        (mapped.add(hit) if hit else unexplained.append(line))
    return r.returncode, mapped, unexplained


def main() -> int:
    if not SERVED.exists() or not (O.PINS / (O.LIVE + ".json")).exists():
        print("UNVERIFIABLE — gate or live pin record missing", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    bad = 0
    W = O.witness_bases()
    print("rung 4 — live gate-vs-oracle cross-check\n")

    # 1. isolation proof — the oracle can reach the gate through NO path. An ALLOWLIST of imports (only
    #    the stdlib the pure oracle needs) plus rejection of every dynamic-execution primitive
    #    (exec/eval/compile/__import__) — so an aliased import, `exec("import check_served_bytes as g")`,
    #    or an eval/compile route is all refused, not just the static `import`/`__import__` forms a
    #    blacklist would catch. This is what makes Aᵢ* provably label-free.
    print("oracle isolation — allowlisted imports, no dynamic-execution primitives\n")
    tree = ast.parse(ORACLE.read_text(encoding="utf-8"))
    ALLOWED = {"itertools", "json", "pathlib", "sys", "__future__"}
    DYNAMIC = {"exec", "eval", "compile", "__import__"}
    leaks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            leaks += [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in ALLOWED]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED:
                leaks.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Name) and node.id in DYNAMIC:
            leaks.append(f"dynamic-exec primitive: {node.id}")   # catches exec(...)/eval(...)/compile/__import__
    ok = not leaks
    print(f"  {'ok  ' if ok else 'FAIL'}  rung4_oracle.py is gate-free ({'clean' if ok else leaks})")
    bad += not ok

    # 2. live comparison — for each mutant, gate observed attribution must EXACTLY equal Aᵢ*, with the
    #    gate exiting 1 and blaming nothing unexplained (a correct-plus-extra failure fails here).
    print("\nlive comparison — gate observed_attribution == Aᵢ*  (rc==1, exact, no unexplained)\n")
    for name, (transform, _) in O.MUTANTS.items():
        a_star = O.attribution(transform, W)
        rc, mapped, unexplained = run_gate_on(transform)
        ok = rc == 1 and mapped == a_star and not unexplained
        detail = ""
        if not ok:
            detail = f"  [rc={rc} gate={sorted(mapped)} Aᵢ*={sorted(a_star)} unexplained={unexplained[:2]}]"
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{detail}")
        bad += not ok

    # 3. shared-labelling failing witness — swap a REAL gate assertion label; the exact comparison reds
    print("\nreal gate-label swap — the executable failing witness for shared labelling\n")
    src = SERVED.read_text(encoding="utf-8")
    frm, to = "{short}: carries availability.serving", "{short}: lists at least one gateway"
    if frm not in src:
        print("  FAIL  swap anchor not found — control patched nothing"); bad += 1
    else:
        a_star = O.attribution(O.m_drop_serving, W)                 # label-free {serving}
        rc, mapped, unexplained = run_gate_on(O.m_drop_serving, served_src=src.replace(frm, to, 1))
        # the swap must make the exact comparison fail: mapped != Aᵢ* (gate now blames gateway)
        caught = not (rc == 1 and mapped == a_star and not unexplained)
        print(f"  {'ok  ' if caught else 'FAIL'}  serving-label swapped→gateway: gate {sorted(mapped)} "
              f"vs Aᵢ* {sorted(a_star)} — {'comparison reds' if caught else 'MISSED'}")
        bad += not caught

    print()
    print("gate compared against the label-free oracle; a real label swap reds the exact comparison"
          if not bad else f"{bad} check(s) failed")
    return EXIT_BAD if bad else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
