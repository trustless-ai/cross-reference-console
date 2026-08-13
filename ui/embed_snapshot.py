#!/usr/bin/env python3
"""Regenerate the ui/index.html embedded registry snapshot (seed-registry) from
the repo's current nodes.json + claims/ + cells/ — run before any IPFS pin so
the offline fallback matches the registry at pin time. Live viewers always
prefer the fetched registry; the snapshot only serves when fetches fail."""
import json, os, re, sys

root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
snap = {"nodes": json.load(open(root + "/nodes.json")), "claims": {}, "cells": {}, "rejected": []}
# Advisory, and kept OUT of snap["nodes"] on purpose: frozen crc.nodes.v0 stays
# frozen, so affiliation must not ride inside the registry object even here.
try:
    snap["affiliations"] = json.load(open(root + "/affiliations.json"))["affiliations"]
except Exception:
    snap["affiliations"] = {}
for fn in sorted(os.listdir(root + "/claims")):
    if fn.endswith(".json") and not fn.startswith("."):
        snap["claims"][fn[:-5]] = json.load(open(root + "/claims/" + fn))
for d in sorted(os.listdir(root + "/cells")):
    p = root + "/cells/" + d
    if os.path.isdir(p) and d != "rejected":
        snap["cells"][d] = {}
        for cf in sorted(os.listdir(p)):
            if cf.endswith(".cell.json"):
                # removesuffix, not replace: replace() strips EVERY occurrence, so a
                # node_id that itself contains ".cell.json" would be silently truncated.
                snap["cells"][d][cf.removesuffix(".cell.json")] = json.load(open(p + "/" + cf))
rej = root + "/claims/rejected"
if os.path.isdir(rej):
    for fn in sorted(os.listdir(rej)):
        if fn.endswith(".json"):
            snap["rejected"].append(json.load(open(rej + "/" + fn)))

targets = sys.argv[1:] or [os.path.join(root, "ui", "index.html")]
import hashlib
canonical = json.dumps(snap, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

# crc.console-snapshot.v1 — `data_as_of` replaces v0's `generated_at`.
#
# v0 stamped wall-clock build time, which made the page unreproducible: the same
# repo state built twice produced different bytes and therefore a different IPFS
# CID. That is fine for a page one person pins, and fatal for a page anyone may
# pin — a CID handed to us could not be checked against main, and the console's
# embedded snapshot is the matrix's PRIMARY source, so a doctored build could
# show fabricated nodes and GREEN cells on the org's own domain. The contenthash
# is the one pointer in this stack that is not recomputable; the build feeding it
# should at least be.
#
# So the timestamp is now derived from the data: the newest observation the
# snapshot actually contains. It answers the question a reader has ("how current
# is this?") instead of the one they don't ("when did someone run a script?"),
# and it makes the whole build a pure function of repo state.
_stamps = re.findall(r'"(20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ)"', canonical)
data_as_of = max(_stamps) if _stamps else "1970-01-01T00:00:00Z"

wrapped = {"schema": "crc.console-snapshot.v1",
           "data_as_of": data_as_of,
           "digest": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
           "data": snap}
blob = json.dumps(wrapped, separators=(",", ":"), ensure_ascii=False)

# The join instruction names the schema a newcomer must sign. Hand-written, it
# was still saying crc.cell.v1 two schema versions later — correct when typed and
# wrong with no commit touching it, the same failure mode as a stale image path.
# So derive it here from the CELL-vN.md files, exactly as gen_in_force.py and
# check_sunset.py do, and let the build stamp it in.
_versions = [int(m.group(1)) for f in os.listdir(root)
             if (m := re.fullmatch(r"CELL-v(\d+)\.md", f))]
in_force = f"crc.cell.v{max(_versions)}" if _versions else "crc.cell.v2"

# The state -> marker mapping lives in ui/lineage-marker.js so a conformance gate can
# import it and assert what a human actually sees. The page must run that exact code, not
# a copy of it: a copy drifts, and then the tested function and the shipped function are
# different functions with the same name. console.lock installs a single artifact, so it
# is inlined here rather than shipped beside the page, and check_console_reproducible.py
# fails the moment the two diverge.
marker_src = open(os.path.join(root, "ui", "lineage-marker.js"), encoding="utf-8").read().strip()

for t in targets:
    s = open(t, encoding="utf-8").read()
    s, n = re.subn(
        r"(/\* BEGIN lineage-marker\.js[\s\S]*?\*/\n)[\s\S]*?(/\* END lineage-marker\.js \*/)",
        lambda m: m.group(1) + marker_src + "\n" + m.group(2), s, count=1)
    # Refuse to write a page whose marker region we could not find: silently shipping the
    # previous copy is exactly the drift this block exists to prevent.
    assert n == 1, f"lineage-marker region not found in {t} (found {n}) — refusing to write"
    s2 = re.sub(r'(<script type="application/json" id="seed-registry">)[\s\S]*?(</script>)',
                lambda m: m.group(1) + blob + m.group(2), s, count=1)
    assert 'id="seed-registry"' in s2
    s2, n = re.subn(r'(<b id="in-force-schema">)crc\.cell\.v\d+(</b>)',
                    lambda m: m.group(1) + in_force + m.group(2), s2)
    # Fail loudly rather than pin a page that names a sunset schema.
    assert n == 1, f"in-force-schema marker not found in {t} (found {n}) — refusing to write"
    open(t, "w", encoding="utf-8", newline="\n").write(s2)
    print(f"snapshot embedded -> {t} ({len(blob)//1024} KB, {wrapped['digest'][:18]}…, "
          f"{len(snap['claims'])} claims, {sum(len(v) for v in snap['cells'].values())} cells, "
          f"{len(snap['nodes']['nodes'])} nodes)")
