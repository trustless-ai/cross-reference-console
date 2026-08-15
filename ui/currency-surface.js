/* The currency surface — the DOM write, and deliberately nothing else.
 *
 * @boardyai's wiring constraint, ratified 15 August 2026: "Keep the page's initial state
 * NOT_RUN, transition to PENDING before the read, and pass the result unchanged through the
 * existing projection. The wiring should add no decision logic and no second mapping."
 *
 * That constraint is the whole design of this file, so it is worth saying what it rules out.
 * The tempting shape is a surface that looks at the state and picks a sentence — a switch on
 * CURRENT/STALE/COULD_NOT_CHECK right here, next to the DOM. It would work, and it would be a
 * SECOND mapping: two files deciding what a state means, one of them tested and one of them
 * shipped. They drift, and the drift always goes the flattering way, because nobody notices a
 * caveat that stopped being rendered.
 *
 * So this file contains no verdict and no reason vocabulary at all. The wording is
 * currency-marker.js's, transported. `NOT_RUN` is the single state name that appears, because
 * the initial state was specified rather than derived, and check_currency_surface.py asserts
 * that the others do NOT appear.
 *
 * THE ONE GUARD. A marker that is malformed — missing text, missing the `qualified` flag —
 * renders a loud defect sentence rather than nothing. Rendering nothing is how this whole
 * class of bug ships: absence of a caveat reads as the strongest claim on the page. The guard
 * is not a mapping; it never inspects state, verdict or reason, and it cannot produce a
 * currency answer.
 */

(function (root) {
  var dep = (typeof require !== 'undefined' && typeof module !== 'undefined')
    ? { m: require('./currency-marker.js'), r: require('./currency-read.js') }
    : { m: { currencyMarker: root.currencyMarker }, r: root.currencyRead };

  var currencyMarker = dep.m.currencyMarker;
  var readCurrency = dep.r.readCurrency;

  /* Not a state, not a verdict, not a reason: a statement that this build could not render
   * what it was handed. Amber because it is unresolved, and it says whose fault it is so a
   * reader does not read it as a finding about the publication. */
  var DEFECT_TEXT = 'could not render — this build was handed a marker it cannot interpret. '
    + 'That is a defect in this page, not a finding about what is published';

  function renderCurrency(marker, el) {
    var wellFormed = !!marker && typeof marker === 'object'
      && typeof marker.text === 'string' && marker.text !== ''
      && typeof marker.tone === 'string' && marker.tone !== ''
      && marker.qualified === true;

    /* Everything below is transport. No branch reads marker.state, marker.verdict or
     * marker.reason to decide anything — they are copied out for CSS and for a reader
     * inspecting the DOM, never consulted. */
    var text = wellFormed ? marker.text : DEFECT_TEXT;
    var tone = wellFormed ? marker.tone : 'amber';
    var state = wellFormed ? String(marker.state) : '';
    var reason = (wellFormed && marker.reason) ? String(marker.reason) : '';

    if (el) {
      el.textContent = text;
      el.setAttribute('data-tone', tone);
      el.setAttribute('data-state', state);
      el.setAttribute('data-reason', reason);
    }
    return { text: text, tone: tone, state: state, reason: reason, wellFormed: wellFormed };
  }

  /* THE WIRING, as a function, so it is drivable by a vector.
   *
   * Left inline in the page it would be five untestable lines, and five lines is exactly the
   * size at which "the initial state is NOT_RUN" and "PENDING is rendered before the wait"
   * become claims nobody checks. Here they are assertions.
   *
   *   element   the node to write into
   *   read      the transport for readCurrency ({resolveCid, fetchPinRecord, sourceCommit})
   */
  function mountCurrency(opts) {
    opts = opts || {};
    var el = opts.element;
    var read = opts.read || {};

    /* Specified, not derived: the page has not asked yet, and says so. */
    renderCurrency(currencyMarker('NOT_RUN'), el);

    return readCurrency({
      resolveCid: read.resolveCid,
      fetchPinRecord: read.fetchPinRecord,
      sourceCommit: read.sourceCommit,
      /* Every marker the read emits reaches the DOM unchanged — including PENDING, which the
       * read emits before it waits. Nothing here filters, delays or upgrades one. */
      onState: function (m) { renderCurrency(m, el); }
    });
  }

  var api = { renderCurrency: renderCurrency, mountCurrency: mountCurrency };
  root.currencySurface = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
