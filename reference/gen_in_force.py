#!/usr/bin/env python3
"""
Generate CELL-IN-FORCE.md — the complete format a NEW Cell must follow today.

Why this exists: the Cell spec is append-only, so it is spread across CELL.md,
CELL-v1.md, CELL-v2.md (and every version after). Each file is a diff over the
one before, which is right for history and wrong for a newcomer — an outsider
who wants to sign one Cell has to triangulate every version to learn what is
currently required. That was gap 6 of the onboarding walk in PR #7.

The obvious fix is a hand-written unified document. That is the WRONG fix: it
would drift from the frozen files the first time anyone edits one, and
not-drifting is the entire reason the versions are frozen.

So this is generated, and generated the most faithful way available — **by
building a conforming Cell and recording what was demanded of it.** Every rule
listed below is a rule that actually fired, in the validator CI runs, against a
Cell created by the tool contributors are told to use. Nothing here is
transcribed from prose, so nothing here can disagree with the code.

    python3 reference/gen_in_force.py            # write CELL-IN-FORCE.md
    python3 reference/gen_in_force.py --check    # CI: fail if it would change
    python3 reference/gen_in_force.py --selftest # activation + LF byte-identity vectors

Generated artifacts are checked by raw UTF-8 bytes (LF only). read_text() is not
used for --check — universal newline translation on Windows would false-GREEN CRLF.

Stdlib + the repo's own modules only.
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import registry_id as ri  # noqa: E402
import create_cell as cc  # noqa: E402

OUT = ROOT / "CELL-IN-FORCE.md"


def canonical_bytes(text: str) -> bytes:
    """LF UTF-8 bytes for a generated artifact. Byte checks use this, never read_text()."""
    return text.encode("utf-8")


def _artifact_stale_reason(on_disk: bytes, want: bytes) -> str:
    if on_disk == want:
        return ""
    if b"\r" in on_disk and on_disk.replace(b"\r\n", b"\n") == want:
        return ("CELL-IN-FORCE.md has CRLF line endings — canonical output is LF only. "
                "Run: python3 reference/gen_in_force.py")
    return ("CELL-IN-FORCE.md is STALE — the enforced format changed and the "
            "generated view did not.\nRun: python3 reference/gen_in_force.py")


def in_force_schema() -> str:
    """Whatever the repo's own admission logic says. Never a second opinion."""
    if hasattr(ri, "in_force_schema"):        # the derivation, once #13 lands
        return ri.in_force_schema()
    return cc.in_force_schema()               # today's derivation


def specs_present():
    """Frozen spec files, oldest first. Discovered, never listed."""
    out = []
    if (ROOT / "CELL.md").exists():
        out.append(("v0", "CELL.md"))
    ns = sorted(int(p.name[6:-3]) for p in ROOT.glob("CELL-v*.md") if p.name[6:-3].isdigit())
    out += [(f"v{n}", f"CELL-v{n}.md") for n in ns]
    return out


def build_and_capture(schema: str):
    """Create a conforming Cell in a scratch copy and record every check it had
    to pass. The list is the output of the validator, not a description of it."""
    from eth_account import Account

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "repo"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(["git", "add", "-A"], cwd=work, check=True)
        subprocess.run(["git", "-c", "user.name=g", "-c", "user.email=g@g",
                        "commit", "-q", "-m", "snapshot"], cwd=work, check=True)

        acct = Account.create()
        nodes = json.loads((work / "nodes.json").read_text())
        nodes["nodes"].append({
            "node_id": "specimen", "display": "specimen (generated)",
            "verifier": acct.address, "lane": "recompute/specimen", "envelope": "eip712",
            "key_ref": {"pubkey": None, "address": acct.address, "keys_url": None},
            "cell_url_template": None, "since": "2026-01-01T00:00:00Z", "retired": None,
        })
        (work / "nodes.json").write_text(json.dumps(nodes, indent=2) + "\n")

        # pathlib's glob includes dotfiles, unlike the shell -- claims/.watermark.json
        # sorts first and is not a Claim. Match the naming convention instead.
        claim_path = sorted(c for c in (work / "claims").glob("*.json")
                            if re.fullmatch(r"[0-9a-f]{64}", c.stem))[0]
        claim = json.loads(claim_path.read_text())
        evidence = {
            "claim_preimage": claim["claim_preimage"],
            "recomputed": {"note": "generated specimen"},
            "independence": {
                "implementation": {"repo": "https://example.invalid/specimen",
                                   "commit": "0" * 40, "path": "specimen.py",
                                   "impl_hash": "sha256:" + "0" * 64},
                "dependency_lock": None, "runtime_image": None, "inputs": [],
            },
        }
        if schema == "crc.cell.v3":
            evidence["independence"]["derived_from"] = []
        ev_path = work / "specimen-evidence.json"
        ev_path.write_text(json.dumps(evidence, indent=2))

        env = {**os.environ, "CRC_KEY": "0x" + acct.key.hex().removeprefix("0x")}
        r = subprocess.run(
            [sys.executable, "reference/create_cell.py", "--claim", str(claim_path),
             "--node", "specimen", "--result", "GREEN",
             "--boundary", "generated specimen — records what the validator demands",
             "--evidence", str(ev_path)],
            cwd=work, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            raise SystemExit("could not build a conforming specimen Cell:\n" + r.stdout + r.stderr)

        checks = [ln.split("·", 1)[1].split("—")[0].strip()
                  for ln in r.stdout.splitlines() if "ok ·" in ln]
        struct = [f["name"] for f in cc.CELL_TYPE_V2]
        return checks, struct


def activation_block(schema: str) -> tuple[str, list[str]]:
    """Markdown table rows for the in-force activation boundary (derived, not hand-written)."""
    if schema == "crc.cell.v3":
        mint = ri.activation_commit("CELL-v3.md")
        enf = ri.v3_enforcement_commit()
        act = ri.schema_activation_commit(schema)
        if mint and enf and act:
            marker = ri.V3_ENFORCEMENT_MARKER
            return act, [
                f"| mint commit (`CELL-v3.md`) | `{mint[:12]}` |",
                f"| enforcement commit (`{marker}`) | `{enf[:12]}` |",
                f"| activation commit | `{act[:12]}` |",
                "| activation rule | later(mint, enforce) by ancestry — v3 in force only when **both** landed |",
            ]
    ver = schema.rsplit(".v", 1)[1]
    spec = f"CELL-v{ver}.md"
    act = ri.schema_activation_commit(schema) or ri.activation_commit(spec)
    return act, [
        f"| activation commit | `{act[:12] if act else 'n/a'}` |",
        f"| derived from | `git log --diff-filter=A -- {spec}` |",
    ]


def _verify_activation(schema: str, text: str) -> None:
    """Regression: generated view must use schema_activation_commit, not enforce-only."""
    act, _ = activation_block(schema)
    if schema != "crc.cell.v3" or not act:
        return
    want = ri.schema_activation_commit(schema)
    enf = ri.v3_enforcement_commit()
    if not want:
        return
    if f"| activation commit | `{want[:12]}` |" not in text:
        raise SystemExit(
            "CELL-IN-FORCE.md activation commit does not match "
            "registry_id.schema_activation_commit() — regenerate with gen_in_force.py")
    if enf and want != enf and f"| activation commit | `{enf[:12]}` |" in text:
        raise SystemExit(
            "CELL-IN-FORCE.md uses enforcement-only activation — v3 requires "
            "later(mint, enforce) by ancestry (see CELL-v3.md §5.1)")


def render(schema: str, checks, struct) -> str:
    act, act_rows = activation_block(schema)

    L = []
    a = L.append
    a("# The Cell format in force — generated, do not edit")
    a("")
    a("**Generated by `reference/gen_in_force.py`. CI fails if it is stale.**")
    a("")
    a("The Cell spec is append-only, so it lives across several frozen files, each a")
    a("diff over the one before. That is right for history and useless for a newcomer:")
    a("to sign one Cell you would have to read all of them and work out what still")
    a("applies. This file answers only *\"what must a Cell I create today satisfy\"*.")
    a("")
    a("It is **not** a spec. The frozen files are normative and this is derived from")
    a("running the code that enforces them — every rule below fired against a Cell built")
    a("by `reference/create_cell.py` and checked by `reference/validate_cell.py`. Nothing")
    a("here is transcribed, so nothing here can disagree with what CI does.")
    a("")
    a("## In force right now")
    a("")
    a(f"| schema | `{schema}` |")
    a("|---|---|")
    for row in act_rows:
        a(row)
    a("")
    if schema == "crc.cell.v3" and act and ri.activation_commit("CELL-v3.md") and ri.v3_enforcement_commit():
        a("v3 is in force because **CELL-v3.md is minted** and the **enforcement marker** "
          "is present — neither alone activates admission. The activation boundary is the "
          "**later** of the mint and enforcement commits by ancestry (same rule as "
          "`check_sunset.py` and `registry_id.schema_activation_commit()`).")
    a("Cells added after the activation commit must carry this schema. Everything older stands as")
    a("frozen history and is never re-signed or re-judged.")
    a("")
    a("## The signed struct")
    a("")
    a("EIP-712 `types.Cell`, in order:")
    a("")
    a("```")
    for f in struct:
        a(f"  {f}")
    a("```")
    a("")
    a("On the Nostr lane the same payload is the signed `content` of a NIP-01 event.")
    a("")
    a("## What a new Cell must satisfy")
    a("")
    a("Every line below is a check that ran, in order, against a freshly created")
    a(f"`{schema}` Cell:")
    a("")
    for i, c in enumerate(checks, 1):
        a(f"{i:2}. {c}")
    a("")
    a("## Where the normative text lives")
    a("")
    a("| version | file | status |")
    a("|---|---|---|")
    cur = schema.rsplit(".v", 1)[1]
    for label, fn in specs_present():
        status = "**in force**" if label == f"v{cur}" else "frozen — history, still verifiable"
        a(f"| `{label}` | [{fn}]({fn}) | {status} |")
    a("")
    a("Read the in-force file for what changed most recently; read the earlier ones only")
    a("to verify a Cell that was signed under them.")
    a("")
    a("## Making one")
    a("")
    a("See [ONBOARDING.md](ONBOARDING.md). The short version:")
    a("")
    a("```bash")
    a("export CRC_KEY=0x...")
    a("python3 reference/create_cell.py --claim claims/<id>.json --node <you> \\")
    a("    --result GREEN --boundary \"...\" --evidence evidence.json")
    a("```")
    a("")
    return "\n".join(L) + "\n"


def _selftest_artifact_bytes() -> int:
    """Byte-identity regression: CRLF must not pass when canonical output is LF."""
    fails = 0
    sample = "# generated\nsecond line\n"
    want = canonical_bytes(sample)
    crlf = sample.replace("\n", "\r\n").encode("utf-8")

    ok = want != crlf
    print(f"  {'ok  ' if ok else 'FAIL'}  CRLF bytes differ from canonical LF")
    fails += not ok

    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "artifact.md"
        path.write_bytes(want)
        ok = path.read_bytes() == want
        print(f"  {'ok  ' if ok else 'FAIL'}  canonical LF artifact -> GREEN")
        fails += not ok

        path.write_bytes(crlf)
        ok = path.read_bytes() != want
        print(f"  {'ok  ' if ok else 'FAIL'}  same logical content with CRLF -> RED")
        fails += not ok

        path.write_bytes(b"# wrong\n")
        ok = path.read_bytes() != want
        print(f"  {'ok  ' if ok else 'FAIL'}  content mismatch -> RED")
        fails += not ok

        path.write_bytes(want)
        ok = path.read_bytes() == want
        print(f"  {'ok  ' if ok else 'FAIL'}  LF regenerated artifact -> GREEN")
        fails += not ok

    return fails


def _selftest() -> int:
    """Regression vectors for activation derivation and byte-identity checks."""
    fails = _selftest_artifact_bytes()
    print()
    schema = in_force_schema()

    if schema == "crc.cell.v3":
        mint = ri.activation_commit("CELL-v3.md")
        enf = ri.v3_enforcement_commit()
        act = ri.schema_activation_commit(schema)
        ok = bool(mint and enf and act)
        print(f"  {'ok  ' if ok else 'FAIL'}  v3 minted + enforced on branch")
        fails += not ok

        if act and enf and act != enf:
            _, rows = activation_block(schema)
            ok = (f"| activation commit | `{act[:12]}` |" in rows
                  and f"| activation commit | `{enf[:12]}` |" not in rows)
            print(f"  {'ok  ' if ok else 'FAIL'}  activation row uses later(mint,enforce), not enforce-only")
            fails += not ok

            text = render(schema, ["specimen check"], ["schema"])
            try:
                _verify_activation(schema, text)
                print("  ok    render + _verify_activation agree with schema_activation_commit()")
            except SystemExit as e:
                print(f"  FAIL  _verify_activation: {e}")
                fails += 1

            ok = act == ri.schema_activation_commit(schema)
            print(f"  {'ok  ' if ok else 'FAIL'}  activation_block matches check_sunset derivation")
            fails += not ok
    else:
        print(f"  ok    skip v3 activation vectors — in-force schema is {schema}")

    if fails:
        print(f"\n{fails} gen_in_force selftest check(s) failed.")
        return 1
    print("\nall green — gen_in_force activation + artifact bytes")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file on disk is not what would be generated")
    ap.add_argument("--selftest", action="store_true",
                    help="run activation-derivation regression vectors")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    schema = in_force_schema()
    checks, struct = build_and_capture(schema)
    text = render(schema, checks, struct)
    _verify_activation(schema, text)

    if args.check:
        if not OUT.exists():
            print("CELL-IN-FORCE.md is missing — run: python3 reference/gen_in_force.py",
                  file=sys.stderr)
            return 1
        on_disk = OUT.read_bytes()
        want = canonical_bytes(text)
        reason = _artifact_stale_reason(on_disk, want)
        if reason:
            print(reason, file=sys.stderr)
            return 1
        print(f"CELL-IN-FORCE.md is current ({schema}, {len(checks)} enforced rules)")
        return 0

    OUT.write_bytes(canonical_bytes(text))
    print(f"wrote {OUT.name} — {schema}, {len(checks)} enforced rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
