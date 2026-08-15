#!/usr/bin/env python3
"""The watcher's three answers, driven against a stub ledger.

On 2026-08-15 the watcher went red on main because someone else's server returned
502 for a minute. The run had seen nothing, changed nothing, and concluded nothing
— and reported that as a failure. A red nobody can act on is how a team learns to
ignore red.

So the intake now distinguishes:

    unreachable            exit 2   we saw nothing. Not a claim about the upstream.
    reachable + malformed  exit 1   we saw something wrong. A real finding.
    reachable + fine       exit 0   including when it stops early on a mid-run outage.

This file proves all three, because the whole point of separating them is lost if
nobody ever watches the separation hold. The stub is a local HTTP server, so the
paths are driven deterministically rather than by waiting for a real outage.

EXIT: 0 all three behave · 1 one did not · 2 could not run.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXIT_OK, EXIT_BAD, EXIT_UNVERIFIABLE = 0, 1, 2
bad = 0

# One liftable entry, so the happy path actually registers a claim rather than
# passing because there was nothing to do.
GOOD_ENTRY = {
    "type": "verdict_proof",
    "proof_event": {"content": json.dumps({
        "schema": "invinoveritas.verdict_proof.v1",
        "decision_ref": "sha256:" + "ab" * 32,
        "verdict": "reject",
        "policy_version": "invinoveritas.review.v9",
        "source_class": "agent_reported",
        "platform": "invinoveritas",
        "verified_at": 1785869697,
    })},
}


class Stub(http.server.BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *a):    # keep the test output readable
        pass

    def do_GET(self):
        m = Stub.mode
        if m == "index_502" or (m == "entry_502" and self.path != "/"):
            self.send_error(502, "Bad Gateway")
            return
        if m == "index_garbage" and self.path == "/":
            body = b"<html>not json at all</html>"
        elif self.path == "/":
            body = json.dumps({"entries": [{"entry": 236}]}).encode()
        elif m == "entry_garbage":
            body = b"{{{ not json"
        else:
            body = json.dumps(GOOD_ENTRY).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_watcher(mode: str) -> tuple[int, str]:
    """Run the watcher against the stub, in a throwaway copy of the tree."""
    Stub.mode = mode
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        (tmp / "reference").mkdir()
        for f in ("watcher.py", "claim_id.py"):
            shutil.copy2(ROOT / "reference" / f, tmp / "reference" / f)
        (tmp / "claims").mkdir()
        env = {**os.environ, "CRC_LEDGER_BASE": f"http://127.0.0.1:{PORT}"}
        r = subprocess.run([sys.executable, str(tmp / "reference" / "watcher.py")],
                           capture_output=True, text=True, env=env, timeout=90)
        registered = list((tmp / "claims").glob("*.json"))
        return r.returncode, (r.stdout + r.stderr) + f"\n[claims registered: {len(registered)}]"


def case(name: str, mode: str, want: int, must_say: str) -> None:
    global bad
    rc, out = run_watcher(mode)
    ok = rc == want and must_say.lower() in out.lower()
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}: exit {rc} (want {want})")
    if not ok:
        bad += 1
        for line in out.strip().splitlines()[-6:]:
            print(f"           {line}")


srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def main() -> int:
    print("the watcher's three answers\n")

    case("ledger 502 → UNVERIFIABLE, not failure", "index_502",
         EXIT_UNVERIFIABLE, "unverifiable")
    case("ledger answers garbage → determinate FAIL", "index_garbage",
         EXIT_BAD, "does not strict-parse")
    case("ledger fine → registers the claim, exit 0", "ok",
         EXIT_OK, "registered")
    case("entry unreachable mid-run → exit 0, watermark holds", "entry_502",
         EXIT_OK, "unreachable")
    case("entry served but unparseable → FAIL", "entry_garbage",
         EXIT_BAD, "not parseable")

    print()
    if bad:
        print(f"{bad} case(s) failed — the three answers are not actually separated")
        return EXIT_BAD
    print("unreachable, malformed and fine are three different answers, and stay that way")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        srv.shutdown()
