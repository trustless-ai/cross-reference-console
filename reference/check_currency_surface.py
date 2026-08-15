#!/usr/bin/env python3
"""The currency surface: the network-backed path, driven through the bytes the page ships.

@boardyai's repin precondition, 15 August 2026: "repin only after the live-surface vectors
cover the network-backed path, including resolver failure, stale data, and the page's rendered
reason."

WHY THIS IS NOT check_currency_read.py AGAIN. That check drives ui/currency-read.js and proves
the READ is right. It says nothing about what a human sees, and the console has already shipped
a correct internal verdict with no marker on the surface — the defect that produced the Boardy
rule in the first place. So this check does three things the read check cannot:

  1. It extracts the INLINED regions out of ui/index.html and runs those. Not the source files
     beside it — the concatenated bytes the published page executes. If embed_snapshot.py ever
     inlines a stale copy, the tested function and the shipped function diverge and this goes
     red rather than staying quietly green on a file nobody serves.
  2. It runs them as an ES module, so `require` and `module` are undefined and the UMD wrappers
     take the SAME branch the browser takes. The CommonJS branch is not the shipped branch.
  3. It asserts the rendered text, the tone and the reason attribute — the state a reader
     actually receives — including that the final render is byte-identical to the marker's own
     text, which is what "passes the result unchanged through the existing projection" means
     mechanically rather than as an intention.

EXIT: 0 · 1 determinate · 2 could not check.
"""

from __future__ import annotations

import json
import pathlib
import re
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


INDEX = _arg("--index", ROOT / "ui" / "index.html")
GOLDEN = _arg("--golden", ROOT / "reference" / "vectors" / "currency-surface.golden.json")
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
fails: list[str] = []

REGIONS = ["currency-marker.js", "currency-read.js", "currency-surface.js"]
SC = "f3e9a670de440442132a1440a568c955f595c550"
OTHER = "0" * 40

# The vocabulary the SURFACE must not contain. NOT_RUN is deliberately absent from this list:
# the initial state was specified by review rather than derived from a read, so the surface
# names it. Every other state, verdict and reason belongs to currency-marker.js alone — a
# second copy of any of them is the second mapping the wiring constraint forbids.
FORBIDDEN_IN_SURFACE = ["CURRENT", "STALE", "CHECKED", "COULD_NOT_CHECK",
                        "resolver_unreachable", "no_local_ipfs", "lock_unreadable",
                        "artifact_unstamped"]


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


HARNESS = r"""
/* A DOM node reduced to what the surface actually touches, and recording every complete
   render in order. Anything the surface reached for beyond these two would throw here, which
   is the point: the fake is the contract.

   Snapshots are taken on data-reason because renderCurrency writes it last, so each entry in
   `renders` is one whole render rather than a half-applied one. That ordering is what makes
   "NOT_RUN, then PENDING, then an answer" an assertion instead of a hope. */
function el() {
  const o = { attrs: {}, renders: [], _text: '' };
  Object.defineProperty(o, 'textContent', {
    get: function () { return this._text; },
    set: function (v) { this._text = v; }
  });
  o.setAttribute = function (k, v) {
    this.attrs[k] = v;
    if (k === 'data-reason') {
      this.renders.push({ text: this._text, tone: this.attrs['data-tone'],
                          state: this.attrs['data-state'], reason: v });
    }
  };
  return o;
}
const rec = (c) => ({ selects: { commit: c, repo: 'r', artifact: 'ui/index.html' } });
const SC = process.argv[2], OTHER = process.argv[3];

const cases = {
  resolver_offline:  { resolveCid: () => Promise.reject(new Error('offline')), fetchPinRecord: () => null, sourceCommit: SC },
  resolver_silent:   { resolveCid: () => null,                                 fetchPinRecord: () => null, sourceCommit: SC },
  record_missing:    { resolveCid: () => 'bafyCID', fetchPinRecord: () => null,               sourceCommit: SC },
  record_no_selects: { resolveCid: () => 'bafyCID', fetchPinRecord: () => ({ commit: 'x' }),  sourceCommit: SC },
  unstamped_build:   { resolveCid: () => 'bafyCID', fetchPinRecord: () => rec(SC),            sourceCommit: '__CONSOLE_SOURCE_COMMIT__' },
  published_stale:   { resolveCid: () => 'bafyCID', fetchPinRecord: () => rec(OTHER),         sourceCommit: SC },
  published_current: { resolveCid: () => 'bafyCID', fetchPinRecord: () => rec(SC),            sourceCommit: SC },
};

const out = { surface: {}, sequences: {}, unchanged: {}, malformed: {} };

for (const [name, read] of Object.entries(cases)) {
  /* One node per case, written to repeatedly exactly as the page's single element is. */
  const node = el();
  const finalMarker = await globalThis.currencySurface.mountCurrency({ element: node, read: read });
  const final = node.renders[node.renders.length - 1];
  out.surface[name] = final;
  out.sequences[name] = node.renders;
  /* "Passed unchanged" is not an intention, it is an equality. */
  out.unchanged[name] = (final.text === finalMarker.text)
    && (final.tone === finalMarker.tone)
    && (final.state === String(finalMarker.state))
    && (final.reason === (finalMarker.reason ? String(finalMarker.reason) : ''));
}

/* The initial state, isolated: render NOT_RUN alone, exactly as mountCurrency does first. */
{
  const node = el();
  globalThis.currencySurface.renderCurrency(globalThis.currencyMarker('NOT_RUN'), node);
  out.initial = node.renders[0];
}
{
  const node = el();
  globalThis.currencySurface.renderCurrency(globalThis.currencyMarker('PENDING'), node);
  out.pending = node.renders[0];
}

/* A malformed marker must produce a loud defect, never an empty node. An empty node is how
   this class of bug ships: absence of a caveat reads as the strongest claim on the page. */
for (const [k, bad] of Object.entries({
  nothing: null,
  unqualified: { state: 'CHECKED', verdict: 'CURRENT', text: 'CURRENT — trust me', tone: 'green' },
  textless: { state: 'CHECKED', verdict: 'CURRENT', tone: 'green', qualified: true },
})) {
  const node = el();
  const r = globalThis.currencySurface.renderCurrency(bad, node);
  out.malformed[k] = Object.assign({}, node.renders[0], { wellFormed: r.wellFormed });
}

process.stdout.write(JSON.stringify(out));
"""


def extract_regions(html: str) -> str | None:
    """Pull the inlined regions out of the published page, in page order."""
    parts = []
    for name in REGIONS:
        m = re.search(r"/\* BEGIN " + re.escape(name) + r"[\s\S]*?\*/\n([\s\S]*?)/\* END "
                      + re.escape(name) + r" \*/", html)
        if not m or not m.group(1).strip():
            return None
        parts.append(m.group(1))
    return "\n".join(parts)


def render(inlined: str) -> dict | None:
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as td:
        # .mjs, so `require` and `module` are undefined and the UMD wrappers take the browser
        # branch. Running the CommonJS branch here would test a path the page never executes.
        mod = pathlib.Path(td) / "page.mjs"
        mod.write_text(inlined + "\n" + HARNESS, encoding="utf-8")
        try:
            r = subprocess.run([node, str(mod), SC, OTHER],
                               capture_output=True, text=True, timeout=120)
        except subprocess.SubprocessError:
            return None
    if r.returncode != 0 or not r.stdout.strip():
        if r.stderr.strip():
            print("      node: " + r.stderr.strip().splitlines()[-1], file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def canon(o) -> str:
    return json.dumps(o, sort_keys=True)


def main() -> int:
    if not INDEX.exists():
        print(f"UNVERIFIABLE — {INDEX} does not exist", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    html = INDEX.read_text(encoding="utf-8")
    inlined = extract_regions(html)
    if inlined is None:
        print("UNVERIFIABLE — the page does not carry all three currency regions.", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    got = render(inlined)
    if got is None:
        print("UNVERIFIABLE — could not execute the page's inlined currency code.", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    if "--write-golden" in sys.argv:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({
            "note": "What a reader SEES for each network-backed path, produced by the code inlined "
                    "in ui/index.html. A lost qualifier reads as a diff here, not as silence.",
            "source": "ui/index.html (inlined currency-marker.js + currency-read.js + currency-surface.js)",
            **got}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {GOLDEN}")
        return EXIT_OK
    if not GOLDEN.exists():
        print(f"UNVERIFIABLE — golden not found at {GOLDEN}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))

    surf = got["surface"]
    print("the currency surface — the network-backed path, as the page renders it\n")

    print("each path renders exactly the text the golden pins\n")
    for name in surf:
        chk(name, canon(surf[name]) == canon(golden.get("surface", {}).get(name)),
            canon(surf[name])[:130])

    print("\nthe initial state is NOT_RUN, and it is not a pass\n")
    chk("initial render is NOT_RUN", got["initial"]["state"] == "NOT_RUN", canon(got["initial"]))
    chk("initial render is not green", got["initial"]["tone"] != "green", got["initial"]["tone"])
    chk("initial render carries no verdict",
        "CURRENT" not in got["initial"]["text"] and "STALE" not in got["initial"]["text"])
    chk("initial render says currency was not established", "not checked" in got["initial"]["text"])
    chk("PENDING is not green", got["pending"]["tone"] != "green")
    chk("PENDING says it is not a pass", "not a pass" in got["pending"]["text"])

    print("\nevery path renders NOT_RUN, then PENDING, then an answer — in that order\n")
    for name, seq in got["sequences"].items():
        chk(f"{name}: opens on NOT_RUN", len(seq) >= 3 and seq[0]["state"] == "NOT_RUN",
            canon([s["state"] for s in seq]))
        chk(f"{name}: renders PENDING before the wait", len(seq) >= 2 and seq[1]["state"] == "PENDING",
            canon([s["state"] for s in seq]))
        chk(f"{name}: settles exactly once", len(seq) == 3, canon([s["state"] for s in seq]))
        chk(f"{name}: renders no verdict before the read settles",
            all("CURRENT" not in s["text"] and "STALE" not in s["text"] for s in seq[:2]))

    print("\nthe marker reaches the DOM unchanged — no second mapping\n")
    for name, ok in got["unchanged"].items():
        chk(f"{name}: rendered text, tone, state and reason are the marker's own", ok,
            canon(surf[name])[:110])

    print("\nresolver failure and unreadable lock render their own reason\n")
    for name, reason in (("resolver_offline", "resolver_unreachable"),
                         ("resolver_silent", "resolver_unreachable"),
                         ("record_missing", "lock_unreadable"),
                         ("record_no_selects", "lock_unreadable"),
                         ("unstamped_build", "artifact_unstamped")):
        chk(f"{name} → data-reason={reason}", surf[name]["reason"] == reason, surf[name]["reason"])
        chk(f"{name}: renders no verdict",
            "CURRENT" not in surf[name]["text"] and "STALE" not in surf[name]["text"],
            surf[name]["text"][:90])
        chk(f"{name}: is neither green nor red", surf[name]["tone"] not in ("green", "red"),
            surf[name]["tone"])
        chk(f"{name}: says why in the text a reader sees",
            surf[name]["text"].startswith("could not check — could not"), surf[name]["text"][:90])

    print("\nthe three failures do not collapse into one amber\n")
    texts = {surf[n]["text"] for n in ("resolver_offline", "record_missing", "unstamped_build")}
    chk("resolver / lock / unstamped read as three different sentences", len(texts) == 3,
        f"{len(texts)} distinct")

    print("\nstale data renders as STALE, and only an established comparison does\n")
    chk("published_stale renders STALE", surf["published_stale"]["state"] == "CHECKED"
        and "STALE" in surf["published_stale"]["text"], canon(surf["published_stale"])[:110])
    chk("published_stale is red, not amber", surf["published_stale"]["tone"] == "red")
    chk("published_stale carries no reason", surf["published_stale"]["reason"] == "")
    chk("published_current renders CURRENT", "CURRENT" in surf["published_current"]["text"])
    chk("exactly one path renders green",
        sum(1 for v in surf.values() if v["tone"] == "green") == 1)
    chk("exactly two paths reach CHECKED",
        sum(1 for v in surf.values() if v["state"] == "CHECKED") == 2)

    print("\na malformed marker renders a defect, never an empty node\n")
    for k in ("nothing", "unqualified", "textless"):
        m = got["malformed"][k]
        chk(f"{k}: refuses it", m["wellFormed"] is False, canon(m)[:110])
        chk(f"{k}: writes a loud sentence rather than nothing",
            m["text"].startswith("could not render"), m["text"][:70])
        chk(f"{k}: is not green", m["tone"] != "green", m["tone"])
        chk(f"{k}: claims no state", m["state"] == "", m["state"])

    print("\nthe surface owns no vocabulary\n")
    region = extract_regions(html)
    surface_src = re.search(r"/\* BEGIN currency-surface\.js[\s\S]*?\*/\n([\s\S]*?)/\* END "
                            r"currency-surface\.js \*/", html).group(1)
    # Comments are stripped first: the file's own header explains what a second mapping WOULD
    # look like, and naming the states in prose is the opposite of owning them. The stripper
    # only handles /* */, so assert it was sufficient rather than assuming it — a `//` comment
    # would carry vocabulary straight past this scan.
    code = re.sub(r"/\*[\s\S]*?\*/", "", surface_src)
    chk("the surface uses only /* */ comments, so the stripper below is complete",
        "//" not in code, "a // comment would slip vocabulary past this scan")
    for word in FORBIDDEN_IN_SURFACE:
        chk(f"the shipped surface's CODE does not contain \"{word}\"", word not in code)
    chk("the shipped surface does name NOT_RUN (the specified initial state)",
        "NOT_RUN" in code)
    chk("the inlined region is byte-identical to ui/currency-surface.js",
        surface_src.strip() == (ROOT / "ui" / "currency-surface.js").read_text(
            encoding="utf-8").strip())

    print("\nthe page wires it, and its no-JS fallback claims nothing\n")
    chk("index.html mounts the surface", "currencySurface.mountCurrency(" in html)
    chk("it mounts onto an element that exists", 'id="prov-currency"' in html)
    chk("it passes the page's own commit",
        re.search(r"sourceCommit:\s*CONSOLE_SOURCE_COMMIT", html) is not None)
    chk("the resolver is read from the contract, not an ENS API",
        "eth_call" in region and "ensdata" not in html and "ens.domains" not in html)
    fallback = re.search(r'id="prov-currency"[^>]*>([^<]*)<', html)
    chk("a no-JS reader is told nothing was checked",
        fallback is not None and "not checked" in fallback.group(1))
    chk("the no-JS fallback carries no verdict",
        fallback is not None and "CURRENT" not in fallback.group(1)
        and "STALE" not in fallback.group(1))

    print()
    if fails:
        print(f"{len(fails)} assertion(s) failed:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("the page renders a currency verdict twice, says why five times, and never silently")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
