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
import os
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

    print("\nTHE LIVE TIER — no longer exempt from being made to fail\n")
    # Four assertions used to live behind a network and a local ipfs node, so no control
    # could mutate an input and watch them bite. "It needs the network" is the same shape of
    # excuse as "the rule is written down", so the gates now accept a DATA-ONLY stub
    # (CRC_LIVE_STUB) that replaces the responses and nothing else. The gate still runs as
    # its own process and still prints its own failure list, so exit code and attribution
    # remain observations of the gate.
    #
    # The stub is built from git and the pin record — no network here either, so this runs
    # in CI exactly as it runs locally.
    import base64
    import subprocess as sp

    def _b64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    def baseline_stub() -> dict:
        rec = json.loads((PINS / (LIVE + ".json")).read_text(encoding="utf-8"))
        sel = rec["selects"]
        built = sp.run(["git", "-C", str(ROOT), "show", f"{sel['commit']}:{sel['artifact']}"],
                       capture_output=True).stdout
        stamped = built.replace(b"__CONSOLE_SOURCE_COMMIT__", sel["commit"].encode())
        installs = rec.get("installs_to") or "console/index.html"
        serving = rec["availability"]["serving"]
        anchor = (b'<a href="https://ipfs.io/cdn-cgi/content?id=x" aria-hidden="true" '
                  b'rel="nofollow noopener" style="display: none !important"></a>')
        gateways = {}
        for url, obs in serving["gateways"].items():
            for o in obs:
                served = stamped
                if o["verdict"] == "SERVE_TIME_INJECTION":
                    served = stamped.replace(b"<body>", b"<body>" + anchor, 1)
                gateways[f"{url}|{o['as']}"] = _b64(served)
        # EVERY record with `selects` must be present, not just the live one: the gate
        # checks them all, and a record missing from the stub is could-not-check — which
        # is exit 2, correctly, and would make every mutant below prove nothing.
        published = {}
        for f in sorted(PINS.glob("*.json")):
            r = json.loads(f.read_text(encoding="utf-8"))
            s = r.get("selects")
            if not s:
                continue
            b = sp.run(["git", "-C", str(ROOT), "show", f"{s['commit']}:{s['artifact']}"],
                       capture_output=True).stdout
            published[f"{f.stem}/{r.get('installs_to') or 'console/index.html'}"] = _b64(
                b.replace(b"__CONSOLE_SOURCE_COMMIT__", s["commit"].encode()))
        return {
            "live_contenthash": LIVE,
            "published": published,
            "canonical": {f"{LIVE}/{serving['object'].split('/', 1)[1]}": _b64(stamped)},
            "gateways": gateways,
        }

    def live_mutate(name, why, expect, edit_stub=None, edit_source=None, script=SERVED):
        global bad
        stub = baseline_stub()
        if edit_stub:
            edit_stub(stub)
        with tempfile.TemporaryDirectory() as td:
            sf = pathlib.Path(td) / "stub.json"
            sf.write_text(json.dumps(stub), encoding="utf-8")
            backup = script.read_text(encoding="utf-8") if edit_source else None
            try:
                if edit_source:
                    patched = edit_source(backup)
                    if patched == backup:
                        print(f"  FAIL  {name}: source mutation patched NOTHING")
                        bad += 1
                        return
                    script.write_text(patched, encoding="utf-8")
                r = sp.run([sys.executable, str(script), "--live"], capture_output=True,
                           text=True, env={**os.environ, "CRC_LIVE_STUB": str(sf)})
            finally:
                if backup is not None:
                    script.write_text(backup, encoding="utf-8")
        wanted = {expect} if isinstance(expect, str) else set(expect)
        blamed = observed_attribution(r.stdout + r.stderr)
        missing = {w for w in wanted if not any(w in b for b in blamed)}
        if r.returncode != 1 or missing:
            print(f"  FAIL  {name}: exit {r.returncode}, blamed {blamed[:2]} — {why}")
            bad += 1
            return
        print(f"  ok    {name} → attribution matches ({why})")

    # 0. the stub must be FAITHFUL, or every mutant below proves nothing
    stub0 = baseline_stub()
    with tempfile.TemporaryDirectory() as td:
        sf = pathlib.Path(td) / "stub.json"
        sf.write_text(json.dumps(stub0), encoding="utf-8")
        r0 = sp.run([sys.executable, str(SERVED), "--live"], capture_output=True, text=True,
                    env={**os.environ, "CRC_LIVE_STUB": str(sf)})
        r1 = sp.run([sys.executable, str(SELECTS), "--live"], capture_output=True, text=True,
                    env={**os.environ, "CRC_LIVE_STUB": str(sf)})
    ok0 = r0.returncode == 0 and r1.returncode == 0
    print(f"  {'ok  ' if ok0 else 'FAIL'}  the unmutated stub passes BOTH gates "
          f"(served {r0.returncode}, selects {r1.returncode})")
    if not ok0:
        bad += 1

    live_mutate("the live contenthash has no pin record",
                "a CID is published that nothing in pins/ describes",
                "the live contenthash has a pin record",
                edit_stub=lambda s: s.update(live_contenthash="bafybeiaaaaaaaaaaaaaaaaaaaa"
                                                              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))

    live_mutate("a gateway contradicts the record",
                "the record says SERVE_TIME_INJECTION and the web says IDENTICAL",
                "the web says",
                edit_stub=lambda s: s["gateways"].update(
                    {k: s["canonical"][next(iter(s["canonical"]))]
                     for k in s["gateways"] if "curl" in k}))

    live_mutate("the namehash constant is wrong",
                "a mistyped node reads a different name's contenthash and says nothing",
                "IS namehash",
                edit_source=lambda src: src.replace(
                    'ENS_NODE = "0x10fa3d22', 'ENS_NODE = "0x20fa3d22', 1))

    live_mutate("the published artifact is not the stamped build",
                "the CID serves bytes that are not what that commit builds",
                "is the stamped build of",
                edit_stub=lambda s: s["published"].update(
                    {k: _b64(base64.b64decode(v).replace(b"<body>", b"<body><!--x-->", 1))
                     for k, v in s["published"].items()}),
                script=SELECTS)

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

    print("\nCAUSALITY — repair one invariant, its attribution must disappear\n")
    # Pavlo Tvardovskyi, 2026-08-15, on breaking the closed loop in which the same person
    # writes the mutant and declares its expected attribution set:
    #
    #   "after m_i produces attribution A_i, apply a targeted repair r_k intended to
    #    restore ONE invariant while leaving the rest of the mutant intact. The
    #    corresponding attribution should disappear while unrelated attributions remain.
    #    That tests causality, not just label agreement."
    #
    # This is the half of his spec reachable without a second author. Set equality proves
    # internal consistency; a repair proves the mapping is CAUSAL. A wrongly-declared A_i
    # tends to survive equality and die here — repairing the invariant I claimed was
    # violated would not remove the attribution I claimed it caused.
    #
    # It does NOT close the loop. A_i is still authored by whoever writes the mutant, and
    # only an oracle derived independently of this gate's output can fix that.
    def counterfactual(mutant, repair, script, name, must_remain) -> None:
        global bad
        with tempfile.TemporaryDirectory() as td:
            pins = pathlib.Path(td) / "pins"
            pins.mkdir()
            for f in PINS.glob("*.json"):
                (pins / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            target = pins / (LIVE + ".json")
            rec = json.loads(target.read_text(encoding="utf-8"))
            mutant(rec)
            repair(rec)
            target.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
            _, out = run(script, pins)
        blamed = observed_attribution(out)
        vanished = {w for w in must_remain if not any(w in b for b in blamed)}
        survived = [b for b in blamed if not any(w in b for w in must_remain)]
        ok = not vanished and not survived
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
        if not ok:
            bad += 1
            if vanished:
                print(f"           should have REMAINED but vanished: {sorted(vanished)}")
            if survived:
                print(f"           should have been REPAIRED but remains: {survived[:3]}")

    def inject_all(rec):
        for gw in rec["availability"]["serving"]["gateways"].values():
            for o in gw:
                o["verdict"] = "SERVE_TIME_INJECTION"
                o.pop("detail", None)

    def restore_one_identical(rec):
        first = next(iter(rec["availability"]["serving"]["gateways"].values()))[0]
        first["verdict"] = "IDENTICAL"
        first.pop("detail", None)

    def detail_every_injection(rec):
        for gw in rec["availability"]["serving"]["gateways"].values():
            for o in gw:
                if o.get("verdict") != "IDENTICAL":
                    o["detail"] = "a stated cause"

    # inject_all violates BOTH invariants. Each repair should clear exactly one.
    counterfactual(inject_all, restore_one_identical, SERVED,
                   "restore one IDENTICAL -> only the pinned-bytes attribution clears",
                   {"non-identical says why"})
    counterfactual(inject_all, detail_every_injection, SERVED,
                   "supply the missing details -> only the says-why attribution clears",
                   {"at least one client somewhere gets the pinned bytes exactly"})

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
