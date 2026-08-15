#!/usr/bin/env python3
"""What a gateway SERVES is not what was pinned, and the difference must be classified.

On 15 August the console's published page hashed differently on two gateways. eth.limo served
the pinned bytes exactly; ipfs.io served them with a hidden `<a href=…/cdn-cgi/content?id=…>`
injected after `<body>`. One wrong hash, two completely different findings:

    "these bytes were altered"          — an attack on a page whose whole claim is integrity
    "this CDN adds a beacon at serve"   — an operational fact about one host

Collapsing them either way is a defect. Calling injection tampering cries wolf on every ipfs.io
fetch; calling tampering injection is how a substituted page ships under the org's own domain.

@boardyai, closing the wiring thread: "keep the served-byte comparison in the availability
record." That is a discipline — someone remembering to paste a paragraph — and a discipline is
a rule with no failure mode.

TWO TIERS, SAME SPLIT AS check_selects_authoritative.py.

  Tier 1 — COVERAGE, offline, always runs, gates CI.
      Every record that names a transaction carries a STRUCTURED `availability.serving`: what
      the served bytes were compared against, and per gateway a list of observations, each
      naming the CLIENT it was made as and a verdict from a closed set. Prose is not a schema
      boundary. A verdict other than IDENTICAL must carry a detail, because "not identical"
      without a reason is the collapse this file exists to refuse.

  Tier 2 — CONTENT, `--live`, needs the network.
      Re-derive every observation, fetching as the client it names. The record becomes a
      recomputable claim rather than a remembered one.

CLASSIFICATION IS STRICT. Serve-time injection means: the served bytes are the canonical bytes
with exactly ONE contiguous insertion, and that insertion is a hidden anchor. One byte changed
anywhere else, or a second insertion, is DIFFERS. A loose classifier would launder a real
substitution into an operational footnote, which is the failure this check would be sold as
preventing.

THE VERDICT IS A FUNCTION OF WHO ASKED, AND THAT IS NOT A DETAIL. Building this check produced
the finding that motivates its shape. ipfs.io serves the SAME CID three different ways:

    curl/8.7.1                  the hidden anchor, 177569 bytes
    a browser user-agent        the pinned bytes exactly, 177277
    python-urllib's default     403 Forbidden

So "ipfs.io injects" — which is what the previous record said, and what I told Tiago — is true
of one client and false of another. A per-gateway verdict with no client attached is a collapsed
value: it hides the state that produced it, and whichever client the checker happens to use
becomes an accidental definition of what the world sees.

Every observation therefore carries the client it was made as, and --live re-derives each one
with that same client. A gateway that refuses the checker is could-not-check, never a pass.

EXIT: 0 · 1 a record's serving claim is missing, malformed, or false · 2 could not check.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2

VERDICTS = {"IDENTICAL", "SERVE_TIME_INJECTION", "DIFFERS"}

# Published before the gateway difference was noticed, so nobody compared. Enumerated by CID
# rather than dated, for the same reason check_pin_selects.py enumerates its own legacy set: a
# date rule silently absolves any future record whose clock looks old enough, while a list means
# a new record without the comparison fails until someone adds its CID here in a visible diff
# and argues for it.
#
# These are NOT retroactively excused. The claim is narrower and true: at the time they were
# published, what a gateway served was never compared with what was pinned.
LEGACY_WITHOUT_SERVING = {
    "bafybeiadnqxc5wmgtct3mjbnfoa5wpqa3fcjrwt4xoli6pivs34p2mnzxy",
    "bafybeiblwwa2wnbftf4nu3byvzprxlz5odmojawms7iv2fxdcnoscpdvya",
    "bafybeibr5uvrp5qvagipyatzv2xdrwtlwzrv4nno45abgqkirt6imhe5lm",
    "bafybeicctklscgxsitekmrdujz4hf345rg225stzpfvihdbgwvdogrh63q",
    "bafybeid4nm3b7ptrhmztyu6kzlz2vgavz4il2bezx6r5ljpvrl3yfpjhli",
    "bafybeigrjta3htvdpiohl55ajiqwvkp4rfdyex2njmihfr2sudtvv7jboy",
    "bafybeigryfhrdiuicuwnrsjdhrkid4l2it5otneqimch463mdlup6wvdg4",
}

# trustless-ai.eth. The node is namehash('trustless-ai.eth'); --live recomputes it when
# pycryptodome is present rather than trusting the constant.
ENS_NAME = "trustless-ai.eth"
ENS_NODE = "0x10fa3d22935a94b65bcfe085f719a5db6afe733511213f4f76d0bd2206b9bfb0"
RESOLVER = "0xf29100983e058b709f3d539b0c765937b804ac15"
RPC = "https://ethereum-rpc.publicnode.com"

# A single hidden anchor, which is what a CDN beacon looks like. Deliberately narrow: it must
# be an <a>, it must be hidden, and it must be the whole insertion.
INJECTED_ANCHOR = re.compile(
    rb"^<a\s[^>]*\bhref=\"https://[^\"]+\"[^>]*\bstyle=\"[^\"]*display:\s*none[^\"]*\"[^>]*>"
    rb"</a>$", re.IGNORECASE)

fails: list[str] = []
unverifiable: list[str] = []


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


def note(label: str, detail: str) -> None:
    print(f"  ..    {label} — {detail}")
    unverifiable.append(label)


def classify(served: bytes, canonical: bytes) -> tuple[str, str]:
    """IDENTICAL | SERVE_TIME_INJECTION | DIFFERS, and why."""
    if served == canonical:
        return "IDENTICAL", ""
    # Longest common prefix and suffix. Whatever sits between them in `served` is the candidate
    # insertion; the corresponding span in `canonical` must be EMPTY, or bytes were replaced
    # rather than added and this is not an insertion at all.
    n = min(len(served), len(canonical))
    p = 0
    while p < n and served[p] == canonical[p]:
        p += 1
    s = 0
    while s < n - p and served[len(served) - 1 - s] == canonical[len(canonical) - 1 - s]:
        s += 1
    removed = canonical[p:len(canonical) - s]
    inserted = served[p:len(served) - s]
    if removed:
        return "DIFFERS", (f"{len(removed)} byte(s) replaced at offset {p} — this is not an "
                           f"insertion")
    if not INJECTED_ANCHOR.match(inserted.strip()):
        return "DIFFERS", (f"{len(inserted)} byte(s) inserted at offset {p}, and the insertion "
                           f"is not a hidden anchor: {inserted[:60]!r}")
    return "SERVE_TIME_INJECTION", (f"one hidden anchor, {len(inserted)} bytes, inserted at "
                                    f"offset {p}")


def fetch(url: str, as_client: str, timeout: int = 60) -> tuple[bytes | None, str]:
    """Fetch AS a named client. What comes back depends on it, so it is never implicit."""
    try:
        req = urllib.request.Request(url, headers={"user-agent": as_client})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} as {as_client!r}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"{type(e).__name__} as {as_client!r}"


def rpc_contenthash() -> str | None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [
        {"to": RESOLVER, "data": "0xbc1c58d1" + ENS_NODE[2:]}, "latest"]}).encode()
    try:
        # The user-agent is explicit here for the same reason it is explicit everywhere else in
        # this file: this RPC returns 403 to python-urllib's default, exactly as ipfs.io does.
        # An omitted client is not a neutral client.
        req = urllib.request.Request(RPC, data=body, headers={
            "content-type": "application/json", "user-agent": "crc-check-served-bytes"})
        with urllib.request.urlopen(req, timeout=45) as r:
            res = json.loads(r.read()).get("result", "")
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    h = res[2:] if res.startswith("0x") else res
    i = h.find("e30101701220")
    if i < 0:
        return None
    raw = bytes.fromhex("01701220" + h[i + 12:i + 12 + 64])
    alpha = "abcdefghijklmnopqrstuvwxyz234567"
    bits = "".join(f"{b:08b}" for b in raw)
    bits += "0" * ((5 - len(bits) % 5) % 5)
    return "b" + "".join(alpha[int(bits[j:j + 5], 2)] for j in range(0, len(bits), 5))


def tier1(records: list[tuple[str, dict]]) -> None:
    print("tier 1 — every published record carries a structured serving comparison (offline)\n")
    published = [(c, r) for c, r in records if str(r.get("tx", "")).strip()]
    if not published:
        note("tier 1", "no record names a transaction yet")
        return
    for cid, rec in published:
        short = cid[:16] + "…"
        serving = (rec.get("availability") or {}).get("serving")
        if serving is None and cid in LEGACY_WITHOUT_SERVING:
            print(f"  ..    {short}: enumerated legacy record — nothing was compared at the time")
            continue
        if not isinstance(serving, dict):
            chk(f"{short}: carries availability.serving", False,
                "a published record with no served-byte comparison")
            continue
        chk(f"{short}: carries availability.serving", True)
        chk(f"{short}: names what the bytes were compared against",
            isinstance(serving.get("object"), str) and serving["object"].strip() != "",
            "`object` missing — a comparison with no stated authority is not a comparison")
        gws = serving.get("gateways")
        if not isinstance(gws, dict) or not gws:
            chk(f"{short}: lists at least one gateway", False, repr(gws)[:60])
            continue
        chk(f"{short}: lists at least one gateway", True)
        seen_identical = False
        for url, obs in gws.items():
            g = url.split("/")[2] if "//" in url else url
            if not isinstance(obs, list) or not obs:
                chk(f"{short}: {g} carries observations", False,
                    "a gateway with no observation is a gateway nobody looked at")
                continue
            for o in obs:
                if not isinstance(o, dict):
                    chk(f"{short}: {g} observation is structured", False, repr(o)[:60])
                    continue
                client = o.get("as")
                # The finding that shaped this file: ipfs.io serves the same CID differently to
                # curl, to a browser, and to python-urllib. A verdict with no client attached
                # would let whichever client the checker used define what "the world sees".
                chk(f"{short}: {g} observation names the client it was made as",
                    isinstance(client, str) and client.strip() != "", repr(client)[:60])
                v = o.get("verdict")
                chk(f"{short}: {g} as {str(client)[:18]!r} — verdict in {sorted(VERDICTS)}",
                    v in VERDICTS, repr(v))
                if v == "IDENTICAL":
                    seen_identical = True
                elif v in VERDICTS:
                    chk(f"{short}: {g} as {str(client)[:18]!r} — non-identical says why",
                        isinstance(o.get("detail"), str) and o["detail"].strip() != "",
                        "a difference with no stated cause reads as unexplained tampering")
                if v == "DIFFERS":
                    chk(f"{short}: {g} as {str(client)[:18]!r} — is not a recorded substitution",
                        False, "a record must never normalise DIFFERS into an operational note")
        chk(f"{short}: at least one client somewhere gets the pinned bytes exactly",
            seen_identical, "no observation found the object served unmodified")


def tier2(records: list[tuple[str, dict]]) -> None:
    print("\ntier 2 — those verdicts re-derived against the live web\n")
    try:
        from Crypto.Hash import keccak

        def k(b: bytes) -> bytes:
            h = keccak.new(digest_bits=256)
            h.update(b)
            return h.digest()

        node = b"\x00" * 32
        for label in reversed(ENS_NAME.split(".")):
            node = k(node + k(label.encode()))
        chk(f"the hard-coded node IS namehash('{ENS_NAME}')", "0x" + node.hex() == ENS_NODE,
            "0x" + node.hex())
    except ImportError:
        note("namehash", "pycryptodome absent — the node constant was not recomputed")

    live = rpc_contenthash()
    if live is None:
        note("tier 2", "could not read the contenthash from the resolver contract")
        return
    print(f"  ..    the contract currently publishes {live[:20]}…")
    match = [(c, r) for c, r in records if c == live]
    if not match:
        chk("the live contenthash has a pin record", False,
            f"{live} is published and no record in pins/ describes it")
        return
    chk("the live contenthash has a pin record", True)

    cid, rec = match[0]
    serving = (rec.get("availability") or {}).get("serving") or {}
    obj_path = str(serving.get("object", "")).split("/", 1)
    artifact = obj_path[1] if len(obj_path) == 2 else "console/index.html"

    # The authority is the CID-addressed object, fetched from a local node when there is one —
    # a gateway is exactly the thing under test and cannot also be the reference.
    import shutil
    import subprocess
    canonical = None
    if shutil.which("ipfs"):
        r = subprocess.run(["ipfs", "cat", f"/ipfs/{cid}/{artifact}"],
                           capture_output=True, timeout=180)
        canonical = r.stdout if r.returncode == 0 and r.stdout else None
    if canonical is None:
        note("canonical object",
             "no local ipfs could produce the CID-addressed bytes; a gateway is under test "
             "here and must not stand in as the reference")
        return
    for url, obs in (serving.get("gateways") or {}).items():
        g = url.split("/")[2] if "//" in url else url
        for o in obs if isinstance(obs, list) else []:
            client = o.get("as") if isinstance(o, dict) else None
            if not isinstance(client, str):
                continue
            served, why = fetch(url, client, timeout=120)
            if served is None:
                note(f"{g} as {client[:18]!r}", f"{why} — reported, never assumed identical")
                continue
            verdict, detail = classify(served, canonical)
            claimed = o.get("verdict")
            chk(f"{g} as {client[:18]!r}: record says {claimed}, the web says {verdict}",
                verdict == claimed, detail or f"{len(served)} bytes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pins", type=pathlib.Path, default=ROOT / "pins")
    ap.add_argument("--live", action="store_true",
                    help="also re-derive the verdicts against the live web")
    args = ap.parse_args()

    if not args.pins.is_dir():
        print(f"UNVERIFIABLE — no pins directory at {args.pins}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    records = []
    for p in sorted(args.pins.glob("*.json")):
        try:
            records.append((p.stem, json.loads(p.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            print(f"UNVERIFIABLE — {p.name} is not valid JSON", file=sys.stderr)
            return EXIT_UNVERIFIABLE
    if not records:
        print("UNVERIFIABLE — no pin records found", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print("what is SERVED, compared against what was PINNED\n")
    tier1(records)
    if args.live:
        tier2(records)

    print()
    if fails:
        print(f"{len(fails)} serving claim(s) missing, malformed or false:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    if unverifiable:
        # Could-not-check is its own verdict and never a pass — including for this checker.
        # Enumerated legacy records are NOT counted here: they are a deliberate, diffable
        # exclusion, not a failure to look.
        print(f"{len(unverifiable)} item(s) could not be checked. That is not a pass.")
        return EXIT_UNVERIFIABLE
    print("every published record states what gateways serve, and says so in a closed vocabulary")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
