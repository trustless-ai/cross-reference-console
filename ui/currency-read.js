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
 * 3. THE READ IS DATED. babyblueviper1, 15 August 2026: "a read agreeing with itself across
 *    multiple sources is not the same claim as a read agreeing with ground truth ... the fix
 *    has to be a freshness bound on the read itself, not more redundant reads of it." Moving
 *    from an ENS API to the contract removed one shared cache, not the class — an RPC node
 *    serves its own `latest`, and a lagging node answers confidently from a stale block. So
 *    resolveCid returns the block it read AT, the call is pinned to that block rather than to
 *    the moving tag `latest`, and the block's age is bounded against the local clock. The
 *    clock is the point: another RPC would be a second read on the same possibly-lagging path,
 *    which is precisely what does not help.
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
      .then(function (answer) {
        /* resolveCid may return a bare CID (legacy) or {cid, block, head_age_seconds}. */
        var cid = (answer && typeof answer === 'object') ? answer.cid : answer;
        var observed = (answer && typeof answer === 'object' && typeof answer.block === 'number')
          ? { block: answer.block, head_age_seconds: answer.head_age_seconds } : null;

        /* A resolver that answers with nothing is not a resolver that answered. */
        if (!cid || typeof cid !== 'string') {
          return emit(currencyMarker('COULD_NOT_CHECK', 'resolver_unreachable', observed));
        }
        /* A node whose head is hours old will answer every question confidently and be
         * behind on all of them. Bounded against the LOCAL CLOCK, deliberately: asking a
         * second node would be another read on the same possibly-lagging path. */
        var maxAge = typeof opts.maxHeadAgeSeconds === 'number' ? opts.maxHeadAgeSeconds : 900;
        if (observed && typeof observed.head_age_seconds === 'number'
            && observed.head_age_seconds > maxAge) {
          return emit(currencyMarker('COULD_NOT_CHECK', 'stale_head', observed));
        }
        return Promise.resolve()
          .then(function () { return opts.fetchPinRecord(cid); })
          .then(function (record) {
            /* No record for a CID that resolved: we can see what is published and cannot tell
             * which commit it selects. That is lock_unreadable, and it is NOT stale. */
            if (!record || typeof record !== 'object') {
              return emit(currencyMarker('COULD_NOT_CHECK', 'lock_unreadable', observed));
            }
            return emit(fromPinRecord(record, opts.sourceCommit, observed));
          })
          .catch(function () {
            return emit(currencyMarker('COULD_NOT_CHECK', 'lock_unreadable', observed));
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

    var rpc = function (method, params) {
      return f(cfg.rpcUrl, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: method, params: params })
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { return j && j.result !== undefined ? j.result : null; });
    };

    /* Name the block, then read AT it. Reading at the moving tag `latest` yields an answer
     * that cannot be dated afterwards — the head may have moved, and there is nothing in
     * the response to say which block it came from. */
    return rpc('eth_blockNumber', [])
      .then(function (hex) {
        if (!hex) return null;
        var block = parseInt(hex, 16);
        return rpc('eth_getBlockByNumber', [hex, false]).then(function (blk) {
          var age = (blk && blk.timestamp)
            ? Math.max(0, Math.round(Date.now() / 1000) - parseInt(blk.timestamp, 16)) : null;
          return rpc('eth_call', [
            { to: cfg.resolver, data: '0xbc1c58d1' + cfg.node.replace(/^0x/, '') }, hex
          ]).then(function (res) {
            var cid = res ? decodeContenthash(res) : null;
            return cid ? { cid: cid, block: block, head_age_seconds: age } : null;
          });
        });
      })
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
