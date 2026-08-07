#!/usr/bin/env python3
"""Cell validator — the mechanical review for cells/{claim_id_hex}/{node_id}.cell.json.

Checks, per NODES.md + CELL-v1.md:
  1. strict parse (duplicate members reject)
  2. node_id registered in nodes.json, not retired; file in the right directory
  3. pre-hash gate on evidence.claim_preimage
  4. claim_id recomputes AND matches the directory name
  5. v1 time split: as_of == claim_preimage.as_of, recomputed_at present & distinct field
  6. envelope check:
       eip712      -> triple equality: recovered == signature.signer == proof_payload.verifier
                      == registered key_ref.address   (needs eth-account)
       nostr-nip01 -> NIP-01 id + BIP-340 schnorr vs registered key_ref.pubkey (stdlib bip340.py)
  7. evidence_hash recomputes (eip712 envelope)

    python3 validate_cell.py cells/<hex>/<node_id>.cell.json [--nodes nodes.json]
Exit 0 = valid, 1 = invalid.
"""
import json, hashlib, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from claim_id import loads_strict, validate as gate, claim_id as derive_claim_id
from registry_id import registry_id as this_registry_id
from lineage_ref import validate_derived_from, LineageRefError

# Schemas this validator accepts. Frozen versions stay verifiable forever
# (append-only discipline), so this list only ever grows.
KNOWN_SCHEMAS = ("crc.cell.v1", "crc.cell.v2", "crc.cell.v3")

# EIP-712 domain.version follows the repo's N-for-vN convention (CELL.md → "0",
# CELL-v1 → "1", CELL-v2 → "2", CELL-v3 §1.3 → "3").
DOMAIN_VERSION_FOR = {"crc.cell.v2": "2", "crc.cell.v3": "3"}
import bip340

failures = []


def chk(label, cond, detail=""):
    print(("  ok · " if cond else "  FAIL · ") + label + ((" — " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        failures.append(label)


def jcs(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def keccak256(data: bytes) -> bytes:
    from Crypto.Hash import keccak as _k  # pycryptodome; CI installs it
    h = _k.new(digest_bits=256); h.update(data); return h.digest()


def _check_lineage(pp):
    """CELL-v3.md §1.1 — derived_from is required, string[], no duplicates, no
    malformed element, no self-reference. Empty [] is valid and is NOT a
    LineageRef (LINEAGE-REF.md §4): it is a signed declaration of no known
    derivation, which is provenance and never proof of independence."""
    ind = (pp.get("evidence") or {}).get("independence") or {}
    if "derived_from" not in ind:
        chk("v3 evidence.independence.derived_from present", False,
            "absent — v3 requires it; use [] to declare no known derivation")
        return
    own = (ind.get("implementation") or {}).get("impl_hash")
    try:
        validate_derived_from(ind["derived_from"], own)
        n = len(ind["derived_from"])
        chk("v3 derived_from conforms (LINEAGE-REF.md §2)", True,
            "[] — declares no known derivation" if n == 0 else f"{n} lineage ref(s) declared")
    except LineageRefError as e:
        chk("v3 derived_from conforms (LINEAGE-REF.md §2)", False, str(e))


def validate(cell_path, nodes_path):
    nodes = loads_strict(open(nodes_path).read())
    text = open(cell_path).read()
    try:
        cell = loads_strict(text)
        chk("strict parse, no duplicate members", True)
    except ValueError as e:
        chk("strict parse", False, e); return

    # path pieces: cells/<hex64>/<node_id>.cell.json
    parts = os.path.normpath(cell_path).split(os.sep)
    fname = parts[-1]
    dirname = parts[-2] if len(parts) >= 2 else ""
    chk("directory is a 64-hex claim digest", bool(re.fullmatch(r"[0-9a-f]{64}", dirname)), dirname)
    m = re.fullmatch(r"(?P<nid>[a-z0-9][a-z0-9-]{1,63})\.cell\.json", fname)
    chk("filename is <node_id>.cell.json", m is not None, fname)
    if failures: return
    node = next((n for n in nodes["nodes"] if n["node_id"] == m["nid"]), None)
    chk("node registered in nodes.json", node is not None, m["nid"])
    if node is None: return
    chk("node not retired", node["retired"] is None)

    env = node["envelope"]
    if env == "eip712":
        chk("cell shape {proof_payload, signature, verify}", set(cell) >= {"proof_payload", "signature"})
        if failures: return
        pp, sg = cell["proof_payload"], cell["signature"]
        pre = pp["evidence"]["claim_preimage"]
        try:
            gate(pre); chk("pre-hash gate on claim_preimage", True)
        except ValueError as e:
            chk("pre-hash gate on claim_preimage", False, e); return
        cid = derive_claim_id(pre)
        chk("claim_id recomputes", cid == pp["claim_id"], cid)
        chk("claim_id matches directory", cid == "sha256:" + dirname)
        schema = pp.get("schema")
        chk("schema is a known crc.cell version", schema in KNOWN_SCHEMAS, schema)
        if schema in ("crc.cell.v2", "crc.cell.v3"):
            # CELL-v2.md §2: payload-primary registry binding is THE normative check.
            want = this_registry_id()
            chk("registry_id == this registry (payload-primary)", pp.get("registry_id") == want, pp.get("registry_id"))
            names = [f["name"] for f in sg["types"]["Cell"]]
            chk("EIP-712 struct carries registry_id", "registry_id" in names, names)
            want_dv = DOMAIN_VERSION_FOR[schema]
            chk(f"domain version is {want_dv}", str(sg["domain"].get("version")) == want_dv, sg["domain"].get("version"))
        if schema == "crc.cell.v3":
            _check_lineage(pp)
        chk("as_of binding (payload == preimage)", pp.get("as_of") == pre["as_of"])
        chk("recomputed_at present and a distinct field", isinstance(pp.get("recomputed_at"), str) and pp["recomputed_at"] != "")
        chk("boundary inside payload", isinstance(pp.get("boundary"), str) and pp["boundary"] != "")
        evh = "0x" + keccak256(jcs(pp["evidence"]).encode()).hex()
        chk("evidence_hash recomputes", evh.lower() == sg["evidence_hash"].lower(), evh)
        # triple equality + registry binding
        from eth_account.messages import encode_typed_data
        from eth_account import Account
        value = {f["name"]: (sg["evidence_hash"] if f["name"] == "evidence_hash" else pp[f["name"]])
                 for f in sg["types"]["Cell"]}
        full = {"types": {"EIP712Domain": [{"name": "name", "type": "string"},
                                           {"name": "version", "type": "string"},
                                           {"name": "chainId", "type": "uint256"}], **sg["types"]},
                "primaryType": "Cell", "domain": sg["domain"], "message": value}
        chk("signature grammar ^0x[0-9a-f]{130}$ (65-byte hex, 0x-prefixed)",
            bool(re.fullmatch(r"0x[0-9a-f]{130}", sg["signature"])), sg["signature"][:12])
        rec = Account.recover_message(encode_typed_data(full_message=full), signature=sg["signature"])
        chk("quadruple equality: recovered == signer == verifier == registered address",
            rec.lower() == sg["signer"].lower() == str(pp["verifier"]).lower() == node["key_ref"]["address"].lower(), rec)

    elif env == "nostr-nip01":
        chk("cell shape {event, …}", "event" in cell)
        if failures: return
        ev = cell["event"]
        try:
            pp = loads_strict(ev["content"])
            chk("content strict-parses", True)
        except ValueError as e:
            chk("content strict-parses", False, e); return
        pre = pp["evidence"]["claim_preimage"]
        try:
            gate(pre); chk("pre-hash gate on claim_preimage", True)
        except ValueError as e:
            chk("pre-hash gate on claim_preimage", False, e); return
        cid = derive_claim_id(pre)
        chk("claim_id recomputes", cid == pp["claim_id"], cid)
        chk("claim_id matches directory", cid == "sha256:" + dirname)
        schema = pp.get("schema")
        chk("schema is a known crc.cell version", schema in KNOWN_SCHEMAS, schema)
        if schema in ("crc.cell.v2", "crc.cell.v3"):
            # CELL-v2.md §2.3: the Nostr lane has no domain — only a field INSIDE the signed
            # content can bind the registry, which is why payload-primary is THE rule.
            want = this_registry_id()
            chk("registry_id == this registry (inside signed content)", pp.get("registry_id") == want, pp.get("registry_id"))
        if schema == "crc.cell.v3":
            _check_lineage(pp)
        chk("as_of binding (payload == preimage)", pp.get("as_of") == pre["as_of"])
        chk("boundary inside signed content", isinstance(pp.get("boundary"), str) and pp["boundary"] != "")
        ser = json.dumps([0, ev["pubkey"], ev["created_at"], ev["kind"], ev["tags"], ev["content"]],
                         separators=(",", ":"), ensure_ascii=False)
        eid = hashlib.sha256(ser.encode()).hexdigest()
        chk("NIP-01 event id recomputes", eid == ev["id"], eid)
        chk("schnorr verifies vs registered pubkey",
            ev["pubkey"] == node["key_ref"]["pubkey"] and bip340.verify_hex(ev["id"], ev["pubkey"], ev["sig"]))
        chk("verifier matches registration", pp.get("verifier") == node["verifier"])
    else:
        chk("known envelope", False, env)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    nodes_path = os.path.join(HERE, "..", "nodes.json")
    if "--nodes" in sys.argv:
        nodes_path = sys.argv[sys.argv.index("--nodes") + 1]
    validate(args[0], nodes_path)
    if failures:
        print(f"\nINVALID — {len(failures)} failure(s)"); sys.exit(1)
    print("\nVALID — Cell verifies under its envelope + the registry"); sys.exit(0)
