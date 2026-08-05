#!/usr/bin/env python3
"""crc.nodes.v0 validator — the mechanical review NODES.md promises.
Stdlib only. Exit 0 = conformant (merges), 1 = nonconformant.

    python3 validate_nodes.py [path/to/nodes.json]
"""
import json, re, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claim_id import loads_strict

NODE_FIELDS = {"node_id", "display", "verifier", "lane", "envelope",
               "key_ref", "cell_url_template", "since", "retired"}
KEY_FIELDS = {"pubkey", "address", "keys_url"}
SOURCE_FIELDS = {"source_id", "url", "admission", "lifts", "since", "retired"}
ENVELOPES = {"nostr-nip01", "eip712"}
RFC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{1,63}")

failures = []


def chk(label, cond):
    print(("  ok · " if cond else "  FAIL · ") + label)
    if not cond:
        failures.append(label)


def nonempty_str(v):
    return isinstance(v, str) and v != ""


def main(path):
    text = open(path).read()
    try:
        d = loads_strict(text)  # strict parse: duplicate members reject at any depth
        chk("strict parse, no duplicate members", True)
    except ValueError as e:
        chk(f"strict parse: {e}", False)
        return finish()

    chk("top-level exact field set", isinstance(d, dict) and set(d) == {"schema", "nodes", "claim_sources"})
    if failures: return finish()
    chk("schema crc.nodes.v0", d["schema"] == "crc.nodes.v0")
    chk("nodes is a non-empty list", isinstance(d["nodes"], list) and len(d["nodes"]) > 0)
    chk("claim_sources is a non-empty list", isinstance(d["claim_sources"], list) and len(d["claim_sources"]) > 0)
    if failures: return finish()

    seen_ids = set()
    for n in d["nodes"]:
        nid = n.get("node_id", "?") if isinstance(n, dict) else "?"
        chk(f"{nid}: exact field set", isinstance(n, dict) and set(n) == NODE_FIELDS)
        if not (isinstance(n, dict) and set(n) == NODE_FIELDS):
            continue
        chk(f"{nid}: node_id slug + unique", bool(SLUG.fullmatch(n["node_id"])) and n["node_id"] not in seen_ids)
        seen_ids.add(n["node_id"])
        chk(f"{nid}: display non-empty", nonempty_str(n["display"]))
        chk(f"{nid}: lane non-empty family/instance", nonempty_str(n["lane"]) and "/" in n["lane"])
        chk(f"{nid}: envelope valid", n["envelope"] in ENVELOPES)
        chk(f"{nid}: key_ref exact field set (null-not-absent)",
            isinstance(n["key_ref"], dict) and set(n["key_ref"]) == KEY_FIELDS)
        if isinstance(n["key_ref"], dict) and set(n["key_ref"]) == KEY_FIELDS:
            if n["envelope"] == "eip712":
                chk(f"{nid}: eip712 verifier is an address matching key_ref.address",
                    nonempty_str(n["verifier"]) and ADDR.fullmatch(n["verifier"]) is not None
                    and n["key_ref"]["address"] == n["verifier"])
            if n["envelope"] == "nostr-nip01":
                chk(f"{nid}: nostr key_ref.pubkey is hex-64",
                    nonempty_str(n["key_ref"]["pubkey"]) and HEX64.fullmatch(n["key_ref"]["pubkey"]) is not None)
                chk(f"{nid}: nostr verifier is an ERC-8004 token id (int)",
                    isinstance(n["verifier"], int) and not isinstance(n["verifier"], bool) and 0 <= n["verifier"] < 2**256)
        chk(f"{nid}: cell_url_template null or url with placeholder",
            n["cell_url_template"] is None
            or (nonempty_str(n["cell_url_template"]) and "{claim_id_hex}" in n["cell_url_template"]))
        chk(f"{nid}: since strict RFC3339 UTC", isinstance(n["since"], str) and bool(RFC.fullmatch(n["since"])))
        chk(f"{nid}: retired null or RFC3339", n["retired"] is None or (isinstance(n["retired"], str) and bool(RFC.fullmatch(n["retired"]))))

    seen_src = set()
    for s in d["claim_sources"]:
        sid = s.get("source_id", "?") if isinstance(s, dict) else "?"
        chk(f"{sid}: exact field set", isinstance(s, dict) and set(s) == SOURCE_FIELDS)
        if not (isinstance(s, dict) and set(s) == SOURCE_FIELDS):
            continue
        chk(f"{sid}: source_id slug + unique", bool(SLUG.fullmatch(s["source_id"])) and s["source_id"] not in seen_src)
        seen_src.add(s["source_id"])
        chk(f"{sid}: url + admission non-empty", nonempty_str(s["url"]) and nonempty_str(s["admission"]))
        chk(f"{sid}: lifts non-empty list of types", isinstance(s["lifts"], list) and len(s["lifts"]) > 0 and all(nonempty_str(x) for x in s["lifts"]))
        chk(f"{sid}: since strict RFC3339 UTC", isinstance(s["since"], str) and bool(RFC.fullmatch(s["since"])))
        chk(f"{sid}: retired null or RFC3339", s["retired"] is None or (isinstance(s["retired"], str) and bool(RFC.fullmatch(s["retired"]))))

    return finish()


def finish():
    if failures:
        print(f"\nNONCONFORMANT — {len(failures)} failure(s)")
        return 1
    print("\nCONFORMANT — merges per NODES.md contract")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "nodes.json")
    sys.exit(main(path))
