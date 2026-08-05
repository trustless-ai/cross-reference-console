#!/usr/bin/env python3
"""The claims watcher — ledger intake → pre-hash gate → claims/ registry.
Designed to run as a public GitHub Action (public logs = the audit trail for
the commit step; no member's box in the loop). Stdlib only.

lift.v0 (deterministic — anyone re-running it derives the same claim_id):
  input : an invinoveritas /ledger entry whose proof_event.content parses as
          invinoveritas.verdict_proof.v1 (decision_ref, verdict, policy_version,
          source_class, platform, verified_at present)
  output: ClaimPreimage {
    schema:           "crc.claim.v0",
    profile_id:       platform + ".review",
    policy_version:   lc.policy_version,
    artifact_hash:    lc.decision_ref stripped of "sha256:",
    artifact_type:    "review_verdict",
    claim_body:       lc.verdict,
    source_class:     lc.source_class,
    verifier_profile: "attestation/" + platform,
    as_of:            RFC3339 UTC of lc.verified_at (the verdict's own instant),
    claimant:         54848   # the issuing verifier's ERC-8004 id — constant for
  }                           # this intake (the claim is "this verifier issued this")

Admission (payment, at the ledger) never decides validity — the gate does.
Nonconforming-but-admitted entries land in claims/rejected/ WITH the gate error:
a rejection is a derivable fact, not a silent drop.

Watermark starts at 235 so #236 enters through the same pipeline as everything
after it — proven safe because lift.v0 derives the EXACT hand-minted claim_id
(sha256:df1a6bfe…) byte-for-byte: as_of = RFC3339(verified_at) is precisely how
the original claim was constructed. One rule, no special cases.
"""
import json, os, sys, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from claim_id import loads_strict, validate as gate, claim_id as derive_claim_id

LEDGER_INDEX = "https://api.babyblueviper.com/ledger"
LEDGER_ENTRY = "https://api.babyblueviper.com/ledger/{n}"
SOURCE_ID = "invinoveritas-ledger"
CLAIMANT = 54848
INITIAL_WATERMARK = 235
CLAIMS = os.path.join(ROOT, "claims")
REJECTED = os.path.join(CLAIMS, "rejected")
WATERMARK_FILE = os.path.join(CLAIMS, ".watermark.json")


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode()


def rfc3339(unix):
    return datetime.datetime.fromtimestamp(int(unix), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lift_v0(lc):
    return {
        "schema": "crc.claim.v0",
        "profile_id": lc["platform"] + ".review",
        "policy_version": lc["policy_version"],
        "artifact_hash": lc["decision_ref"].removeprefix("sha256:"),
        "artifact_type": "review_verdict",
        "claim_body": lc["verdict"],
        "source_class": lc["source_class"],
        "verifier_profile": "attestation/" + lc["platform"],
        "as_of": rfc3339(lc["verified_at"]),
        "claimant": CLAIMANT,
    }


def main():
    os.makedirs(REJECTED, exist_ok=True)
    watermark = INITIAL_WATERMARK
    if os.path.exists(WATERMARK_FILE):
        watermark = json.load(open(WATERMARK_FILE))["last_entry"]

    index = loads_strict(fetch(LEDGER_INDEX))
    numbers = sorted(e["entry"] for e in index["entries"] if isinstance(e, dict) and isinstance(e.get("entry"), int))
    todo = [n for n in numbers if n > watermark]
    print(f"watermark {watermark} · ledger head {numbers[-1] if numbers else '?'} · {len(todo)} new entr{'y' if len(todo)==1 else 'ies'}")

    changed = False
    for n in todo:
        try:
            entry = loads_strict(fetch(LEDGER_ENTRY.format(n=n)))
        except Exception as e:
            print(f"  #{n}: fetch failed ({e}) — stopping before watermark advance")
            break
        pe = entry.get("proof_event")
        lc = None
        if isinstance(pe, dict) and isinstance(pe.get("content"), str):
            try:
                parsed = loads_strict(pe["content"])
                if parsed.get("schema") == "invinoveritas.verdict_proof.v1" and all(
                        k in parsed for k in ("decision_ref", "verdict", "policy_version",
                                              "source_class", "platform", "verified_at")):
                    lc = parsed
            except ValueError as e:
                # a submission whose signed content doesn't even strict-parse is a rejection, not a skip
                out = os.path.join(REJECTED, f"entry-{n}.json")
                json.dump({"schema": "crc.rejected.v0", "source_id": SOURCE_ID, "entry": n,
                           "stage": "strict-parse", "error": str(e),
                           "source_url": LEDGER_ENTRY.format(n=n)}, open(out, "w"), indent=2)
                print(f"  #{n}: REJECTED (strict-parse: {e})"); changed = True
        if lc is None:
            if not os.path.exists(os.path.join(REJECTED, f"entry-{n}.json")):
                print(f"  #{n}: skip (not a liftable verdict proof — type {entry.get('type')!r})")
            watermark = n
            continue

        preimage = lift_v0(lc)
        try:
            gate(preimage)
            cid = derive_claim_id(preimage)
            hexdir = cid.removeprefix("sha256:")
            out = os.path.join(CLAIMS, hexdir + ".json")
            if os.path.exists(out):
                print(f"  #{n}: claim {cid[:18]}… already registered (idempotent)")
            else:
                json.dump({"schema": "crc.claimfile.v0", "claim_id": cid,
                           "claim_preimage": preimage,
                           "lift": {"rule": "lift.v0", "source_id": SOURCE_ID, "entry": n},
                           "source_url": LEDGER_ENTRY.format(n=n)},
                          open(out, "w"), indent=2, ensure_ascii=False)
                print(f"  #{n}: CLAIM {cid[:18]}… registered"); changed = True
        except ValueError as e:
            out = os.path.join(REJECTED, f"entry-{n}.json")
            json.dump({"schema": "crc.rejected.v0", "source_id": SOURCE_ID, "entry": n,
                       "stage": "pre-hash-gate", "error": str(e), "lift_attempt": preimage,
                       "source_url": LEDGER_ENTRY.format(n=n)}, open(out, "w"), indent=2, ensure_ascii=False)
            print(f"  #{n}: REJECTED (gate: {e})"); changed = True
        watermark = n

    json.dump({"schema": "crc.watermark.v0", "source_id": SOURCE_ID, "last_entry": watermark},
              open(WATERMARK_FILE, "w"), indent=2)
    print(f"watermark -> {watermark} · {'changes to commit' if changed else 'no registry changes'}")


if __name__ == "__main__":
    main()
