#!/usr/bin/env python3
"""Prove the two operational gates can fail, once per claim they make.

@boardyai closed the wiring thread with two disciplines: keep the served-byte comparison in the
availability record, and keep `selects` authoritative. check_served_bytes.py and
check_selects_authoritative.py convert those into gates — and a gate nobody has watched fail is
just a longer way of writing the discipline down.

The classifier gets the most attention here, because it is the piece that could do real harm.
It exists to say "this CDN added a beacon" instead of "these bytes were altered" — and a loose
version would launder a genuine substitution into an operational footnote, on a page whose
entire claim is integrity. So it is driven with a substitution, a visible anchor, a script tag,
two insertions and a truncation, and every one of them must come back DIFFERS.

EXIT: 0 all cases caught · 1 one survived · 2 could not run.
"""

from __future__ import annotations

import json
import pathlib
import contextlib
import io
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins"
SELECTS = ROOT / "reference" / "check_selects_authoritative.py"
SERVED = ROOT / "reference" / "check_served_bytes.py"
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

sys.path.insert(0, str(ROOT / "reference"))
from check_served_bytes import classify  # noqa: E402

LIVE = "bafybeihim4cjh2uqxlctepgibzdhr77rag53mqu6vlces72eyyiqnjjipe"
CANON = b"<html>\n<body>\n<p>the pinned page</p>\n</body>\n</html>\n"
ANCHOR = (b'<a href="https://ipfs.io/cdn-cgi/content?id=abc" aria-hidden="true" '
          b'rel="nofollow noopener" style="display: none !important; visibility: hidden '
          b'!important"></a>')

bad = 0


def run(script: pathlib.Path, pins: pathlib.Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(script), "--pins", str(pins)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def observed_attribution(out: str) -> list[str]:
    """The assertion labels the gate actually blamed.

    Parsed from the gate's own failure list rather than from anywhere in stdout, so
    'the word appears somewhere in the output' cannot be mistaken for 'this assertion
    was the one that failed'.
    """
    # The two gates end with differently-worded summaries ("N record(s) name something
    # that does not exist:", "N serving claim(s) missing, malformed or false:"), so the
    # anchor is the shape of the list, not its heading. An earlier version anchored on a
    # string neither gate emits and would have reported "never blamed" for every mutant —
    # which is the same defect one level up, in the harness that checks for it.
    return [m.group(1).strip() for m in re.finditer(r"^ {4}- (.+)$", out, re.M)]


def mutate(fn, script: pathlib.Path, name: str, why: str, expect) -> None:
    """Apply fn to the live record and require exit 1 with the DECLARED attribution set.

    Pavlo Tvardovskyi's conformance target, 2026-08-15:

        for each targeted mutant m_i, declare the expected attribution set A_i and
        require the OBSERVED attribution to match A_i — not merely that the gate goes
        red somewhere. In the simple case A_i = {I_i}, but singleton attribution is
        not universally required: one mutation can legitimately violate several
        invariants.

    So `expect` is a set of distinctive substrings, one per invariant the mutant is
    declared to violate. Matching is set equality up to the f-string interpolation in
    the labels: every declared invariant must be blamed, and NOTHING ELSE may be. A
    mutant that trips five assertions when it should trip one is too blunt to be
    evidence about any of them.
    """
    global bad
    wanted = {expect} if isinstance(expect, str) else set(expect)
    with tempfile.TemporaryDirectory() as td:
        pins = pathlib.Path(td) / "pins"
        pins.mkdir()
        for p in PINS.glob("*.json"):
            (pins / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        target = pins / (LIVE + ".json")
        rec = json.loads(target.read_text(encoding="utf-8"))
        fn(rec)
        target.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rc, out = run(script, pins)
    if rc != 1:
        print(f"  FAIL  {name}: expected exit 1, got {rc} — {why}")
        bad += 1
        return

    blamed = observed_attribution(out)
    matched, unexplained = set(), []
    for label in blamed:
        hit = next((w for w in wanted if w in label), None)
        if hit:
            matched.add(hit)
        else:
            unexplained.append(label)

    missing = wanted - matched
    if missing:
        print(f"  FAIL  {name}: declared {sorted(wanted)} but never blamed {sorted(missing)}")
        bad += 1
        return
    if unexplained:
        print(f"  FAIL  {name}: blamed invariants it was not declared to violate — "
              f"{unexplained[:3]}")
        bad += 1
        return
    print(f"  ok    {name} → attribution matches ({why})")


def main() -> int:
    global bad
    if not SELECTS.exists() or not SERVED.exists() or not PINS.is_dir():
        print("UNVERIFIABLE — checks or pins missing", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print("do the two operational gates go red when a record starts lying?\n")

    print("baseline\n")
    for label, s in (("selects", SELECTS), ("served bytes", SERVED)):
        rc, _ = run(s, PINS)
        print(f"  {'ok  ' if rc == 0 else 'FAIL'}  {label}: the unmutated records pass (exit {rc})")
        bad += rc != 0

    print("\n`selects` must resolve to something that exists\n")

    def set_sel(k, v):
        def f(rec):
            rec["selects"][k] = v
        return f

    mutate(set_sel("commit", "0" * 40), SELECTS, "commit that does not exist",
           "currency derived against a commit that is not a thing", "`selects.commit` resolves")
    mutate(set_sel("artifact", "ui/never-existed.html"), SELECTS, "artifact missing at the commit",
           "the record names a file that was not in that tree",
           "`selects.artifact` exists at that commit")
    mutate(set_sel("artifact", "ui"), SELECTS, "artifact is a directory",
           "a tree is not an artifact", "`selects.artifact` is a file at that commit")
    mutate(set_sel("commit", "not-a-sha"), SELECTS, "commit is not a full sha",
           "a short or malformed ref cannot pin anything", "`selects.commit` is a full sha")
    mutate(lambda rec: rec.pop("selects"), SELECTS, "selects removed from a non-legacy record",
           "the field vanishes and the record is not on the enumerated legacy list",
           "has `selects`")

    print("\nthe serving record must be structured, honest, and client-aware\n")

    def serving(fn):
        def f(rec):
            fn(rec["availability"]["serving"])
        return f

    def first_obs(s):
        return next(iter(s["gateways"].values()))[0]

    mutate(lambda r: r["availability"].pop("serving"), SERVED, "no serving comparison at all",
           "a published record that never compared what is served",
           "carries availability.serving")
    mutate(serving(lambda s: s.pop("object")), SERVED, "no stated authority",
           "a comparison with nothing to compare against",
           "names what the bytes were compared against")
    # A_i is NOT a singleton here, and declaring that is the point: with no structured
    # observations anywhere, it is also true that no client was found to receive the pinned
    # bytes. Both invariants really are violated, so both are declared — loosening the check
    # to "contains" instead would hide the day a mutant starts tripping something it should
    # not.
    mutate(serving(lambda s: s.update(gateways={"https://x/y": {"verdict": "IDENTICAL"}})),
           SERVED, "gateway is a bare verdict, not observations",
           "one verdict per gateway hides which client asked",
           {"carries observations", "at least one client somewhere gets the pinned bytes exactly"})
    mutate(serving(lambda s: s.update(gateways={})), SERVED, "no gateways listed at all",
           "an availability block that compared nothing still looks present",
           "lists at least one gateway")
    mutate(serving(lambda s: s["gateways"].update(
               {next(iter(s["gateways"])): ["a bare string, not an observation"]})),
           SERVED, "observation is a bare string",
           "an unstructured entry carries no client and no verdict, and must not pass as one",
           "observation is structured")
    mutate(serving(lambda s: first_obs(s).pop("as")), SERVED, "observation with no client",
           "ipfs.io answers curl and a browser differently — a verdict without a client is "
           "whichever client the checker happened to use",
           "observation names the client it was made as")
    mutate(serving(lambda s: first_obs(s).update(verdict="FINE")), SERVED,
           "verdict outside the closed set", "a vocabulary that grows is a vocabulary that lies",
           "verdict in ")
    # Every observation becomes a detail-less injection, so no observation is IDENTICAL
    # either — the second invariant follows from the mutation and is declared, not tolerated.
    mutate(serving(lambda s: [o.update(verdict="SERVE_TIME_INJECTION") or o.pop("detail", None)
                              for gw in s["gateways"].values() for o in gw]),
           SERVED, "injection with no detail",
           "'not identical' with no cause reads as unexplained tampering",
           {"non-identical says why", "at least one client somewhere gets the pinned bytes exactly"})
    mutate(serving(lambda s: first_obs(s).update(verdict="DIFFERS", detail="shrug")), SERVED,
           "DIFFERS normalised into the record",
           "a substitution must never be filed as an operational note",
           "is not a recorded substitution")
    mutate(serving(lambda s: [o.update(verdict="SERVE_TIME_INJECTION", detail="d")
                              for gw in s["gateways"].values() for o in gw]),
           SERVED, "no client anywhere gets the pinned bytes",
           "if every path is modified, the pin is not what anyone receives",
           "at least one client somewhere gets the pinned bytes exactly")

    print("\nthe classifier separates a beacon from a substitution\n")
    cases = [
        ("identical", CANON, "IDENTICAL"),
        ("hidden anchor inserted", CANON.replace(b"<body>\n", b"<body>" + ANCHOR + b"\n"),
         "SERVE_TIME_INJECTION"),
        ("one byte replaced", CANON.replace(b"pinned", b"pwned"), "DIFFERS"),
        ("visible anchor inserted",
         CANON.replace(b"<body>\n", b'<body><a href="https://evil/x">click</a>\n'), "DIFFERS"),
        ("script tag inserted",
         CANON.replace(b"<body>\n", b'<body><script src="https://evil/x.js"></script>\n'),
         "DIFFERS"),
        ("two separate insertions",
         CANON.replace(b"<body>\n", b"<body>" + ANCHOR + b"\n").replace(
             b"</body>", ANCHOR + b"</body>"), "DIFFERS"),
        ("content truncated", CANON[:20], "DIFFERS"),
        ("content appended", CANON + b"<p>extra</p>", "DIFFERS"),
        ("empty response", b"", "DIFFERS"),
    ]
    for name, served, expect in cases:
        got, detail = classify(served, CANON)
        ok = got == expect
        print(f"  {'ok  ' if ok else 'FAIL'}  {name} → {got}" + ("" if ok else f" (want {expect})"))
        bad += not ok

    print("\nthe attribution layer is not decorative\n")
    # Pavlo Tvardovskyi's negative control, 2026-08-15: "deliberately swap or corrupt
    # attribution IDs while leaving the underlying predicates unchanged. If the harness
    # still passes, the attribution layer is decorative."
    #
    # The predicates below are untouched — every assertion still evaluates exactly the same
    # condition on exactly the same data, and the gate still goes red in exactly the same
    # places. ONLY THE LABELS MOVE. A harness that reads "did it go red" survives this. A
    # harness that reads "did it blame the right invariant" cannot.
    for label, (frm, to) in {
        # Corrupt the label on the branch the probe's mutant ACTUALLY reaches (line 191,
        # the failing chk — not its passing twin on 194). An earlier version of this control
        # patched the passing branch and the harness sailed through, which made the control
        # itself decorative: it was checking a label no mutant in it ever caused to be
        # printed.
        "the blamed label is corrupted": (
            'chk(f"{short}: carries availability.serving", False,',
            'chk(f"{short}: carries something else entirely", False,'),
        "the blamed label is swapped with another real one": (
            'chk(f"{short}: carries availability.serving", False,',
            'chk(f"{short}: lists at least one gateway", False,'),
    }.items():
        src = SERVED.read_text(encoding="utf-8")
        if frm not in src:
            print(f"  FAIL  {label}: anchor not found — the control patched nothing")
            bad += 1
            continue
        backup = src
        try:
            SERVED.write_text(src.replace(frm, to, 1), encoding="utf-8")
            before = bad
            # The probe is SUPPOSED to fail. Printing its failure would put a red FAIL line
            # in a passing run, which is how output stops being read.
            with contextlib.redirect_stdout(io.StringIO()):
                mutate(lambda r: r["availability"].pop("serving"), SERVED,
                       "probe", "predicates unchanged, attribution moved",
                       "carries availability.serving")
            caught = bad > before
            bad = before          # the probe's own failure is the expected outcome
        finally:
            SERVED.write_text(backup, encoding="utf-8")
        print(f"  {'ok  ' if caught else 'FAIL'}  {label}: "
              f"{'harness refuses it' if caught else 'HARNESS PASSED — attribution is decorative'}")
        if not caught:
            bad += 1

    print("\ncould-not-check is never a pass\n")
    with tempfile.TemporaryDirectory() as td:
        empty = pathlib.Path(td) / "pins"
        empty.mkdir()
        for label, s in (("selects", SELECTS), ("served bytes", SERVED)):
            rc, _ = run(s, empty)
            print(f"  {'ok  ' if rc == 2 else 'FAIL'}  {label}: no records at all is "
                  f"UNVERIFIABLE (exit {rc})")
            bad += rc != 2

    print()
    if bad:
        print(f"{bad} case(s) failed — the gates do not catch what they claim to")
        return EXIT_BAD
    print("both gates go red on the assertion that names the defect, and the classifier "
          "refuses to launder a substitution")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
