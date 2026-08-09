#!/usr/bin/env python3
"""`ui/index.html` must be exactly what building this repo produces.

This is the check that makes "someone sends us an IPFS CID and we repin it" a
safe thing to do instead of an act of trust.

The ENS contenthash is the one pointer in this stack that is not recomputable.
Everything else — claim_id, evidence_hash, the signer, the edge — a stranger can
re-derive. The pin cannot be: it is a transaction we send, pointing at bytes we
chose. And the console's embedded snapshot is the matrix's PRIMARY data source
(only node 2's cell is fetched live), so bytes that were tampered with would
render fabricated nodes and fabricated GREEN cells under the org's own domain.

If the build is a pure function of repo state, that problem dissolves. Anyone can
take a proposed CID, build `main` at a stated commit, and compare. Nobody has to
trust the person who sent it, including us. "Don't trust, recompute" applied to
our own front door.

This check enforces the precondition: the committed page is byte-identical to a
fresh build. If it drifts, the published page stops corresponding to any commit
and there is nothing to compare a CID against.

Run `python3 ui/embed_snapshot.py` to fix a failure.
"""

import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "ui" / "index.html"


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not INDEX.exists():
        print(f"FAIL  {INDEX.relative_to(ROOT)} does not exist")
        return 1

    committed = sha(INDEX)

    # Build into a copy so a failing check never mutates the working tree —
    # a check that "fixes" what it is checking cannot fail twice, and would
    # turn a CI failure into a silent local pass.
    with tempfile.TemporaryDirectory() as td:
        probe = pathlib.Path(td) / "index.html"
        shutil.copy2(INDEX, probe)
        r = subprocess.run([sys.executable, str(ROOT / "ui" / "embed_snapshot.py"), str(probe)],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            print("FAIL  the build itself failed:")
            print("      " + (r.stderr.strip().splitlines() or ["(no output)"])[-1])
            return 1
        rebuilt = sha(probe)

        # Build twice: a build that is not deterministic against ITSELF can
        # never be checked against anyone else's, and would make this whole
        # check pass or fail by luck.
        probe2 = pathlib.Path(td) / "index2.html"
        shutil.copy2(INDEX, probe2)
        subprocess.run([sys.executable, str(ROOT / "ui" / "embed_snapshot.py"), str(probe2)],
                       capture_output=True, text=True, cwd=ROOT)
        if sha(probe2) != rebuilt:
            print("FAIL  the build is not deterministic — two builds of one repo state\n"
                  "      differ, so no CID can be verified against a commit. Something\n"
                  "      time- or order-dependent got into ui/embed_snapshot.py.")
            return 1

    if committed != rebuilt:
        print(f"FAIL  ui/index.html is not the build of this commit.\n"
              f"        committed: sha256:{committed[:32]}…\n"
              f"        rebuilt:   sha256:{rebuilt[:32]}…\n"
              f"      The published page would correspond to no commit, and a\n"
              f"      submitted CID could not be checked against main.\n"
              f"      Fix: python3 ui/embed_snapshot.py")
        return 1

    print(f"ok    ui/index.html is the deterministic build of this commit "
          f"(sha256:{committed[:16]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
