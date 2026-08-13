/* The state -> marker mapping, extracted so it can be asserted.
 *
 * WHY THIS IS ITS OWN FILE. Everything about the lineage state was already correct in
 * the data: linPairState/linClaimState model INDEPENDENT, DERIVED and
 * INDEPENDENCE_NOT_PROVEN as first-class values. Nothing tested what a human actually
 * sees, because the mapping from that state to the rendered marker lived inline in a
 * DOM branch with no way to call it. @boardyai's phrasing for the gap: {present:false}
 * survives serialization while a UI quietly drops "independence NOT PROVEN" — and the
 * boundary between testing observability and testing typography is whether you can feed
 * the mapping a state and assert on what comes back.
 *
 * The console imports this. A conformance gate imports the same file. The thing under
 * test is therefore the thing that ships, rather than a copy of it that can drift.
 *
 * THE BUG THIS FIXES. The previous inline version was guarded by `if (lin) { ... }`, and
 * linClaimState returns null whenever the lineage graph holds fewer than two nodes. So an
 * edge that held rendered as a plain green "edge holds — 2 GREEN Cells, byte-equal ..."
 * with no independence qualifier at all. Not "not proven" — nothing. Absence of a state
 * was rendered as absence of a caveat, which reads as the strongest claim on the page.
 * That is the collapsed value this console exists to refuse, and it was doing it.
 *
 * THE RULE HERE: there is no input for which this returns an unqualified green. Unknown,
 * absent and malformed all resolve to NOT PROVEN with a reason naming why. A marker can
 * only be omitted by a caller that never asks — never by this function answering.
 */

(function (root) {
  var INDEPENDENT = 'INDEPENDENT';
  var DERIVED = 'DERIVED';
  var UNPROVEN = 'INDEPENDENCE_NOT_PROVEN';

  var NOT_PROVEN_SUFFIX = '. Distinctness is necessary, not sufficient.';

  function unproven(why) {
    return {
      state: UNPROVEN,
      addClass: ['lin-unproven'],
      removeClass: [],
      tail: ' · independence NOT PROVEN — ' + why + NOT_PROVEN_SUFFIX,
      qualified: true
    };
  }

  /* lin: the [state, why] pair from linClaimState, or null/undefined when it could not
   * determine one. Returns what the caller must apply to the edge element and append to
   * its label. `qualified` is always true: it exists so a caller (or a test) can assert
   * that no branch ever produces a bare green. */
  function lineageMarker(lin) {
    // Absent. linClaimState returns null with fewer than two lanes in the graph, which is
    // "we cannot say", not "independent".
    if (lin === null || lin === undefined) {
      return unproven('lineage state unavailable — fewer than two lanes in the graph, so independence was never evaluated');
    }

    // Malformed. Anything that is not a well-formed [state, why] pair is a state we cannot
    // interpret, and an uninterpretable state is not evidence of independence.
    if (!Array.isArray(lin) || lin.length < 1 || typeof lin[0] !== 'string') {
      return unproven('lineage state malformed — expected a [state, reason] pair, cannot interpret it');
    }

    var state = lin[0];
    var why = (typeof lin[1] === 'string' && lin[1]) ? lin[1] : 'no reason recorded';

    if (state === INDEPENDENT) {
      return {
        state: INDEPENDENT,
        addClass: ['lin-independent'],
        removeClass: [],
        tail: ' · INDEPENDENT — ' + why,
        qualified: true
      };
    }

    if (state === DERIVED) {
      return {
        state: DERIVED,
        addClass: ['lin-derived'],
        removeClass: ['match'],
        tail: ' · DERIVED — ' + why + '. The claim_ids agree, but these lanes share lineage, so this edge is weaker than two independent recomputations.',
        qualified: true
      };
    }

    if (state === UNPROVEN) return unproven(why);

    // An unrecognised state string. Failing closed is the only safe direction: a future
    // state this build has never heard of must not inherit the strongest rendering.
    return unproven('unrecognised lineage state "' + state + '" — this build cannot interpret it' + (why !== 'no reason recorded' ? ' (' + why + ')' : ''));
  }

  lineageMarker.STATES = { INDEPENDENT: INDEPENDENT, DERIVED: DERIVED, UNPROVEN: UNPROVEN };

  root.lineageMarker = lineageMarker;
  if (typeof module !== 'undefined' && module.exports) module.exports = { lineageMarker: lineageMarker };
})(typeof globalThis !== 'undefined' ? globalThis : this);
