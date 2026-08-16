#!/usr/bin/env python3
"""`selects` must be TRUE, not merely present.

check_pin_selects.py proves the field is there and well-formed. That is a syntax check: a
record could carry `selects.commit` naming a commit that does not exist, or an artifact path
that was never in that tree, and pass. The published page derives its currency from this field
in one hop, so a `selects` that points nowhere makes the page render CURRENT or STALE against
a commit that is not a thing.

@boardyai, 15 August 2026, closing the wiring thread: "keep the pin record's selects field
authoritative." That sentence is a discipline, and a discipline is a rule with no failure mode.
This is the failure mode.

TWO TIERS, AND THE SPLIT IS THE DESIGN.

  Tier 1 — COVERAGE, offline, always runs, gates CI.
      `selects.commit` resolves in this repository and `selects.artifact` exists at it, as a
      file. Pure local git, deterministic, no network. This catches the realistic failure: a
      typo, a commit that only ever existed on someone's machine, a renamed artifact.

  Tier 2 — CONTENT, `--live`, needs the network.
      The stamped build of `selects.artifact` at `selects.commit` is byte-identical to the
      artifact actually published under the record's CID. That is what makes `selects` true
      rather than resolvable. It reproduces exactly what trustless-ai-landing/build/
      sync_console.py installs: the committed artifact with __CONSOLE_SOURCE_COMMIT__ replaced
      by the commit — the only transformation that build applies.

Tier 2 cannot run in CI (no daemon, no peers), and a check that reports could-not-check on
every CI run is a check nobody reads. So Tier 2 is run by hand at publication time and its
RESULT is written into the pin record, where check_served_bytes.py's coverage tier then
requires it to be present. Coverage is gateable offline; content needs the world. Conflating
them is how you get a green that means nothing.

EXIT: 0 · 1 a record's `selects` does not resolve · 2 could not check.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
SHA40 = re.compile(r"^[0-9a-f]{40}$")

# Records written before `selects` existed. Kept in sync with check_pin_selects.py by importing
# it rather than by copying the set — two lists that must agree is the duplication this repo
# refuses everywhere else.
sys.path.insert(0, str(ROOT / "reference"))
from check_pin_selects import LEGACY_WITHOUT_SELECTS  # noqa: E402

# `selects.repo` is resolved against THIS checkout. A record selecting some other repository
# cannot be verified from here, and the honest answer is could-not-check, never a pass.
THIS_REPO = "https://github.com/trustless-ai/cross-reference-console"

fails: list[str] = []
unverifiable: list[str] = []


def _stub() -> dict | None:
    """Data-only substitute for the published-artifact fetch — see the twin in
    check_served_bytes.py. The live tier could not be made to fail on demand, which made
    its one assertion permanently unbacked."""
    import os
    path = os.environ.get("CRC_LIVE_STUB")
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def chk(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {label}" + (f" — {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(label)


def note(label: str, detail: str) -> None:
    print(f"  ..    {label} — {detail}")
    unverifiable.append(label)


def git(*args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def stamped_artifact(commit: str, artifact: str) -> bytes | None:
    """Exactly what sync_console.py installs: the committed artifact, placeholder replaced.

    Reproduced here rather than imported because that script lives in the landing repository
    and this check must run without it. The transformation is one substitution — if that ever
    stops being true, Tier 2 starts failing, which is the correct direction for a check whose
    subject is 'does the record still describe reality'.
    """
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{artifact}"],
                       capture_output=True)
    if r.returncode != 0:
        return None
    built = r.stdout
    stamped = built.replace(b"__CONSOLE_SOURCE_COMMIT__", commit.encode())
    return None if stamped == built else stamped


def tier1(records: list[tuple[str, dict]]) -> None:
    print("tier 1 — every `selects` resolves in this repository (offline)\n")
    for cid, rec in records:
        short = cid[:16] + "…"
        sel = rec.get("selects")
        if sel is None:
            if cid in LEGACY_WITHOUT_SELECTS:
                print(f"  ..    {short}: enumerated legacy record, predates the field")
            else:
                chk(f"{short}: has `selects`", False, "not legacy and not present")
            continue

        repo = str(sel.get("repo", "")).rstrip("/").removesuffix(".git")
        if repo != THIS_REPO:
            # Not a pass and not a failure: this checkout cannot resolve a foreign repo, and
            # pretending otherwise is exactly the collapse the rest of this repo refuses.
            note(f"{short}: selects a repository this checkout is not",
                 f"{repo or '(none)'} — cannot resolve here")
            continue

        commit = str(sel.get("commit", ""))
        artifact = str(sel.get("artifact", ""))
        if not SHA40.match(commit):
            chk(f"{short}: `selects.commit` is a full sha", False, repr(commit)[:60])
            continue

        rc, _ = git("cat-file", "-e", commit + "^{commit}")
        if rc != 0:
            chk(f"{short}: `selects.commit` resolves", False,
                f"{commit[:12]} is not a commit in this repository")
            continue
        chk(f"{short}: `selects.commit` resolves", True)

        rc, kind = git("cat-file", "-t", f"{commit}:{artifact}")
        if rc != 0:
            chk(f"{short}: `selects.artifact` exists at that commit", False,
                f"{artifact!r} not found at {commit[:12]}")
            continue
        chk(f"{short}: `selects.artifact` is a file at that commit",
            kind.strip() == "blob", f"{artifact} is a {kind.strip()}")


def tier2(records: list[tuple[str, dict]]) -> None:
    """The record's CID actually serves the build of the commit it names."""
    import shutil
    print("\ntier 2 — the published artifact IS the stamped build of the selected commit\n")
    if _stub() is None and not shutil.which("ipfs"):
        note("tier 2", "no ipfs binary — cannot fetch any published artifact")
        return
    for cid, rec in records:
        short = cid[:16] + "…"
        sel = rec.get("selects") or {}
        commit, artifact = str(sel.get("commit", "")), str(sel.get("artifact", ""))
        if not SHA40.match(commit) or not artifact:
            continue
        installs_to = str(rec.get("installs_to") or "console/index.html")
        expected = stamped_artifact(commit, artifact)
        if expected is None:
            note(f"{short}: rebuild", f"{artifact} at {commit[:12]} carries no placeholder")
            continue
        stub = _stub()
        if stub is not None:
            import base64
            v = (stub.get("published") or {}).get(f"{cid}/{installs_to}")
            published = None if v is None else base64.b64decode(v)
        else:
            r = subprocess.run(["ipfs", "cat", f"/ipfs/{cid}/{installs_to}"],
                               capture_output=True, timeout=180)
            published = r.stdout if r.returncode == 0 and r.stdout else None
        if published is None:
            note(f"{short}: fetch {installs_to}", "not retrievable")
            continue
        chk(f"{short}: published {installs_to} is the stamped build of {commit[:12]}",
            published == expected,
            f"published bytes differ from the rebuild ({len(published)} vs {len(expected)})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pins", type=pathlib.Path, default=ROOT / "pins")
    ap.add_argument("--live", action="store_true",
                    help="also verify the published artifact against the rebuild (needs ipfs)")
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

    rc, _ = git("rev-parse", "--git-dir")
    if rc != 0:
        print("UNVERIFIABLE — not a git checkout, so no commit can be resolved", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print("`selects` is true, not merely present\n")
    tier1(records)
    if args.live:
        tier2(records)

    print()
    if fails:
        print(f"{len(fails)} record(s) name something that does not exist:")
        for f in fails:
            print(f"    - {f}")
        return EXIT_BAD
    if unverifiable:
        # Could-not-check is its own verdict and never a pass — including for this checker.
        # Enumerated legacy records are NOT counted here: they are a deliberate, diffable
        # exclusion, not a failure to look.
        print(f"{len(unverifiable)} item(s) could not be checked. That is not a pass.")
        return EXIT_UNVERIFIABLE
    print("every `selects` resolves to a real commit and a real artifact")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
