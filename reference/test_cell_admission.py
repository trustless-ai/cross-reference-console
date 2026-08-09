#!/usr/bin/env python3
"""Admission / activation vectors for deferred v3 enforcement (CELL-v3.md §5.1).

Run:  python3 reference/test_cell_admission.py
"""
import os
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
_REAL_MINT = _ORIG_ACTIVATION("CELL-v3.md")
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
            if not minted:
                return ""
            # When the spec is not on branch yet, stand in a distinct commit so
            # patched ancestry tests remain meaningful on enforcement-only main.
            return _REAL_MINT if _REAL_MINT else _REAL_V2
        if spec == ri.V3_ENFORCEMENT_MARKER:
            return _REAL_ENF if enforced else ""
        return _ORIG_ACTIVATION(spec, root)

    ri.activation_commit = fake_activation


def _restore_activation():
    ri.activation_commit = _ORIG_ACTIVATION


def _expected_in_force(minted: bool, enforced: bool) -> str:
    return "crc.cell.v3" if (minted and enforced) else "crc.cell.v2"


def _activation_by_ancestry(mint: str, enf: str) -> str:
    if not mint or not enf:
        return ""
    if subprocess.run(["git", "merge-base", "--is-ancestor", mint, enf],
                      cwd=str(ROOT), capture_output=True).returncode == 0:
        return enf
    if subprocess.run(["git", "merge-base", "--is-ancestor", enf, mint],
                      cwd=str(ROOT), capture_output=True).returncode == 0:
        return mint
    raise RuntimeError("divergent mint/enforce commits — activation undefined")


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

    print("\n── live checkout smoke (derived, not hardcoded)")
    live_minted = bool(_ORIG_ACTIVATION("CELL-v3.md"))
    live_enforced = bool(_REAL_ENF)
    live_expect = _expected_in_force(live_minted, live_enforced)
    chk("v3 enforcement marker derivable when present in history", live_enforced)
    chk(
        f"live: minted={live_minted} enforced={live_enforced} → in_force={live_expect}",
        ri.in_force_schema() == live_expect,
    )
    if live_minted and live_enforced:
        chk("v3 activation commit derivable when both live", bool(ri.schema_activation_commit("crc.cell.v3")))
    else:
        chk("v3 activation commit absent until both live", not ri.schema_activation_commit("crc.cell.v3"))

    print("\n── regression: harness passes in enforcement-only and minted+enforced states")
    for minted, enforced, label in (
        (False, True, "enforcement-only (simulated)"),
        (True, True, "minted + enforced (simulated)"),
    ):
        _patch_mint_enforce(minted, enforced)
        expect = _expected_in_force(minted, enforced)
        chk(f"{label}: in_force_schema() == {expect}", ri.in_force_schema() == expect)
        if minted and enforced:
            mint = ri.activation_commit("CELL-v3.md")
            enf = ri.v3_enforcement_commit()
            act = ri.schema_activation_commit("crc.cell.v3")
            want = _activation_by_ancestry(mint, enf)
            chk(f"{label}: schema_activation_commit() == later(mint, enforce)", act == want)
        else:
            chk(f"{label}: schema_activation_commit() empty", not ri.schema_activation_commit("crc.cell.v3"))
    _restore_activation()

    print("\n── v3 sunset activation uses later of mint and enforce")
    _patch_mint_enforce(True, True)
    mint = ri.activation_commit("CELL-v3.md")
    enf = ri.v3_enforcement_commit()
    act = ri.schema_activation_commit("crc.cell.v3")
    expected = _activation_by_ancestry(mint, enf)
    chk("v3 activation is the descendant of mint/enforce (by ancestry)", act == expected)
    _restore_activation()

    print("\n── activation follows history order, NOT commit timestamps")
    # A descendant may legally carry an earlier %ct than its parent — rebase,
    # cherry-pick, imported history, a skewed clock. Ordering by timestamp then
    # selects the ANCESTOR and moves the activation boundary backwards.
    # Reproduced by @pipavlo82; this pins it.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        run = lambda *a, **k: subprocess.run(a, cwd=td, capture_output=True, text=True,
                                      env={**env, **k.pop("extra", {})}, **k)
        run("git", "init", "-q", ".")
        pathlib.Path(td, "f1").write_text("a"); run("git", "add", "f1")
        run("git", "commit", "-q", "-m", "parent",
            extra={"GIT_AUTHOR_DATE": "2026-08-09T12:00:00",
                   "GIT_COMMITTER_DATE": "2026-08-09T12:00:00"})
        parent = run("git", "rev-parse", "HEAD").stdout.strip()
        pathlib.Path(td, "f2").write_text("b"); run("git", "add", "f2")
        run("git", "commit", "-q", "-m", "child",          # descendant, EARLIER date
            extra={"GIT_AUTHOR_DATE": "2026-08-09T09:00:00",
                   "GIT_COMMITTER_DATE": "2026-08-09T09:00:00"})
        child = run("git", "rev-parse", "HEAD").stdout.strip()

        ct = lambda x: int(run("git", "show", "-s", "--format=%ct", x).stdout.strip())
        chk("  fixture is genuinely skewed (child older by clock)", ct(child) < ct(parent))
        chk("picks the descendant despite the earlier timestamp",
            ri._later_commit(parent, child, root=td) == child)
        chk("  and is order-independent",
            ri._later_commit(child, parent, root=td) == child)

        # Divergent histories must refuse — never guess an activation boundary.
        run("git", "checkout", "-q", parent)
        pathlib.Path(td, "f3").write_text("c"); run("git", "add", "f3")
        run("git", "commit", "-q", "-m", "sibling")
        sibling = run("git", "rev-parse", "HEAD").stdout.strip()
        diverged = False
        try:
            ri._later_commit(child, sibling, root=td)
        except RuntimeError:
            diverged = True
        chk("divergent histories refuse _later_commit (fail-closed)", diverged)

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
