#!/usr/bin/env python3
"""Derive this registry's crc.cell.v2 `registry_id` — frozen-genesis identity.

    registry_id = "sha256:" + hex(SHA-256(JCS(genesis nodes.json)))

The genesis commit is the one that ADDED nodes.json — mechanically derivable,
never recorded by hand:

    git log --diff-filter=A --format=%H -- nodes.json

JCS canonical (not raw bytes, not the git blob hash) so the identity derives from
parsed content and is independent of on-disk formatting. See CELL-v2.md §1.
Stdlib only.
"""
import hashlib
import json
import subprocess
import sys
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# CELL-v3.md §5.1 — v3 admission requires BOTH minted (CELL-v3.md) AND this
# enforcement marker. Same git-log discipline as v2 §4.
V3_ENFORCEMENT_MARKER = "reference/lineage_ref.py"


def _is_shallow(root: str) -> bool:
    r = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                       cwd=root, capture_output=True, text=True)
    return r.stdout.strip() == "true"


def genesis_commit(root: str = ROOT) -> str:
    # Refuse on truncated history BEFORE looking, not after finding nothing.
    #
    # The old guard fired only when the log came back empty — which never happens
    # on a shallow clone. At depth=1 the single visible commit genuinely shows
    # nodes.json as ADDED (it has no parent to diff against), so the log is
    # non-empty, the guard stays silent, and this returns the shallow HEAD as
    # "genesis". That produced a DIFFERENT registry_id and exited 0.
    #
    # The registry identity is what every crc.cell.v2 Cell binds to, so a wrong
    # one silently invalidates every valid Cell — or, worse, lets someone sign a
    # new Cell against a registry identity that does not exist. A default
    # actions/checkout is shallow, so this is the normal case in CI, not an edge.
    #
    # The old guard checked "did I find something" when the question was "could I
    # have seen everything". Could-not-check is never a pass.
    if _is_shallow(root):
        raise RuntimeError(
            "shallow repository — the genesis commit for nodes.json cannot be "
            "derived, and the registry_id computed from a truncated history would "
            "be wrong rather than missing. Fetch full history "
            "(actions/checkout with fetch-depth: 0).")

    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "nodes.json"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    if not out:
        raise RuntimeError("no genesis commit for nodes.json (is this the right repo?)")
    return out[-1]  # oldest = the add


def genesis_bytes(root: str = ROOT) -> bytes:
    commit = genesis_commit(root)
    return subprocess.run(
        ["git", "show", f"{commit}:nodes.json"],
        cwd=root, capture_output=True, check=True,
    ).stdout


def registry_id(root: str = ROOT) -> str:
    obj = json.loads(genesis_bytes(root))
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def activation_commit(spec: str = "CELL-v2.md", root: str = ROOT) -> str:
    """The sunset activation point for `spec`: the commit that ADDED it.

    CELL-v2.md §4: v2 activates when CELL-v2.md lands.
    CELL-v3.md §5.1 (deferred): v3 activates at the enforcement commit — use
    v3_enforcement_commit(), not CELL-v3.md add-commit.
    """
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", spec],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    return out[-1] if out else ""


def v3_enforcement_commit(root: str = ROOT) -> str:
    """CELL-v3.md §5.1 — commit that landed v3 gate + sunset enforcement."""
    return activation_commit(V3_ENFORCEMENT_MARKER, root)


def _later_commit(a: str, b: str, root: str = ROOT) -> str:
    """Chronologically later of two commits on this branch (both must be non-empty)."""
    if not a:
        return b
    if not b:
        return a
    ta = int(subprocess.run(
        ["git", "show", "-s", "--format=%ct", a], cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip())
    tb = int(subprocess.run(
        ["git", "show", "-s", "--format=%ct", b], cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip())
    return a if ta >= tb else b


def in_force_schema(root: str = ROOT) -> str:
    """Admission schema for newly submitted Cells on this branch (derived).

    crc.cell.v3 is in force only when BOTH are true (CELL-v3.md §5.1 deferred):
      minted   = CELL-v3.md has landed
      enforced = v3 enforcement marker has landed
    Until then, CELL-v2.md §4 keeps crc.cell.v2 as the admission schema.
    """
    minted = bool(activation_commit("CELL-v3.md", root))
    enforced = bool(v3_enforcement_commit(root))
    if minted and enforced:
        return "crc.cell.v3"
    if activation_commit("CELL-v2.md", root):
        return "crc.cell.v2"
    return "crc.cell.v1"


def schema_activation_commit(schema: str, root: str = ROOT) -> str:
    """Activation commit for sunset checks on newly submitted Cells."""
    if schema == "crc.cell.v3":
        mint = activation_commit("CELL-v3.md", root)
        enf = v3_enforcement_commit(root)
        if mint and enf:
            return _later_commit(mint, enf, root)
        return ""
    if schema == "crc.cell.v2":
        return activation_commit("CELL-v2.md", root)
    return ""


if __name__ == "__main__" and "--selftest" not in sys.argv:
    print("genesis commit        :", genesis_commit())
    print("registry_id           :", registry_id())
    print("v2 activation commit  :", activation_commit() or "(CELL-v2.md not on branch)")
    print("v3 minted (CELL-v3.md) :", activation_commit("CELL-v3.md") or "(not yet)")
    print("v3 enforced (marker)  :", v3_enforcement_commit() or "(not yet)")
    print("in-force schema       :", in_force_schema())


def _selftest() -> int:
    """Vectors for the derivation's preconditions.

    The shallow case is here because the original guard checked the wrong thing:
    it fired when the git log came back EMPTY, which never happens on a shallow
    clone — depth=1 shows nodes.json as added, so a wrong genesis was returned
    with exit 0. A default actions/checkout is shallow, so this was the normal
    case in CI rather than an edge one.
    """
    import tempfile
    fails = 0

    try:
        rid = registry_id()
        ok = rid.startswith("sha256:") and len(rid) == 71
        print(f"  {'ok  ' if ok else 'FAIL'}  derives from full history: {rid[:26]}…")
        fails += not ok
    except Exception as e:
        print(f"  FAIL  full history raised: {e}")
        fails += 1

    with tempfile.TemporaryDirectory() as td:
        dst = os.path.join(td, "shallow")
        r = subprocess.run(["git", "clone", "--quiet", "--depth=1", "file://" + ROOT, dst],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("  amber could not make a shallow clone — vector SKIPPED")
        else:
            try:
                got = registry_id(dst)
                print(f"  FAIL  shallow clone returned a value ({got[:22]}…) instead of refusing")
                fails += 1
            except RuntimeError:
                print("  ok    refuses on a shallow repository (never a wrong identity)")
    return fails


if __name__ == "__main__" and "--selftest" in sys.argv:
    raise SystemExit(1 if _selftest() else 0)

