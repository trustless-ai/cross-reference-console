#!/usr/bin/env python3
"""The live read, driven over every path with the transport stubbed.

The read is the last piece and the one with a network in it, so its failure modes are exactly
the ones nobody exercises by accident. Transport is injected in ui/currency-read.js precisely so
they can be driven here: silent resolver, resolver returning nothing, record missing, record
malformed, unstamped build, and the two established comparisons.

WHAT THIS ASSERTS BEYOND THE MAPPING:

  * PENDING is emitted BEFORE the wait, every time. "Not asked" and "asked, waiting" are
    different facts, and a surface that sits on NOT_RUN during a request is telling a reader
    the check has not started when it has.
  * No path returns a verdict that was not established. Six of the eight vectors here are
    failures, and not one of them may carry CURRENT or STALE.
  * A throw is a state, not a crash. Both transports can reject; each maps to the reason for
    the side that went dark, never to a generic one.

EXIT: 0 · 1 determinate · 2 could not check.
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


READ = _arg("--read", ROOT / "ui" / "currency-read.js")
GOLDEN = _arg("--golden", ROOT / "reference" / "vectors" / "currency-read.golden.json")
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
fails: list[str] = []

SC = "f3e9a670de440442132a1440a568c955f595c550"
OTHER = "0" * 40


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


HARNESS = r"""
const path = process.argv[2];
const { readCurrency, decodeContenthash } = require(path);
const SC = process.argv[3], OTHER = process.argv[4];
const rec = (c) => ({ selects: { commit: c, repo: 'r', artifact: 'ui/index.html' } });

const cases = {
  resolver_throws:      { resolveCid: () => Promise.reject(new Error('offline')), fetchPinRecord: () => null, sourceCommit: SC },
  resolver_null:        { resolveCid: () => null,                                  fetchPinRecord: () => null, sourceCommit: SC },
  resolver_empty:       { resolveCid: () => '',                                    fetchPinRecord: () => null, sourceCommit: SC },
  record_missing:       { resolveCid: () => 'bafyCID',  fetchPinRecord: () => null,                         sourceCommit: SC },
  record_throws:        { resolveCid: () => 'bafyCID',  fetchPinRecord: () => Promise.reject(new Error('404')), sourceCommit: SC },
  record_no_selects:    { resolveCid: () => 'bafyCID',  fetchPinRecord: () => ({ commit: 'landing' }),      sourceCommit: SC },
  unstamped_build:      { resolveCid: () => 'bafyCID',  fetchPinRecord: () => rec(SC),                      sourceCommit: '__CONSOLE_SOURCE_COMMIT__' },
  established_current:  { resolveCid: () => 'bafyCID',  fetchPinRecord: () => rec(SC),                      sourceCommit: SC },
  established_stale:    { resolveCid: () => 'bafyCID',  fetchPinRecord: () => rec(OTHER),                   sourceCommit: SC },
};

(async () => {
  const out = { results: {}, sequences: {}, decode: {} };
  for (const [name, opts] of Object.entries(cases)) {
    const seq = [];
    const final = await readCurrency({ ...opts, onState: (m) => seq.push(m.state) });
    out.results[name] = final;
    out.sequences[name] = seq;
  }
  // the decoder, on the real published contenthash and on things it must refuse
  out.decode.real = decodeContenthash('0xe30101701220d14cc1b3cea37a1c75f7a04a216aa9fc8947825f4d4b1072c752a0e75afd2176');
  out.decode.garbage = decodeContenthash('0xdeadbeef');
  out.decode.empty = decodeContenthash('');
  out.decode.nonstring = decodeContenthash(null);
  process.stdout.write(JSON.stringify(out));
})();
"""


def render() -> dict | None:
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as td:
        h = pathlib.Path(td) / "h.cjs"
        h.write_text(HARNESS, encoding="utf-8")
        try:
            r = subprocess.run([node, str(h), str(READ.resolve()), SC, OTHER],
                               capture_output=True, text=True, timeout=120)
        except subprocess.SubprocessError:
            return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    if not READ.exists():
        print(f"UNVERIFIABLE — read module not found at {READ}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    got = render()
    if got is None:
        print("UNVERIFIABLE — could not execute the read module.", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    if "--write-golden" in sys.argv:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({
            "note": "The live read, driven with transport stubbed. Every failure path is here because "
                    "a network read whose failures need a cable unplugged is a read nobody tests.",
            "source": "ui/currency-read.js", **got}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}")
        return EXIT_OK
    if not GOLDEN.exists():
        print(f"UNVERIFIABLE — golden not found at {GOLDEN}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    print("the live read — every path, transport stubbed\n")
    res = got["results"]

    print("each path renders exactly what the golden records\n")
    for name in res:
        chk(f"{name}", json.dumps(res[name], sort_keys=True) ==
            json.dumps(golden.get("results", {}).get(name), sort_keys=True),
            json.dumps(res[name])[:120])

    print("\nPENDING is emitted before the wait, on every path\n")
    for name, seq in got["sequences"].items():
        chk(f"{name}: starts PENDING", seq and seq[0] == "PENDING", str(seq))
        chk(f"{name}: settles once", len(seq) == 2, str(seq))

    print("\nno path returns a verdict it did not establish\n")
    failures = ["resolver_throws", "resolver_null", "resolver_empty", "record_missing",
                "record_throws", "record_no_selects", "unstamped_build"]
    for name in failures:
        chk(f"{name}: no verdict", res[name]["verdict"] is None, json.dumps(res[name])[:110])
        chk(f"{name}: carries a reason", isinstance(res[name].get("reason"), str) and res[name]["reason"])
        chk(f"{name}: is neither green nor red", res[name]["tone"] not in ("green", "red"), res[name]["tone"])

    print("\nthe reason names the side that went dark\n")
    for name in ("resolver_throws", "resolver_null", "resolver_empty"):
        chk(f"{name} → resolver_unreachable", res[name]["reason"] == "resolver_unreachable", res[name]["reason"])
    for name in ("record_missing", "record_throws", "record_no_selects"):
        chk(f"{name} → lock_unreadable", res[name]["reason"] == "lock_unreadable", res[name]["reason"])
    chk("unstamped_build → artifact_unstamped", res["unstamped_build"]["reason"] == "artifact_unstamped")

    print("\nonly the two established comparisons produce a verdict\n")
    chk("established_current → CURRENT", res["established_current"]["verdict"] == "CURRENT")
    chk("established_stale → STALE", res["established_stale"]["verdict"] == "STALE")
    chk("exactly two of nine paths reach CHECKED",
        sum(1 for v in res.values() if v["state"] == "CHECKED") == 2)

    print("\nthe contenthash decoder\n")
    chk("decodes the real published contenthash",
        got["decode"]["real"] == "bafybeigrjta3htvdpiohl55ajiqwvkp4rfdyex2njmihfr2sudtvv7jboy",
        str(got["decode"]["real"]))
    for bad in ("garbage", "empty", "nonstring"):
        chk(f"refuses {bad} rather than inventing a CID", got["decode"][bad] is None, str(got["decode"][bad]))

    print()
    if fails:
        print(f"{len(fails)} assertion(s) failed:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("the read establishes a verdict twice, and says why the other seven times")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
