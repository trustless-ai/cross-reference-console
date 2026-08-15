/* The live currency read — the last piece, and deliberately the smallest.
 *
 * @boardyai's shape, ratified 15 August 2026: "resolve CID, read its pin record, compare
 * selects.commit with CONSOLE_SOURCE_COMMIT, and project through the vectors." Everything it
 * needs already exists: currencyMarker is the projection, fromPinRecord is the adapter, and the
 * reason taxonomy is closed. This file adds transport and nothing else — it invents no state,
 * no verdict and no vocabulary.
 *
 * TWO DESIGN DECISIONS WORTH THE COMMENT.
 *
 * 1. THE RESOLVER IS READ FROM THE CONTRACT, NOT FROM AN ENS API. On 15 August two independent
 *    ENS APIs served a superseded contenthash for minutes after the transaction confirmed, and
 *    a currency check reading one of them reported STALE against a record that was correct. A
 *    cached API answer is not an independent confirmation. So the default transport is an
 *    eth_call against the resolver and a decode of the raw e30101701220 bytes.
 *
 * 2. TRANSPORT IS INJECTED. A network read whose failure modes can only be exercised by
 *    unplugging a cable is a network read nobody tests. `resolveCid` and `fetchPinRecord` are
 *    parameters, so every path — silent resolver, missing record, malformed record, unstamped
 *    build — is drivable offline and pinned by a vector.
 *
 * NO FALLBACK. Every path that is not an established comparison returns COULD_NOT_CHECK with a
 * reason. There is no default, no last-known-good, and no assumption of currency when the
 * network disappears. The page would rather say it cannot see than guess.
 */

(function (root) {
  var marker = (typeof require !== 'undefined' && typeof module !== 'undefined')
    ? require('./currency-marker.js')
    : { currencyMarker: root.currencyMarker, fromPinRecord: root.currencyMarker.fromPinRecord };

  var currencyMarker = marker.currencyMarker;
  var fromPinRecord = marker.fromPinRecord || currencyMarker.fromPinRecord;

  /* Decode an ENS contenthash to a CIDv1 base32 string. Returns null on anything it does not
   * recognise — the caller turns that into resolver_unreachable rather than guessing. */
  function decodeContenthash(hex) {
    if (typeof hex !== 'string') return null;
    var h = hex.replace(/^0x/, '').toLowerCase();
    var i = h.indexOf('e30101701220');           /* ipfs / cidv1 / dag-pb / sha2-256 */
    if (i < 0) return null;
    var digest = h.slice(i + 12, i + 12 + 64);
    if (digest.length !== 64) return null;
    var bytes = [];
    var raw = '01701220' + digest;
    for (var b = 0; b < raw.length; b += 2) bytes.push(parseInt(raw.substr(b, 2), 16));
    var A = 'abcdefghijklmnopqrstuvwxyz234567', bits = '', out = 'b';
    for (var k = 0; k < bytes.length; k++) bits += ('00000000' + bytes[k].toString(2)).slice(-8);
    while (bits.length % 5) bits += '0';
    for (var j = 0; j < bits.length; j += 5) out += A[parseInt(bits.substr(j, 5), 2)];
    return out;
  }

  /* The read. Reports PENDING through onState before it waits, so the surface never sits on
   * NOT_RUN while a request is in flight — "not asked" and "asked, waiting" are different
   * facts and the page should not conflate them.
   *
   *   resolveCid       () => Promise<string|null>   the published CID, or null/throw
   *   fetchPinRecord   (cid) => Promise<object|null> that CID's pin record, or null/throw
   *   sourceCommit     the artifact's own CONSOLE_SOURCE_COMMIT
   *   onState          optional, called with each marker as the read progresses
   */
  function readCurrency(opts) {
    opts = opts || {};
    var onState = typeof opts.onState === 'function' ? opts.onState : function () {};
    var emit = function (m) { onState(m); return m; };

    emit(currencyMarker('PENDING'));

    return Promise.resolve()
      .then(function () { return opts.resolveCid(); })
      .then(function (cid) {
        /* A resolver that answers with nothing is not a resolver that answered. */
        if (!cid || typeof cid !== 'string') {
          return emit(currencyMarker('COULD_NOT_CHECK', 'resolver_unreachable'));
        }
        return Promise.resolve()
          .then(function () { return opts.fetchPinRecord(cid); })
          .then(function (record) {
            /* No record for a CID that resolved: we can see what is published and cannot tell
             * which commit it selects. That is lock_unreadable, and it is NOT stale. */
            if (!record || typeof record !== 'object') {
              return emit(currencyMarker('COULD_NOT_CHECK', 'lock_unreadable'));
            }
            return emit(fromPinRecord(record, opts.sourceCommit));
          })
          .catch(function () {
            return emit(currencyMarker('COULD_NOT_CHECK', 'lock_unreadable'));
          });
      })
      .catch(function () {
        return emit(currencyMarker('COULD_NOT_CHECK', 'resolver_unreachable'));
      });
  }

  /* ── Default transport ──────────────────────────────────────────────────────────────────
   * Separated so the logic above is testable without it, and so a self-hoster can point this
   * at their own RPC and pin mirror without touching the state machine. */

  function defaultResolveCid(cfg, fetchImpl) {
    var f = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!f) return Promise.resolve(null);
    var body = {
      jsonrpc: '2.0', id: 1, method: 'eth_call',
      params: [{ to: cfg.resolver, data: '0xbc1c58d1' + cfg.node.replace(/^0x/, '') }, 'latest']
    };
    return f(cfg.rpcUrl, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && j.result ? decodeContenthash(j.result) : null; })
      .catch(function () { return null; });
  }

  function defaultFetchPinRecord(cfg, cid, fetchImpl) {
    var f = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!f) return Promise.resolve(null);
    return f(cfg.pinBase.replace(/\/$/, '') + '/' + cid + '.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  var api = {
    readCurrency: readCurrency,
    decodeContenthash: decodeContenthash,
    defaultResolveCid: defaultResolveCid,
    defaultFetchPinRecord: defaultFetchPinRecord
  };

  root.currencyRead = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
