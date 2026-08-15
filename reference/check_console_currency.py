#!/usr/bin/env python3
"""Is trustless-ai.eth's contenthash the CID of a fresh landing site-tree?

Pin records prove a CID was honestly derived from a commit. They do not prove
the ENS contenthash still points at that CID. This is the second verdict
PIN-RECORD.md names Currency.

The contenthash is a *directory* CID of the whole published landing site, not
a file CID of this repo's `ui/index.html`. The comparison is therefore the
same computation `verify_pin.py`'s `site-tree` branch already knows how to
run — clone an allowlisted repo, `build/sync_console.py --check`,
`build/site_cid.py --json` — but against landing HEAD rather than a pinned
commit. That is "what would a fresh build of the landing site look like
today", compared to what ENS actually points at.

Three outcomes, and the third is not optional:

    CURRENT        resolved contenthash CID == directory CID of the
                   landing site-tree at HEAD
    STALE          both were computed and they differ — determinate. Names
                   both CIDs and the commit range on the *landing* repo
                   between the pinned commit and landing HEAD.
    UNDETERMINED   could not be computed. Required reason:
                     resolver_unreachable | no_local_ipfs
                   Never a silent not-current. A failed
                   `sync_console --check` is this too: there is then no
                   trustworthy site-tree CID to compare (the tree has
                   drifted from its sources). Same bucket as "could not
                   produce the CID", not a silent STALE.

Consumer rule, verbatim from PIN-RECORD.md:

    CURRENT is the only pass. STALE is a determinate fail naming both CIDs
    and the range. UNDETERMINED is don't-act, never a silent not-current.

    python3 reference/check_console_currency.py
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_pin  # noqa: E402

ROOT = verify_pin.ROOT
PINS = ROOT / "pins"
ENS_NAME = "trustless-ai.eth"
ENSDATA_URL = "https://api.ensdata.net/{name}"
RESOLVE_TIMEOUT_S = 15
CLONE_TIMEOUT_S = 180
BUILD_TIMEOUT_S = 180

GREEN, AMBER, RED = verify_pin.GREEN, verify_pin.AMBER, verify_pin.RED

CURRENT, STALE, UNDETERMINED = "CURRENT", "STALE", "UNDETERMINED"
REASON_RESOLVER = "resolver_unreachable"
REASON_IPFS = "no_local_ipfs"

# Range that was not computed from a landing clone. Never filled in from
# this (cross-reference-console) repo's git log — that is a different tree.
RANGE_NOT_COMPUTED = "not computed"


@dataclass
class CurrencyResult:
    verdict: str
    reason: Optional[str] = None
    resolved_cid: Optional[str] = None
    main_cid: Optional[str] = None
    pin_path: Optional[str] = None
    pin_commit: Optional[str] = None
    pin_at: Optional[str] = None
    range: Optional[dict[str, Any]] = None
    detail: Optional[str] = None
    rows: list[tuple[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        # Same convention as verify_pin: 0 only for a real pass (CURRENT /
        # GREEN). STALE is a determinate fail. UNDETERMINED is could-not-check
        # and is never a pass — matching AMBER → 1.
        return 0 if self.verdict == CURRENT else 1


@dataclass
class SiteTreeBuild:
    """Outcome of reproducing the landing site-tree at HEAD."""
    cid: Optional[str] = None
    head: Optional[str] = None
    repo: Optional[str] = None
    range: Optional[dict[str, Any]] = None
    error: Optional[str] = None


def normalize_cid(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    for prefix in ("ipfs://", "/ipfs/", "ipns://", "/ipns/"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.split("/")[0].strip()
    return s or None


def resolve_ens_contenthash(
    name: str = ENS_NAME,
    urlopen: Callable = urllib.request.urlopen,
) -> tuple[Optional[str], Optional[str]]:
    """Return (cid, None) or (None, REASON_RESOLVER). Never raises."""
    url = ENSDATA_URL.format(name=name)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "crc-check-console-currency/1.0 (+https://github.com/trustless-ai/cross-reference-console)"},
    )
    try:
        with urlopen(req, timeout=RESOLVE_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError, ValueError):
        return None, REASON_RESOLVER
    cid = normalize_cid(
        data.get("contentHash")
        or data.get("contenthash")
        or data.get("content_hash")
    )
    if not cid:
        return None, REASON_RESOLVER
    return cid, None


def load_pin_records() -> list[tuple[pathlib.Path, dict]]:
    if not PINS.is_dir():
        return []
    out = []
    for p in sorted(PINS.glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict) and rec.get("cid"):
            out.append((p, rec))
    return out


def pin_for_cid(cid: str) -> Optional[tuple[pathlib.Path, dict]]:
    want = normalize_cid(cid)
    for path, rec in load_pin_records():
        if normalize_cid(rec.get("cid")) == want:
            return path, rec
    return None


def newest_pin() -> Optional[tuple[pathlib.Path, dict]]:
    """Latest record that actually has a pinned_at, else the last by filename."""
    recs = load_pin_records()
    dated = [(p, r) for p, r in recs if r.get("pinned_at")]
    if dated:
        dated.sort(key=lambda pr: pr[1]["pinned_at"])
        return dated[-1]
    return recs[-1] if recs else None


def cid_params_from(rec: Optional[dict]) -> dict:
    if rec and rec.get("cid_params"):
        return dict(rec["cid_params"])
    return {"cid_version": 1}


def have_ipfs() -> bool:
    return shutil.which("ipfs") is not None


def allowlisted_site_repo(named: Optional[str] = None) -> Optional[str]:
    """Repo whose build code we are willing to execute.

    The allowlist lives in verify_pin on purpose — a pin record is untrusted
    input, and this checker must not keep a second copy that can drift.
    `named` is accepted only when it is already on that list; otherwise we
    refuse rather than fall through to "whatever is allowlisted" (a record
    pointing elsewhere must not quietly run a different repo's build).
    With no name, the single allowlisted repo is the site we check currency
    against.
    """
    allowed = verify_pin.ALLOWED_SITE_REPOS
    if named:
        canon = named.rstrip("/").removesuffix(".git")
        return canon if canon in allowed else None
    if len(allowed) == 1:
        return next(iter(allowed))
    return None


def _git(args: list[str], cwd: pathlib.Path, timeout: int = BUILD_TIMEOUT_S):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=cwd, timeout=timeout,
    )


def landing_commit_range(
    site: pathlib.Path,
    pin_rec: Optional[dict],
    repo: Optional[str] = None,
) -> dict[str, Any]:
    """Pinned commit → landing HEAD, computed *in the landing clone*.

    Never consults this (cross-reference-console) repo. If the pin commit
    is not in the landing tree, the range is not invented from somewhere
    else — it is reported as not computed.
    """
    head_r = _git(["rev-parse", "HEAD"], site)
    head = head_r.stdout.strip() if head_r.returncode == 0 else None
    pinned = (pin_rec or {}).get("commit") or ""
    base = {
        "from": pinned or None,
        "to": head,
        "count": None,
        "first": None,
        "last": None,
        "commits": None,
        "basis": RANGE_NOT_COMPUTED,
        "repo": repo,
    }
    if not pinned or not head:
        return base
    probe = _git(["cat-file", "-t", pinned], site)
    if probe.returncode != 0:
        return base
    r = _git(["rev-list", "--reverse", f"{pinned}..HEAD"], site)
    if r.returncode != 0:
        return base
    shas = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return {
        "from": pinned,
        "to": head,
        "count": len(shas),
        "first": shas[0] if shas else None,
        "last": shas[-1] if shas else None,
        "commits": shas,
        "basis": "git rev-list pinned..HEAD (landing)",
        "repo": repo,
    }


def build_site_tree(pin_rec: Optional[dict] = None) -> SiteTreeBuild:
    """Reproduce verify_pin's site-tree computation against landing HEAD.

    Clone the allowlisted repo, check out HEAD (not the pin commit), refuse
    a CID if `sync_console --check` fails, then take `site_cid.py --json`'s
    `cid`. `site_cid.py` itself returns cid=None (exit 0) when there is no
    usable `ipfs` — same tolerance as verify_pin's site-tree branch.
    """
    named = (pin_rec or {}).get("repo")
    repo = allowlisted_site_repo(named)
    if repo is None:
        return SiteTreeBuild(error="repo_not_allowlisted")

    with tempfile.TemporaryDirectory() as td:
        site = pathlib.Path(td) / "site"
        try:
            r = subprocess.run(
                ["git", "clone", "--quiet", "--no-checkout",
                 repo + ".git", str(site)],
                capture_output=True, text=True, timeout=CLONE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return SiteTreeBuild(repo=repo, error="clone_failed")
        if r.returncode != 0:
            return SiteTreeBuild(repo=repo, error="clone_failed")

        r = _git(["checkout", "--quiet", "HEAD"], site)
        if r.returncode != 0:
            return SiteTreeBuild(repo=repo, error="checkout_failed")

        rng = landing_commit_range(site, pin_rec, repo=repo)
        head = rng.get("to")

        try:
            c = subprocess.run(
                [sys.executable, "build/sync_console.py", "--check"],
                capture_output=True, text=True, cwd=site, timeout=BUILD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="sync_console",
            )
        if c.returncode != 0:
            # verify_pin reports RED here because it is checking an already-
            # committed pin. Nothing is committed yet: we asked for the CID
            # of a consistent fresh build, and the tree has drifted from its
            # sources. Computing site_cid.py against that drifted tree would
            # be a different claim (and could false-CURRENT if the drifted
            # bytes happen to be what ENS already points at).
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="sync_console",
            )

        try:
            s = subprocess.run(
                [sys.executable, "build/site_cid.py", "--json"],
                capture_output=True, text=True, cwd=site, timeout=BUILD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="site_cid",
            )
        if s.returncode != 0:
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="site_cid",
            )
        try:
            got = json.loads(s.stdout)
        except json.JSONDecodeError:
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="site_cid",
            )
        cid = got.get("cid")
        # site_cid.py returns cid=None (and exits 0) when there is no usable
        # ipfs — "directory CID not recomputed", same as verify_pin.
        if cid is None:
            return SiteTreeBuild(
                head=head, repo=repo, range=rng, error="no_ipfs",
            )
        return SiteTreeBuild(cid=cid, head=head, repo=repo, range=rng)


def build_main_cid(pin_rec: Optional[dict] = None) -> Optional[str]:
    """Directory CID of the landing site-tree at HEAD, or None."""
    return build_site_tree(pin_rec).cid


def evaluate(
    *,
    resolve: Optional[Callable[[], tuple[Optional[str], Optional[str]]]] = None,
    ipfs_present: Optional[Callable[[], bool]] = None,
    build: Optional[Callable[[dict], Optional[str]]] = None,
    ens_name: str = ENS_NAME,
) -> CurrencyResult:
    """Pure-enough entry point for tests. Hooks default to the real operations.

    `build`, when supplied, is the site-tree CID builder (directory CID of
    the landing site at HEAD), not a file CID of this repo's index.html.
    A mocked CURRENT/STALE must feed that same artifact.
    """
    resolve = resolve or (lambda: resolve_ens_contenthash(ens_name))
    ipfs_present = ipfs_present or have_ipfs

    resolved, rerr = resolve()
    if resolved is None:
        reason = rerr or REASON_RESOLVER
        return CurrencyResult(verdict=UNDETERMINED, reason=reason)

    if not ipfs_present():
        return CurrencyResult(
            verdict=UNDETERMINED, reason=REASON_IPFS, resolved_cid=resolved,
            detail="no usable `ipfs` binary",
        )

    matched = pin_for_cid(resolved)
    pin_path, pin_rec = matched if matched else (None, None)
    if pin_rec is None:
        newest = newest_pin()
        params = cid_params_from(newest[1] if newest else None)
        # Currency without a matching pin still has to build *a* landing
        # site-tree. Use the newest record only for cid_params / repo hint;
        # the range is still landing-pinned→HEAD if that record names one.
        range_rec = newest[1] if newest else None
    else:
        params = cid_params_from(pin_rec)
        range_rec = pin_rec

    pin_bits = dict(
        pin_path=str(pin_path) if pin_path else None,
        pin_commit=(pin_rec or {}).get("commit") if pin_rec else None,
        pin_at=(pin_rec or {}).get("pinned_at") if pin_rec else None,
    )

    if build is not None:
        # Test / injected path. Do not invent a range from this repo.
        main_cid = build(params)
        rng = None
        detail = None
    else:
        site = build_site_tree(range_rec if pin_rec is None else pin_rec)
        main_cid = site.cid
        rng = site.range
        detail = site.error

    if main_cid is None:
        # ipfs was present but the CID still could not be computed (clone
        # failed, sync_console --check failed, site_cid.py returned cid=None).
        # PIN-RECORD names this bucket no_local_ipfs: we could not produce
        # the candidate CID, so we must not invent CURRENT/STALE.
        return CurrencyResult(
            verdict=UNDETERMINED, reason=REASON_IPFS, resolved_cid=resolved,
            detail=detail or "could not produce the site-tree CID",
            range=rng,
            **pin_bits,
        )

    if resolved == main_cid:
        return CurrencyResult(
            verdict=CURRENT,
            resolved_cid=resolved,
            main_cid=main_cid,
            range=rng,
            **pin_bits,
        )
    return CurrencyResult(
        verdict=STALE,
        resolved_cid=resolved,
        main_cid=main_cid,
        range=rng,
        **pin_bits,
    )


def _fmt_range(rng: Optional[dict]) -> str:
    if not rng:
        return "range not computed"
    if rng.get("basis") == RANGE_NOT_COMPUTED or rng.get("count") is None:
        fr = (rng.get("from") or "?")
        to = (rng.get("to") or "?")
        if isinstance(fr, str) and len(fr) > 12:
            fr = fr[:12]
        if isinstance(to, str) and len(to) > 12:
            to = to[:12]
        return f"range not computed ({fr}..{to} on landing)"
    n = rng.get("count")
    fr = (rng.get("from") or "?")
    to = (rng.get("to") or "HEAD")
    if isinstance(fr, str) and len(fr) > 12:
        fr = fr[:12]
    if isinstance(to, str) and len(to) > 12:
        to = to[:12]
    first = rng.get("first") or ""
    last = rng.get("last") or ""
    if first:
        first = first[:12]
    if last:
        last = last[:12]
    span = f"{first}..{last}" if first and last else "(empty)"
    where = "landing"
    return f"{n} commit(s) {fr}..{to} {span} on {where}"


def render(result: CurrencyResult) -> int:
    rep = verify_pin.Report()
    if result.verdict == UNDETERMINED:
        if result.reason == REASON_RESOLVER:
            rep.add(AMBER, f"UNDETERMINED reason={REASON_RESOLVER} — "
                           f"could not resolve {ENS_NAME} contenthash")
        elif result.reason == REASON_IPFS:
            extra = result.detail or "could not produce the site-tree CID"
            rep.add(AMBER, f"UNDETERMINED reason={REASON_IPFS} — {extra}")
        else:
            rep.add(AMBER, f"UNDETERMINED reason={result.reason}")
        print()
        print("UNDETERMINED — don't-act, never a silent not-current")
        return result.exit_code

    if result.pin_path:
        rep.add(GREEN, f"resolved contenthash matches pin record {pathlib.Path(result.pin_path).name}"
                       + (f" (commit {(result.pin_commit or '')[:12]}, {result.pin_at})"
                          if result.pin_commit or result.pin_at else ""))
    else:
        rep.add(AMBER, "no pin record in pins/ for the resolved CID")

    if result.verdict == CURRENT:
        rep.add(GREEN, f"contenthash CID equals the landing site-tree at HEAD: {result.resolved_cid}")
        print()
        print("CURRENT — contenthash is the deterministic site-tree of landing HEAD")
        return result.exit_code

    rep.add(RED, "contenthash CID is not the landing site-tree at HEAD")
    rep.add(RED, f"resolved: {result.resolved_cid}")
    rep.add(RED, f"landing:  {result.main_cid}")
    rep.add(RED, f"range:    {_fmt_range(result.range)}")
    print()
    print("STALE — determinate fail: both CIDs computed and they differ")
    return result.exit_code


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv in (["-h"], ["--help"]):
        print(__doc__)
        return 2
    print(f"\ncurrency of {ENS_NAME}\n")
    return render(evaluate())


if __name__ == "__main__":
    sys.exit(main())
