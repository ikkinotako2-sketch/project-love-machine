'use strict';
// Pure browser-local formatter. It has no HTTP, storage, file or logging adapter.
(function (root) {
  const fail = reason => { throw new Error(reason); };
  function timestamp(date, time) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}(:\d{2})?$/.test(time)) fail('RECEIPT_TIME_REQUIRED');
    const full = time.length === 5 ? time + ':00' : time;
    const ms = Date.parse(date + 'T' + full + '+09:00');
    if (!Number.isFinite(ms) || new Date(ms + 32400000).toISOString().slice(0, 19) !== date + 'T' + full) fail('RECEIPT_TIME_INVALID');
    return ms / 1000;
  }
  function compose(config, callback, date, time, now) {
    if (!config || !/^\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(config.client_id) ||
        config.redirect_uri !== 'https://developers.google.com/oauthplayground' ||
        !/^[A-Za-z0-9_-]{43,128}$/.test(config.state)) fail('PUBLIC_PINS_INVALID');
    let url;
    try { url = new URL(callback); } catch { fail('CALLBACK_INVALID'); }
    // Google Playground canonically redirects its registered no-slash URI to a slash path.
    // Only these two exact HTTPS targets are accepted. The exchange redirect_uri stays pinned.
    if (url.origin !== 'https://developers.google.com' ||
        !['/oauthplayground', '/oauthplayground/'].includes(url.pathname) ||
        url.hash || url.username || url.password) fail('CALLBACK_TARGET_MISMATCH');
    const allowed = new Set(['code', 'state', 'scope', 'authuser', 'prompt']);
    for (const key of url.searchParams.keys()) {
      if (!allowed.has(key) || url.searchParams.getAll(key).length !== 1) fail('CALLBACK_FIELDS_INVALID');
    }
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    if (state !== config.state) fail('RETURNED_STATE_MISMATCH');
    if (!code || code.length > 16384 || !/^[!-~]+$/.test(code)) fail('CODE_INVALID');
    const issued = timestamp(date, time);
    if (!Number.isFinite(now) || now < issued || now >= issued + 300) fail('LOCAL_300_SECOND_STOP');
    return JSON.stringify({client_id: config.client_id, code, state, redirect_uri: config.redirect_uri, issued_at: issued});
  }
  function session(config, clock) {
    let used = false, expected = null;
    return Object.freeze({
      async copy(callback, date, time, write) {
        if (used) fail('LOCAL_HANDOFF_ALREADY_USED');
        const payload = compose(config, callback, date, time, clock());
        if (typeof write !== 'function') fail('CLIPBOARD_UNAVAILABLE_STOP');
        used = true;
        expected = payload;
        // Attempt once. Unknown clipboard result is terminal for this page.
        try { await write(payload); } catch { expected = null; fail('CLIPBOARD_UNKNOWN_NO_RETRY'); }
        return 'HANDOFF_COPIED_NOT_SAVED_NOT_EXCHANGED';
      },
      verifyPaste(raw) {
        if (!used || expected === null) fail('PASTEBACK_NOT_READY_STOP');
        if (raw !== expected) { expected = null; fail('PASTEBACK_MISMATCH_STOP'); }
        const parsed = JSON.parse(raw);
        if (typeof parsed.issued_at !== 'number' || !Number.isSafeInteger(parsed.issued_at)) fail('PASTEBACK_SHAPE_STOP');
        if (clock() < parsed.issued_at || clock() >= parsed.issued_at + 300) fail('LOCAL_300_SECOND_STOP');
        return 'PASTEBACK_EXACT_JSON_CONFIRMED';
      },
      clear() { expected = null; used = true; }
    });
  }
  const api = Object.freeze({timestamp, compose, session});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PLMHandoff = api;
})(typeof window === 'undefined' ? {} : window);
