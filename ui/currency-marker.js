/* The currency state -> marker mapping, extracted so it can be asserted before it ships.
 *
 * WHY THIS EXISTS BEFORE THE FEATURE. The console does not yet read the resolver, and it must
 * not start until this mapping and its vectors exist. @boardyai, 15 August 2026: "a verification
 * page should earn the right to make a new claim before it gets another source of uncertainty."
 *
 * THE CONTRACT is his two-layer one, unchanged — no new states were invented for this surface:
 *
 *   NOT_RUN          the page has loaded and has not asked yet
 *   PENDING          the resolver read is in flight
 *   COULD_NOT_CHECK  a check was attempted and no result could be established.
 *                    REQUIRED reason: resolver_unreachable | no_local_ipfs | lock_unreadable
 *   CHECKED          + domain verdict CURRENT | STALE
 *
 * Network-unreachable is a REASON, not a state. Naming it would have been the move that earns a
 * fifth entry next month. And UNDETERMINED does not appear here at all: it was UNVERIFIABLE
 * wearing a third name, and it maps at the boundary (fromLegacy) rather than surviving as a
 * second canonical state.
 *
 * WHAT THE CONSOLE MUST NEVER DO. This mapping renders currency for a value the page is TOLD at
 * read time. It must never be given a baked answer: a frozen artifact asserting its own currency
 * is a claim that was true when written and is read as true now, which is the collapse this
 * whole console exists to refuse — self-inflicted, and unfalsifiable from inside the page. The
 * artifact states what it IS (CONSOLE_SOURCE_COMMIT). The verdict is derived by whoever asks.
 *
 * THE TWO ASSERTIONS THAT MATTER, both his:
 *   1. No reason can manufacture a verdict. A reason accompanies a failure to establish one; it
 *      never becomes one.
 *   2. No failure disappears into a generic green or amber. The three reasons are three
 *      different next actions, so they must not render as one indistinguishable amber — that
 *      would keep the reason in the data and collapse it on the surface, which is the same
 *      defect one layer out.
 */

(function (root) {
  var NOT_RUN = 'NOT_RUN';
  var PENDING = 'PENDING';
  var COULD_NOT_CHECK = 'COULD_NOT_CHECK';
  var CHECKED = 'CHECKED';

  var CURRENT = 'CURRENT';
  var STALE = 'STALE';

  var EXECUTION_STATES = [NOT_RUN, PENDING, COULD_NOT_CHECK, CHECKED];
  var VERDICTS = [CURRENT, STALE];
  var REASONS = ['resolver_unreachable', 'no_local_ipfs', 'lock_unreadable'];

  /* Each reason says which side of the comparison went dark, and they are not
   * interchangeable: one means the candidate could not be computed, another that the
   * published side could not be read, the third that we cannot even tell which commit is
   * selected. Different next actions, therefore different text. */
  var REASON_TEXT = {
    resolver_unreachable:
      'could not read what is published — the resolver did not answer, so the live contenthash is unknown',
    no_local_ipfs:
      'could not compute the candidate — no local ipfs to derive the CID from, so there is nothing to compare against',
    lock_unreadable:
      'could not tell which commit is selected — the pin record or lock could not be read'
  };

  function unqualifiedGuard(o) {
    /* `qualified` is true on every branch and exists so a gate can assert that no path
     * produces a bare claim. A green with it absent would be a bug in this file. */
    o.qualified = true;
    return o;
  }

  /* The ONLY input is the pair. A caller that wants to decide something else has to reach
   * outside this function, which CI can see. */
  function currencyMarker(execution, detail) {
    if (execution === CHECKED) {
      var verdict = detail;
      if (verdict === CURRENT) {
        return unqualifiedGuard({
          state: CHECKED, verdict: CURRENT, reason: null, tone: 'green',
          text: 'CURRENT — the published contenthash is the build of this commit'
        });
      }
      if (verdict === STALE) {
        return unqualifiedGuard({
          state: CHECKED, verdict: STALE, reason: null, tone: 'red',
          text: 'STALE — the published contenthash is not the build of this commit'
        });
      }
      /* A verdict this build has never heard of. Failing closed is the only safe direction:
       * an unrecognised verdict must not inherit the strongest rendering, and it must not be
       * rendered as a determinate STALE either — we did not establish that. */
      return unqualifiedGuard({
        state: COULD_NOT_CHECK, verdict: null, reason: 'unrecognised_verdict', tone: 'amber',
        text: 'could not check — unrecognised currency verdict "' + String(verdict) + '", this build cannot interpret it'
      });
    }

    if (execution === COULD_NOT_CHECK) {
      var reason = detail;
      var known = Object.prototype.hasOwnProperty.call(REASON_TEXT, reason);
      return unqualifiedGuard({
        state: COULD_NOT_CHECK,
        verdict: null,                     /* rule 1: a reason never becomes a verdict */
        reason: known ? reason : 'unspecified',
        tone: 'amber',
        text: 'could not check — ' + (known
          ? REASON_TEXT[reason]
          : 'no reason was recorded, which is itself a defect in the caller')
      });
    }

    if (execution === PENDING) {
      return unqualifiedGuard({
        state: PENDING, verdict: null, reason: null, tone: 'amber',
        text: 'checking — the resolver read is in flight. This is not a pass'
      });
    }

    if (execution === NOT_RUN) {
      return unqualifiedGuard({
        state: NOT_RUN, verdict: null, reason: null, tone: 'neutral',
        text: 'not checked — currency has not been established, which is not the same as being current'
      });
    }

    /* An execution state this build has never heard of — same fail-closed direction. */
    return unqualifiedGuard({
      state: COULD_NOT_CHECK, verdict: null, reason: 'unrecognised_state', tone: 'amber',
      text: 'could not check — unrecognised execution state "' + String(execution) + '", this build cannot interpret it'
    });
  }

  /* THE BOUNDARY. Rule 3: legacy UNVERIFIABLE / UNDETERMINED map here and must not survive as
   * second canonical states. The reasons the existing checks already emit are carried through
   * unchanged — reference/check_console_currency.py emits resolver_unreachable and
   * no_local_ipfs; the landing repo's build/check_console_currency.py emits
   * upstream_unreachable and lock_unreadable. No information is lost; one fewer state exists. */
  var LEGACY_REASON = {
    resolver_unreachable: 'resolver_unreachable',
    upstream_unreachable: 'resolver_unreachable',
    no_local_ipfs: 'no_local_ipfs',
    lock_unreadable: 'lock_unreadable'
  };

  function fromLegacy(verdict, reason) {
    var v = String(verdict || '').toUpperCase();
    if (v === 'CURRENT') return currencyMarker(CHECKED, CURRENT);
    if (v === 'STALE') return currencyMarker(CHECKED, STALE);
    if (v === 'UNDETERMINED' || v === 'UNVERIFIABLE') {
      return currencyMarker(COULD_NOT_CHECK, LEGACY_REASON[reason] || 'unspecified');
    }
    return currencyMarker('__unrecognised__', verdict);
  }

  currencyMarker.EXECUTION_STATES = EXECUTION_STATES;
  currencyMarker.VERDICTS = VERDICTS;
  currencyMarker.REASONS = REASONS;
  currencyMarker.fromLegacy = fromLegacy;

  root.currencyMarker = currencyMarker;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { currencyMarker: currencyMarker, fromLegacy: fromLegacy };
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
