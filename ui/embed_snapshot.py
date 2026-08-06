#!/usr/bin/env python3
"""Regenerate the ui/index.html embedded registry snapshot (seed-registry) from
the repo's current nodes.json + claims/ + cells/ — run before any IPFS pin so
the offline fallback matches the registry at pin time. Live viewers always
prefer the fetched registry; the snapshot only serves when fetches fail."""
import json, os, re, sys

root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
snap = {"nodes": json.load(open(root + "/nodes.json")), "claims": {}, "cells": {}, "rejected": []}
for fn in sorted(os.listdir(root + "/claims")):
    if fn.endswith(".json") and not fn.startswith("."):
        snap["claims"][fn[:-5]] = json.load(open(root + "/claims/" + fn))
for d in sorted(os.listdir(root + "/cells")):
    p = root + "/cells/" + d
    if os.path.isdir(p) and d != "rejected":
        snap["cells"][d] = {}
        for cf in sorted(os.listdir(p)):
            if cf.endswith(".cell.json"):
                snap["cells"][d][cf.replace(".cell.json", "")] = json.load(open(p + "/" + cf))
rej = root + "/claims/rejected"
if os.path.isdir(rej):
    for fn in sorted(os.listdir(rej)):
        if fn.endswith(".json"):
            snap["rejected"].append(json.load(open(rej + "/" + fn)))

targets = sys.argv[1:] or [os.path.join(root, "ui", "index.html")]
blob = json.dumps(snap, separators=(",", ":"), ensure_ascii=False)
for t in targets:
    s = open(t).read()
    s2 = re.sub(r'(<script type="application/json" id="seed-registry">)[\s\S]*?(</script>)',
                lambda m: m.group(1) + blob + m.group(2), s, count=1)
    assert 'id="seed-registry"' in s2
    open(t, "w").write(s2)
    print(f"snapshot embedded -> {t} ({len(blob)//1024} KB, "
          f"{len(snap['claims'])} claims, {sum(len(v) for v in snap['cells'].values())} cells, "
          f"{len(snap['nodes']['nodes'])} nodes)")
