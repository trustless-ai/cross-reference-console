#!/usr/bin/env python3
"""Vectors for the currency verdict — site-tree vs site-tree.

PIN-RECORD.md's Currency section is only as good as a check that can actually
report STALE. The comparison is the landing site-tree at HEAD against the
resolved ENS contenthash (a directory CID), not a file CID of this repo's
`ui/index.html`. A suite that only mocked CURRENT would not have proven the
fail path; a live run that compared the wrong artifact would have reported
STALE forever for the wrong reason.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_console_currency as cur  # noqa: E402
import verify_pin  # noqa: E402

fails = 0

LIVE_PIN_CID = "bafybeiblwwa2wnbftf4nu3byvzprxlz5odmojawms7iv2fxdcnoscpdvya"
# Directory-CID shape (bafy…), not a file CID (bafkrei…).
SITE_CID_FIXTURE = "bafybeicurrentfixture00000000000000000000000000000000000"
OTHER_SITE_CID = "bafybeistalefixture0000000000000000000000000000000000000"


def check(label: str, cond: bool, detail: str = "") -> None:
    global fails
    if cond:
        print(f"  ok    {label}")
    else:
        fails += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


def mocked_current():
    print("\nmocked CURRENT — same *site-tree* CID on both sides:")
    result = cur.evaluate(
        resolve=lambda: (SITE_CID_FIXTURE, None),
        ipfs_present=lambda: True,
        build=lambda params: SITE_CID_FIXTURE,
    )
    check("verdict is CURRENT", result.verdict == cur.CURRENT)
    check("no reason field on CURRENT", result.reason is None)
    check("CURRENT is the only pass (exit 0)", result.exit_code == 0)
    check("does not invent a pin when the CID is synthetic",
          result.pin_path is None)
    check("mocked build is a directory CID, not a file CID",
          SITE_CID_FIXTURE.startswith("bafy")
          and not SITE_CID_FIXTURE.startswith("bafkrei"))
    check("mocked CURRENT does not invent a range from this repo",
          result.range is None)


def mocked_stale():
    print("\nmocked STALE — two different site-tree CIDs:")
    result = cur.evaluate(
        resolve=lambda: (LIVE_PIN_CID, None),
        ipfs_present=lambda: True,
        build=lambda params: OTHER_SITE_CID,
    )
    check("verdict is STALE", result.verdict == cur.STALE)
    check("names the resolved contenthash CID", result.resolved_cid == LIVE_PIN_CID)
    check("names the site-tree CID", result.main_cid == OTHER_SITE_CID)
    check("the two CIDs differ", result.resolved_cid != result.main_cid)
    check("matched the pin record for the resolved CID",
          result.pin_path is not None and result.pin_path.endswith(LIVE_PIN_CID + ".json"),
          str(result.pin_path))
    check("STALE is a determinate fail (exit 1)", result.exit_code == 1)
    check("mocked STALE does not silently report this repo's commit range",
          result.range is None)


def undetermined_resolver():
    print("\nUNDETERMINED — resolver_unreachable:")
    result = cur.evaluate(
        resolve=lambda: (None, cur.REASON_RESOLVER),
        ipfs_present=lambda: True,
        build=lambda params: "should-not-be-called",
    )
    check("verdict is UNDETERMINED", result.verdict == cur.UNDETERMINED)
    check("reason is resolver_unreachable", result.reason == cur.REASON_RESOLVER)
    check("not CURRENT and not STALE", result.verdict not in (cur.CURRENT, cur.STALE))
    check("don't-act (exit 1, never a silent not-current)", result.exit_code == 1)
    check("no main CID was computed", result.main_cid is None)


def undetermined_no_ipfs():
    print("\nUNDETERMINED — no_local_ipfs:")
    result = cur.evaluate(
        resolve=lambda: (LIVE_PIN_CID, None),
        ipfs_present=lambda: False,
        build=lambda params: (_ for _ in ()).throw(AssertionError("build must not run")),
    )
    check("verdict is UNDETERMINED", result.verdict == cur.UNDETERMINED)
    check("reason is no_local_ipfs", result.reason == cur.REASON_IPFS)
    check("not CURRENT and not STALE", result.verdict not in (cur.CURRENT, cur.STALE))
    check("resolved CID is still reported", result.resolved_cid == LIVE_PIN_CID)
    check("don't-act (exit 1)", result.exit_code == 1)


def undetermined_build_failed():
    print("\nUNDETERMINED — site-tree CID could not be produced:")
    result = cur.evaluate(
        resolve=lambda: (LIVE_PIN_CID, None),
        ipfs_present=lambda: True,
        build=lambda params: None,
    )
    check("verdict is UNDETERMINED", result.verdict == cur.UNDETERMINED)
    check("reason is no_local_ipfs (could-not-produce-the-CID bucket)",
          result.reason == cur.REASON_IPFS)
    check("not a silent STALE", result.verdict != cur.STALE)
    check("don't-act (exit 1)", result.exit_code == 1)


def pin_lookup():
    print("\npin lookup against committed records:")
    hit = cur.pin_for_cid(LIVE_PIN_CID)
    check("finds the 2026-08-10 pin by CID", hit is not None)
    if hit:
        path, rec = hit
        check("record cid matches", rec.get("cid") == LIVE_PIN_CID)
        check("record commit is 4e9d6af…", rec.get("commit", "").startswith("4e9d6af"))
        check("record is a site-tree", rec.get("artifact_kind") == "site-tree")
    miss = cur.pin_for_cid("bafybeianotapinrecord0000000000000000000000000000000")
    check("unknown CID returns no record", miss is None)


def normalize_vectors():
    print("\nCID normalisation:")
    check("strips ipfs://",
          cur.normalize_cid("ipfs://bafybeiabc") == "bafybeiabc")
    check("strips /ipfs/",
          cur.normalize_cid("/ipfs/bafybeiabc") == "bafybeiabc")
    check("empty is None", cur.normalize_cid("") is None)


def allowlist_is_verify_pins():
    print("\nallowlist is verify_pin.ALLOWED_SITE_REPOS, not a second copy:")
    check("allowlisted_site_repo() with no name returns the single allowlisted repo",
          cur.allowlisted_site_repo() in verify_pin.ALLOWED_SITE_REPOS)
    named = next(iter(verify_pin.ALLOWED_SITE_REPOS))
    check("an allowlisted name is accepted",
          cur.allowlisted_site_repo(named) == named)
    check("the same name with .git is accepted",
          cur.allowlisted_site_repo(named + ".git") == named)
    check("an unknown repo is refused — we do not execute it",
          cur.allowlisted_site_repo("https://github.com/evil/not-ours") is None)
    check("this checker does not keep its own ALLOWED_SITE_REPOS",
          not hasattr(cur, "ALLOWED_SITE_REPOS"))


def landing_range_fixture():
    print("\nlanding commit range is computed in a landing clone, not this repo:")
    with tempfile.TemporaryDirectory() as td:
        site = pathlib.Path(td)
        subprocess.run(["git", "init"], cwd=site, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=site,
                       check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=site,
                       check=True, capture_output=True)
        (site / "f").write_text("a")
        subprocess.run(["git", "add", "f"], cwd=site, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", "one"], cwd=site, check=True,
                       capture_output=True)
        pin = subprocess.run(["git", "rev-parse", "HEAD"], cwd=site,
                             capture_output=True, text=True, check=True
                             ).stdout.strip()
        (site / "f").write_text("b")
        subprocess.run(["git", "add", "f"], cwd=site, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", "two"], cwd=site, check=True,
                       capture_output=True)
        (site / "f").write_text("c")
        subprocess.run(["git", "add", "f"], cwd=site, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", "three"], cwd=site, check=True,
                       capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=site,
                              capture_output=True, text=True, check=True
                              ).stdout.strip()

        rng = cur.landing_commit_range(
            site, {"commit": pin}, repo="https://example/landing",
        )
        check("count is 2 (two commits after the pin)", rng.get("count") == 2,
              str(rng.get("count")))
        check("from is the pin", rng.get("from") == pin)
        check("to is landing HEAD", rng.get("to") == head)
        check("basis names the landing rev-list, not this repo",
              rng.get("basis") == "git rev-list pinned..HEAD (landing)")
        check("repo field is the landing repo",
              rng.get("repo") == "https://example/landing")

        empty = cur.landing_commit_range(site, {"commit": head})
        check("pin == HEAD yields an empty range, not this repo's log",
              empty.get("count") == 0, str(empty.get("count")))

        missing = cur.landing_commit_range(
            site, {"commit": "deadbeef" * 5},
        )
        check("unknown pin commit is 'not computed', not this repo's log",
              missing.get("basis") == cur.RANGE_NOT_COMPUTED
              and missing.get("count") is None,
              str(missing))

    this_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=cur.ROOT,
    ).stdout.strip()
    check("the fixture HEADs are not this (console) repo's HEAD",
          head != this_head and pin != this_head)


def live_control():
    """Real ENS contenthash vs a real clone of trustless-ai-landing at HEAD."""
    print("\nlive control — real ENS vs real landing-HEAD site-tree:")
    result = cur.evaluate()
    check("not UNDETERMINED — both CIDs were produced",
          result.verdict in (cur.CURRENT, cur.STALE),
          f"got {result.verdict} reason={result.reason} detail={result.detail}")
    if result.verdict not in (cur.CURRENT, cur.STALE):
        return
    check("names the resolved contenthash CID", bool(result.resolved_cid))
    check("names the landing site-tree CID", bool(result.main_cid))
    check("resolved CID is the live 2026-08-10 pin",
          result.resolved_cid == LIVE_PIN_CID, str(result.resolved_cid))
    check("matched the pin record for that CID",
          result.pin_path is not None and result.pin_path.endswith(
              LIVE_PIN_CID + ".json"),
          str(result.pin_path))
    check("pin commit is 4e9d6af…",
          (result.pin_commit or "").startswith("4e9d6af"),
          str(result.pin_commit))
    check("site-tree CID is a directory CID (bafy…), not a file CID (bafkrei…)",
          (result.main_cid or "").startswith("bafy")
          and not (result.main_cid or "").startswith("bafkrei"),
          str(result.main_cid))
    check("range was computed from the landing clone",
          isinstance(result.range, dict)
          and result.range.get("basis") == "git rev-list pinned..HEAD (landing)",
          str(result.range))
    if result.range:
        check("range.to is a landing commit, not silently this repo's HEAD",
              isinstance(result.range.get("to"), str)
              and len(result.range["to"]) == 40)
        this_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=cur.ROOT,
        ).stdout.strip()
        # Landing HEAD is currently the pin (4e9d6af). This console's HEAD is
        # not. If they ever coincide it would be coincidence; the assertion
        # that matters is the basis string above. Still flag a silent swap
        # if range.to equals this repo AND not the pin — that would mean we
        # walked the wrong tree.
        pin = result.pin_commit or ""
        check("range.to is not this console repo's HEAD (unless that is also the pin)",
              result.range.get("to") != this_head
              or this_head.startswith(pin[:12]),
              f"range.to={result.range.get('to')} this={this_head}")

    if result.verdict == cur.STALE:
        check("the two CIDs differ — genuinely, site-tree vs site-tree",
              result.resolved_cid != result.main_cid,
              f"{result.resolved_cid} == {result.main_cid}")
        check("STALE is a determinate fail (exit 1)", result.exit_code == 1)
        rendered = cur._fmt_range(result.range)
        check("range formatter names landing",
              "landing" in rendered, rendered)
        print(f"  note  live verdict is STALE")
        print(f"        resolved {result.resolved_cid}")
        print(f"        landing  {result.main_cid}")
        print(f"        range    {rendered}")
    else:
        check("the two CIDs match — landing HEAD still is the pinned site-tree",
              result.resolved_cid == result.main_cid,
              f"{result.resolved_cid} != {result.main_cid}")
        check("CURRENT is the only pass (exit 0)", result.exit_code == 0)
        check("range count is 0 — landing HEAD has not moved past the pin",
              (result.range or {}).get("count") == 0,
              str((result.range or {}).get("count")))
        print(f"  note  live verdict is CURRENT (landing HEAD == pin {result.pin_commit[:12] if result.pin_commit else '?'})")
        print(f"        cid {result.resolved_cid}")


if __name__ == "__main__":
    print("currency verdict — site-tree vs site-tree")
    normalize_vectors()
    pin_lookup()
    allowlist_is_verify_pins()
    landing_range_fixture()
    mocked_current()
    mocked_stale()
    undetermined_resolver()
    undetermined_no_ipfs()
    undetermined_build_failed()
    live_control()
    print()
    print("all green — currency check vectors" if not fails else f"{fails} FAILURE(S)")
    raise SystemExit(1 if fails else 0)
