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


def activation_commit(root: str = ROOT) -> str:
    """The v1-sunset activation point: the commit that ADDED CELL-v2.md (CELL-v2.md §4)."""
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", "CELL-v2.md"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.split()
    return out[-1] if out else ""


if __name__ == "__main__":
    print("genesis commit   :", genesis_commit())
    print("registry_id      :", registry_id())
    act = activation_commit()
    print("activation commit:", act or "(CELL-v2.md not yet on this branch)")
