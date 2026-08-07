#!/usr/bin/env python3
"""Admission / activation vectors for deferred v3 enforcement (CELL-v3.md §5.1).

Run:  python3 reference/test_cell_admission.py
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import registry_id as ri  # noqa: E402
from lineage_ref import validate_derived_from, LineageRefError  # noqa: E402

PASS, FAIL = "  ok  ", "  FAIL"
failures = 0

_ORIG_ACTIVATION = ri.activation_commit
_REAL_V2 = _ORIG_ACTIVATION("CELL-v2.md")
_REAL_ENF = ri.v3_enforcement_commit()


def chk(label, cond):
    global failures
    print(f"{PASS if cond else FAIL}  {label}")
    if not cond:
        failures += 1


def _patch_mint_enforce(minted: bool, enforced: bool):
    """Simulate CELL-v3.md and enforcement-marker presence without touching disk."""

    def fake_activation(spec: str = "CELL-v2.md", root: str = ri.ROOT) -> str:
        if spec == "CELL-v3.md":
            return _REAL_V2 if minted else ""
        if spec == ri.V3_ENFORCEMENT_MARKER:
            return _REAL_ENF if enforced else ""
        return _ORIG_ACTIVATION(spec, root)

    ri.activation_commit = fake_activation


def _restore_activation():
    ri.activation_commit = _ORIG_ACTIVATION


def main() -> int:
    print("── four-state in-force schema (minted × enforced)")
    for minted, enforced, expect, label in (
        (False, False, "crc.cell.v2", "neither present → v2"),
        (True, False, "crc.cell.v2", "spec only → v2"),
        (False, True, "crc.cell.v2", "enforcement only → v2"),
        (True, True, "crc.cell.v3", "spec + enforcement → v3"),
    ):
        _patch_mint_enforce(minted, enforced)
        chk(label, ri.in_force_schema() == expect)
    _restore_activation()

    print("\n── live branch state (enforcement-only until CELL-v3.md lands)")
    chk("v3 enforcement marker derivable", bool(ri.v3_enforcement_commit()))
    chk("CELL-v3.md not minted on branch", not ri.activation_commit("CELL-v3.md"))
    chk("in-force schema is crc.cell.v2 (enforcement alone)", ri.in_force_schema() == "crc.cell.v2")

    print("\n── v3 sunset activation uses later of mint and enforce")
    _patch_mint_enforce(True, True)
    act = ri.schema_activation_commit("crc.cell.v3")
    later = ri._later_commit(_REAL_V2, _REAL_ENF)
    chk("v3 activation commit derivable when both present", act == later)
    _restore_activation()

    print("\n── existing Cells still validate")
    for c in sorted(ROOT.glob("cells/*/*.cell.json")):
        r = subprocess.run(
            [sys.executable, str(HERE / "validate_cell.py"), str(c)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        chk(f"{c.name} validates unchanged", r.returncode == 0)

    print("\n── lineage gate vectors")
    own = "sha256:" + "a" * 64
    try:
        validate_derived_from([], own)
        chk("[] accepted", True)
    except LineageRefError:
        chk("[] accepted", False)
    for bad in (
        None,
        ["crc.lineage.v0:impl/sha256:" + "a" * 64],
        ["crc.lineage.v0:impl/sha256:" + "b" * 64, "crc.lineage.v0:impl/sha256:" + "b" * 64],
    ):
        try:
            validate_derived_from(bad, own)
            chk(f"rejects {bad!r}", False)
        except LineageRefError:
            chk(f"rejects {bad!r}", True)

    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("all green — cell admission / lineage gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
