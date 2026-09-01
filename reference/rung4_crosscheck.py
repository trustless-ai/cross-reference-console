#!/usr/bin/env python3
"""Rung 4 — the live gate-vs-oracle cross-check. Runs the actual gate on each mutant and requires the
gate's observed attribution to equal the oracle's independent Aᵢ* — the executable form of the
shared-labelling failing witness.

The oracle (rung4_oracle.py) is PURE: it has no capability to reach the gate. Isolation is proven two
ways — a fast static AST pre-filter (§1, module-level, so an aliased `from check_served_bytes import
classify as g` cannot hide), and, load-bearing, CAPABILITY CONFINEMENT (§1c): the oracle is executed
with an explicit __builtins__ that excludes every import/exec/reflection route and offers only an
allowlist-guarded importer — so no syntax, including Python's auto-injected `__builtins__["__import__"]`
(Pavlo's 7th counterexample), resolves to anything that can load the gate. The runner then imports the
confined oracle and does the gate comparison here, where the subprocess call legitimately lives. The
gate's labels are COMPARED to Aᵢ*, never fed into it.

EXIT: 0 all comparisons + controls hold · 1 a comparison/control failed · 2 could not run.
"""

from __future__ import annotations

import ast
import builtins as _builtins
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
SERVED = HERE / "check_served_bytes.py"
ORACLE = HERE / "rung4_oracle.py"
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

ALLOWED_IMPORTS = {"itertools", "json", "pathlib", "sys", "__future__"}
# dynamic-execution + reflection primitives the pure oracle never needs (belt to the import-allowlist's
# braces — a blacklist here only has to hold within an already import-restricted module)
DYNAMIC = {"exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "vars"}
BANNED_ATTR = {"modules", "__dict__", "__builtins__", "__globals__", "__class__", "__mro__", "__subclasses__"}


def scan_oracle_isolation(src: str):
    """Static AST scan of the oracle's EXACT bytes, run on a pristine `ast` BEFORE the oracle is imported
    or executed — so the oracle cannot sabotage this walk at import time. Rejects any import outside the
    allowlist, any dynamic-execution primitive (exec/eval/compile/__import__), and any `sys.modules`
    access (the route that would monkeypatch this very verifier). Returns the list of leaks."""
    leaks = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            leaks += [f"import {a.name}" for a in node.names if a.name.split(".")[0] not in ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                leaks.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Name) and node.id in DYNAMIC:
            leaks.append(f"dynamic/reflection primitive: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_ATTR:
            # any base — catches sys.modules AND an aliased `import sys as _s; _s.modules[...]`
            leaks.append(f"introspection/tamper attribute: .{node.attr}")
    return leaks


# ── Capability confinement — the load-bearing isolation control (Pavlo's 7th counterexample) ─────────
# The AST scan above is a static pre-filter, NOT the proof. Blacklisting escape *syntax* one form at a
# time is unbounded: a scanned-clean source can still reach the gate through Python's auto-injected
# builtins — `__builtins__["__import__"]("check_served_bytes")` has no Import node and no bare __import__
# Name. So the oracle is EXECUTED with an explicit __builtins__ that has no import/reflection capability
# to name at all: a guarded importer locked to the allowlist, with eval/exec/compile/open/getattr/setattr/
# delattr/globals/vars/__import__(raw) simply absent. There is no capability to reach, by any syntax.
_UNSAFE_BUILTINS = {"__import__", "eval", "exec", "compile", "open", "globals", "vars",
                    "getattr", "setattr", "delattr", "input", "breakpoint"}


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    """The ONLY importer the oracle can reach — enforces the allowlist at RUNTIME, not just in the static
    scan. `import check_served_bytes` and `__builtins__["__import__"]("check_served_bytes")` both route
    here and both raise; only the pure allowlist resolves. `_builtins` itself is a runner-module global,
    never present in the oracle namespace, so the oracle cannot reach the real importer through it."""
    if name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import of {name!r} is not permitted in the isolated oracle namespace")
    return _builtins.__import__(name, globals, locals, fromlist, level)


def confined_builtins():
    """Real builtins MINUS every import/exec/reflection route, PLUS the allowlist-guarded importer. A
    fresh dict per call so a witness run cannot mutate the builtins the real oracle executes under."""
    b = {k: v for k, v in vars(_builtins).items() if k not in _UNSAFE_BUILTINS}
    b["__import__"] = _guarded_import
    return b


def runs_under_confinement(src: str):
    """Exec a source under the SAME confined builtins the real oracle runs with, in a FRESH namespace.
    Returns the exception it raised, or None if it ran clean. Hostile sources must raise (the gate never
    binds); allowlisted imports must run — proving the confinement is a capability boundary, not a
    syntactic guess."""
    ns = {"__builtins__": confined_builtins(), "__name__": "witness", "__file__": "<witness>"}
    try:
        exec(compile(src, "<witness>", "exec"), ns)
        return None
    except BaseException as e:  # noqa: BLE001 — a control: any raise means the route is blocked
        return e


# Scan the exact oracle bytes FIRST (fast static pre-filter), then execute those same checked bytes into
# an isolated namespace whose __builtins__ is set BEFORE exec — so Python does not inject the real
# builtins, and the real oracle itself runs capability-confined, not just the witnesses.
_ORACLE_SRC = ORACLE.read_text(encoding="utf-8")
_ISOLATION_LEAKS = scan_oracle_isolation(_ORACLE_SRC)
O = types.ModuleType("rung4_oracle")
O.__dict__["__name__"] = "rung4_oracle"
O.__file__ = str(ORACLE)
O.__dict__["__builtins__"] = confined_builtins()   # set before exec → Python keeps it, no real builtins
if not _ISOLATION_LEAKS:
    exec(compile(_ORACLE_SRC, str(ORACLE), "exec"), O.__dict__)


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
        # A mutated gate (label swap) runs as a TEMPORARY COPY in the same dir — the tracked
        # check_served_bytes.py is never rewritten (rewrite+restore left CRLF / a dirty worktree on
        # Windows). Same directory so the gate's sibling imports still resolve.
        gate = SERVED
        tmp_gate = None
        if served_src is not None:
            tmp_gate = HERE / ("_tmp_gate_" + pathlib.Path(td).name + ".py")
            tmp_gate.write_text(served_src, encoding="utf-8")
            gate = tmp_gate
        try:
            r = subprocess.run([sys.executable, str(gate), "--pins", str(pins)],
                               capture_output=True, text=True)
        finally:
            if tmp_gate is not None:
                tmp_gate.unlink(missing_ok=True)
    blamed = observed(r.stdout + r.stderr)
    labels = {inv: O.label_of(inv) for inv in O.INVARIANTS}
    mapped, unexplained = set(), []
    for line in blamed:
        hit = next((inv for inv, lab in labels.items() if lab in line), None)
        (mapped.add(hit) if hit else unexplained.append(line))
    return r.returncode, mapped, unexplained


def main() -> int:
    bad = 0
    print("rung 4 — live gate-vs-oracle cross-check\n")

    # 1. isolation proof — scanned on the oracle's EXACT bytes BEFORE it was imported/executed (module
    #    top), so the oracle cannot sabotage this scan at import time. If it leaked, the oracle was never
    #    executed and there is nothing safe to run — stop.
    print("oracle isolation — static AST pre-filter (fast fail-early; the capability confinement in §1c "
          "is the load-bearing proof)\n")
    ok = not _ISOLATION_LEAKS
    print(f"  {'ok  ' if ok else 'FAIL'}  rung4_oracle.py is gate-free ({'clean' if ok else _ISOLATION_LEAKS})")
    bad += not ok
    if _ISOLATION_LEAKS:
        print("\noracle not proven clean — it was NOT executed; refusing to run the O-dependent checks")
        return EXIT_BAD

    # 1b. pin the escape routes — the pre-import scan must red every known counterexample (incl. Pavlo's
    #     sixth: import-time sys.modules tampering) and still pass the clean oracle.
    print("\nisolation controls — the pre-import scan reds every known escape route\n")
    for nm, src in {
        "aliased import":      "from check_served_bytes import classify as g",
        "exec dynamic import": 'exec("import check_served_bytes as gate")',
        "eval dynamic import": 'g = eval("__import__")("check_served_bytes")',
        "sys.modules tamper":  'import sys\nsys.modules["ast"].walk = lambda t: []',
        "aliased sys.modules": 'import sys as _s\n_s.modules["ast"].walk = lambda t: []',
        "getattr reflection":  'import sys\ngetattr(sys, "modules")["ast"].walk = lambda t: []',
    }.items():
        caught = bool(scan_oracle_isolation(src))
        print(f"  {'ok  ' if caught else 'FAIL'}  {nm}: {'rejected' if caught else 'MISSED'}")
        bad += not caught
    clean_ok = not scan_oracle_isolation(
        "from __future__ import annotations\nimport itertools, json, pathlib, sys")
    print(f"  {'ok  ' if clean_ok else 'FAIL'}  clean oracle imports: {'pass' if clean_ok else 'WRONGLY REJECTED'}")
    bad += not clean_ok

    # 1c. capability confinement — the LOAD-BEARING isolation proof. Each hostile source is executed
    #     under the same confined builtins the real oracle runs with; it must RAISE (the gate never
    #     binds), by capability absence, not by the scan guessing its syntax. Pavlo's seventh
    #     counterexample is pinned first. The allowlisted imports must still run.
    print("\ncapability confinement — hostile source raises under the confined builtins (gate unreachable)\n")
    hostile = {
        "builtins __import__ (Pavlo #7)": '__builtins__["__import__"]("check_served_bytes")',
        "bare __import__ Name":           '__import__("check_served_bytes")',
        "plain import statement":         "import check_served_bytes",
        "eval route":                     'eval("__import__")("check_served_bytes")',
        "exec route":                     'exec("import check_served_bytes")',
        "getattr reflection":             'import sys\ng = getattr(sys, "modules")',
        "open file-read route":           'src = open("check_served_bytes.py").read()',
    }
    for nm, src in hostile.items():
        err = runs_under_confinement(src)
        blocked = err is not None
        print(f"  {'ok  ' if blocked else 'FAIL'}  {nm}: "
              f"{'blocked (' + type(err).__name__ + ')' if blocked else 'REACHED GATE'}")
        bad += not blocked
    for nm, src in {"itertools": "import itertools",
                    "json/pathlib/sys": "import json, pathlib, sys",
                    "__future__": "from __future__ import annotations"}.items():
        err = runs_under_confinement(src)
        ran = err is None
        print(f"  {'ok  ' if ran else 'FAIL'}  allowlisted import '{nm}': "
              f"{'runs' if ran else 'WRONGLY BLOCKED (' + type(err).__name__ + ')'}")
        bad += not ran

    if not SERVED.exists() or not (O.PINS / (O.LIVE + ".json")).exists():
        print("UNVERIFIABLE — gate or live pin record missing", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    W = O.witness_bases()

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
