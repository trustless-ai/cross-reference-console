#!/usr/bin/env python3
"""`selects` is required on new pin records — the bridge the schema already knew in prose.

WHY. A pin record says which CID was published and which landing commit produced it. It did not
say which CONSOLE commit that publication selects, so deriving currency meant: resolved CID ->
pin record -> landing commit -> console.lock at that commit -> console commit. Three network
hops, the middle one a file in another repo at a specific commit. The fact was present the whole
time — in prose, in the `purpose` field — but prose is not a schema boundary and cannot support
a one-hop derivation safely.

@boardyai, 15 August 2026:

    "Make selects required for new crc.pin-record.v0 records, with the selected repo, exact
     commit, and artifact path or name. Existing records should map to lock_unreadable, not be
     inferred through landing history."

    "Missing selects is a structural inability to establish currency, not an old-style STALE
     and not permission to chase another repo."

THE GRANDFATHER SET IS ENUMERATED, NOT DATED. Records that predate the field are listed below by
CID. A date rule would silently absolve any future record whose clock looked old enough; an
explicit list means a new record without `selects` fails unless someone deliberately adds its
CID here, which is visible in a diff and has to be argued for.

EXIT: 0 every record either carries a well-formed `selects` or is an enumerated legacy record ·
1 a record is missing it or malformed · 2 could not check.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PINS = ROOT / "pins"

# Written before `selects` existed. Their currency is not derivable one-hop and must resolve to
# COULD_NOT_CHECK / lock_unreadable — never inferred through landing history.
LEGACY_WITHOUT_SELECTS = {
    "bafybeiadnqxc5wmgtct3mjbnfoa5wpqa3fcjrwt4xoli6pivs34p2mnzxy",
    "bafybeiblwwa2wnbftf4nu3byvzprxlz5odmojawms7iv2fxdcnoscpdvya",
    "bafybeibr5uvrp5qvagipyatzv2xdrwtlwzrv4nno45abgqkirt6imhe5lm",
    "bafybeicctklscgxsitekmrdujz4hf345rg225stzpfvihdbgwvdogrh63q",
    "bafybeid4nm3b7ptrhmztyu6kzlz2vgavz4il2bezx6r5ljpvrl3yfpjhli",
    "bafybeigryfhrdiuicuwnrsjdhrkid4l2it5otneqimch463mdlup6wvdg4",
}

EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
SHA40 = re.compile(r"^[0-9a-f]{40}$")
fails: list[str] = []


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


def main() -> int:
    if not PINS.is_dir():
        print(f"UNVERIFIABLE — no pins directory at {PINS}", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    records = sorted(PINS.glob("*.json"))
    if not records:
        print("UNVERIFIABLE — no pin records found; nothing was checked", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print(f"`selects` on {len(records)} pin record(s)\n")
    seen_legacy = set()

    for rec in records:
        cid = rec.stem
        try:
            d = json.loads(rec.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            chk(f"{cid[:18]}… readable", False, str(e))
            continue

        sel = d.get("selects")
        if cid in LEGACY_WITHOUT_SELECTS:
            seen_legacy.add(cid)
            # Grandfathered — but if one ever GAINS the field it must still be well formed.
            if sel is None:
                print(f"  ..    {cid[:18]}… legacy, no `selects` — currency is COULD_NOT_CHECK/lock_unreadable by design")
                continue
            print(f"  ..    {cid[:18]}… legacy but now carries `selects`; validating it anyway")

        if sel is None:
            chk(f"{cid[:18]}… carries `selects`", False,
                "new records must name the commit they select; add it, or argue for the CID in LEGACY_WITHOUT_SELECTS")
            continue

        ok_shape = isinstance(sel, dict)
        chk(f"{cid[:18]}… `selects` is an object", ok_shape, type(sel).__name__)
        if not ok_shape:
            continue
        chk(f"{cid[:18]}… names a repo", isinstance(sel.get("repo"), str) and sel["repo"].startswith("http"),
            str(sel.get("repo")))
        chk(f"{cid[:18]}… names an exact 40-hex commit",
            isinstance(sel.get("commit"), str) and bool(SHA40.match(sel["commit"])), str(sel.get("commit")))
        chk(f"{cid[:18]}… names the artifact", isinstance(sel.get("artifact"), str) and len(sel["artifact"]) > 2,
            str(sel.get("artifact")))
        # The two commits are different facts and must not be the same value by accident.
        chk(f"{cid[:18]}… selects.commit is not the landing commit",
            sel.get("commit") != d.get("commit"),
            "a record that selects its own landing commit has not recorded the bridge")

    print()
    stale_legacy = LEGACY_WITHOUT_SELECTS - seen_legacy
    chk("every enumerated legacy CID still exists",
        not stale_legacy,
        f"listed but absent: {sorted(stale_legacy)} — remove them rather than carrying dead exemptions")

    print()
    if fails:
        print(f"{len(fails)} problem(s):")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    print("every record either names the commit it selects, or is an enumerated legacy record")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
