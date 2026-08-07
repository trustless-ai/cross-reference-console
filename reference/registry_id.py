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


def genesis_commit(root: str = ROOT) -> str:
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "nodes.json"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    if not out:
        raise RuntimeError("no genesis commit for nodes.json (shallow clone? fetch full history)")
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


if __name__ == "__main__":
    print("genesis commit        :", genesis_commit())
    print("registry_id           :", registry_id())
    print("v2 activation commit  :", activation_commit() or "(CELL-v2.md not on branch)")
    print("v3 minted (CELL-v3.md) :", activation_commit("CELL-v3.md") or "(not yet)")
    print("v3 enforced (marker)  :", v3_enforcement_commit() or "(not yet)")
    print("in-force schema       :", in_force_schema())
