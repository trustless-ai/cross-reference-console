#!/usr/bin/env python3
"""The currency mapping, asserted before the console is allowed to read the resolver.

@boardyai, 15 August 2026, on the ordering: "vectors before the network read. A verification
page should earn the right to make a new claim before it gets another source of uncertainty."

So this exists while ui/currency-marker.js is still unwired — the console makes no resolver
call today. The mapping is gated first; the live surface comes second.

THE TWO ASSERTIONS HE NAMED, which are the reason this file is not just a golden diff:

  1. NO REASON CAN MANUFACTURE A VERDICT. A reason accompanies a failure to establish one. If
     any COULD_NOT_CHECK surface ever carries a non-null verdict, the layering has collapsed.

  2. NO FAILURE DISAPPEARS INTO A GENERIC GREEN OR AMBER. resolver_unreachable, no_local_ipfs
     and lock_unreadable are three different next actions. Rendering them as one
     indistinguishable amber would keep the reason in the data and lose it on the surface —
     the same defect one layer out, and precisely the shape the reason field was introduced to
     prevent.

Everything else follows the sibling check (check_boardy_rule.py): drive the SHIPPED mapping,
pin every rendered result to a golden, and treat could-not-check as its own exit code.

EXIT: 0 all assertions hold · 1 determinate mismatch · 2 could not check (no node, no mapping,
unreadable golden). A skipped comparison is never a pass.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _arg(flag: str, default: pathlib.Path) -> pathlib.Path:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return pathlib.Path(sys.argv[i + 1])
    return default


MARKER = _arg("--marker", ROOT / "ui" / "currency-marker.js")
GOLDEN = _arg("--golden", ROOT / "reference" / "vectors" / "currency-markers.golden.json")

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
fails: list[str] = []


def canon(o) -> str:
    """Compare objects, not serialisation order. The golden is written with sort_keys=True and
    the harness returns JS insertion order; comparing raw dumps made every vector fail while
    every object was equal — a diff that was correct about bytes and wrong about the question."""
    return json.dumps(o, sort_keys=True)


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


# Every state the contract declares, plus the ones a caller can get wrong. Named so a state
# added without a vector cannot slip past (rule 5).
CASES: list[tuple[str, str, object]] = [
    ("not_run",              "NOT_RUN",         None),
    ("pending",              "PENDING",         None),
    ("checked_current",      "CHECKED",         "CURRENT"),
    ("checked_stale",        "CHECKED",         "STALE"),
    ("cnc_resolver",         "COULD_NOT_CHECK", "resolver_unreachable"),
    ("cnc_no_ipfs",          "COULD_NOT_CHECK", "no_local_ipfs"),
    ("cnc_lock",             "COULD_NOT_CHECK", "lock_unreadable"),
    ("cnc_no_reason",        "COULD_NOT_CHECK", None),
    ("unrecognised_verdict", "CHECKED",         "PROBABLY_FINE"),
    ("unrecognised_state",   "SOMETHING_NEW",   None),
]

# The boundary the two existing checks need (rule 3).
LEGACY: list[tuple[str, str, object]] = [
    ("legacy_current",              "CURRENT",      None),
    ("legacy_stale",                "STALE",        None),
    ("legacy_undetermined_resolver", "UNDETERMINED", "resolver_unreachable"),
    ("legacy_undetermined_upstream", "UNDETERMINED", "upstream_unreachable"),
    ("legacy_undetermined_ipfs",     "UNDETERMINED", "no_local_ipfs"),
    ("legacy_undetermined_lock",     "UNDETERMINED", "lock_unreadable"),
    ("legacy_unverifiable",          "UNVERIFIABLE", "resolver_unreachable"),
    ("legacy_unknown",               "SOMETHING",    None),
]


def render() -> dict | None:
    node = shutil.which("node")
    if not node:
        return None
    harness = (
        "const m = require(process.argv[2]);\n"
        "const cases = JSON.parse(process.argv[3]);\n"
        "const legacy = JSON.parse(process.argv[4]);\n"
        "const out = {states:{}, legacy:{}};\n"
        "for (const [name, a, b] of cases) { try { out.states[name] = m.currencyMarker(a, b); }\n"
        "  catch (e) { out.states[name] = {__threw: String(e && e.message || e)}; } }\n"
        "for (const [name, a, b] of legacy) { try { out.legacy[name] = m.fromLegacy(a, b); }\n"
        "  catch (e) { out.legacy[name] = {__threw: String(e && e.message || e)}; } }\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "h.cjs"
        h.write_text(harness, encoding="utf-8")
        try:
            r = subprocess.run([node, str(h), str(MARKER.resolve()), json.dumps(CASES), json.dumps(LEGACY)],
                               capture_output=True, text=True, timeout=120)
        except subprocess.SubprocessError:
            return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def write_golden(got: dict) -> int:
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps({
        "note": "Rendered currency markers, pinned. Changing what a reader is told is a deliberate "
                "act that updates this file — read the diff. Regenerate with "
                "reference/check_currency_marker.py --write-golden.",
        "source": "ui/currency-marker.js",
        **got,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
    return EXIT_OK


def main() -> int:
    if not MARKER.exists():
        print(f"UNVERIFIABLE — mapping not found at {MARKER}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    got = render()
    if got is None:
        print("UNVERIFIABLE — could not execute the mapping (node missing or it failed).", file=sys.stderr)
        print("A skipped comparison is not a pass: the surface would be unverified.", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    if "--write-golden" in sys.argv:
        return write_golden(got)
    if not GOLDEN.exists():
        print(f"UNVERIFIABLE — golden not found at {GOLDEN}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    try:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"UNVERIFIABLE — golden unreadable: {e}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print("currency mapping — asserted before the console reads the resolver\n")

    print("every state renders exactly what the golden records\n")
    for name, _, _ in CASES:
        chk(f"state {name}", canon(got["states"].get(name)) == canon(golden.get("states", {}).get(name)),
            json.dumps(got["states"].get(name))[:130])
    for name, _, _ in LEGACY:
        chk(f"legacy {name}", canon(got["legacy"].get(name)) == canon(golden.get("legacy", {}).get(name)),
            json.dumps(got["legacy"].get(name))[:130])

    surfaces = list(got["states"].values()) + list(got["legacy"].values())

    print("\nassertion 1 — no reason can manufacture a verdict\n")
    chk("a verdict appears only under CHECKED",
        all(s.get("state") == "CHECKED" or s.get("verdict") is None for s in surfaces))
    chk("every CHECKED surface names a verdict",
        all(s.get("state") != "CHECKED" or s.get("verdict") is not None for s in surfaces))
    chk("no COULD_NOT_CHECK surface carries a verdict",
        all(s.get("state") != "COULD_NOT_CHECK" or s.get("verdict") is None for s in surfaces))
    chk("a reason appears only where no verdict was established",
        all(s.get("reason") is None or s.get("verdict") is None for s in surfaces))

    print("\nassertion 2 — no failure disappears into a generic green or amber\n")
    reason_texts = {}
    for name in ("cnc_resolver", "cnc_no_ipfs", "cnc_lock"):
        s = got["states"][name]
        reason_texts[s.get("reason")] = s.get("text")
    chk("the three reasons produce three distinct texts", len(set(reason_texts.values())) == 3,
        json.dumps(reason_texts)[:200])
    chk("each names which side of the comparison went dark",
        all(isinstance(t, str) and len(t) > 40 for t in reason_texts.values()))
    chk("a missing reason is itself reported, not silently generic",
        got["states"]["cnc_no_reason"].get("reason") == "unspecified"
        and "no reason was recorded" in got["states"]["cnc_no_reason"].get("text", ""))

    print("\ngreen is reachable only from CHECKED + CURRENT\n")
    for s in surfaces:
        if s.get("tone") == "green":
            chk("green surface is CHECKED/CURRENT",
                s.get("state") == "CHECKED" and s.get("verdict") == "CURRENT", json.dumps(s)[:120])
    chk("exactly one case renders green",
        sum(1 for s in got["states"].values() if s.get("tone") == "green") == 1)
    chk("every surface is qualified", all(s.get("qualified") is True for s in surfaces))

    print("\nunrecognised input fails closed, in both directions\n")
    for name in ("unrecognised_verdict", "unrecognised_state"):
        s = got["states"][name]
        chk(f"{name} → COULD_NOT_CHECK", s.get("state") == "COULD_NOT_CHECK", json.dumps(s)[:120])
        chk(f"{name} is neither green nor red", s.get("tone") not in ("green", "red"), s.get("tone"))

    print("\nrule 3 — UNDETERMINED does not survive as a second canonical state\n")
    chk("legacy UNDETERMINED maps to COULD_NOT_CHECK",
        all(got["legacy"][n]["state"] == "COULD_NOT_CHECK"
            for n in ("legacy_undetermined_resolver", "legacy_undetermined_upstream",
                      "legacy_undetermined_ipfs", "legacy_undetermined_lock")))
    chk("legacy UNVERIFIABLE maps to COULD_NOT_CHECK",
        got["legacy"]["legacy_unverifiable"]["state"] == "COULD_NOT_CHECK")
    chk("upstream_unreachable carries through as resolver_unreachable",
        got["legacy"]["legacy_undetermined_upstream"]["reason"] == "resolver_unreachable")
    chk("no surface anywhere reports UNDETERMINED",
        all(s.get("state") != "UNDETERMINED" for s in surfaces))

    print("\nrule 5 — every declared state is reachable from some vector\n")
    reached = {s.get("state") for s in got["states"].values()}
    for st in ("NOT_RUN", "PENDING", "COULD_NOT_CHECK", "CHECKED"):
        chk(f"reachable: {st}", st in reached)
    verdicts = {s.get("verdict") for s in got["states"].values() if s.get("verdict")}
    for v in ("CURRENT", "STALE"):
        chk(f"reachable verdict: {v}", v in verdicts)

    print()
    if fails:
        print(f"{len(fails)} assertion(s) failed:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("the currency mapping holds — and the console still makes no network call")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
