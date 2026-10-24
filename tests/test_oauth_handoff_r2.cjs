'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const fixture=require('./oauth_handoff_r2_dom.cjs');
test('actual HTML click handler copies exact complete JSON and validates owner pasteback',async()=>{
 const f=fixture();await f.copy();const raw=f.payload();f.paste(raw);
 assert.equal(f.copies(),1);assert.equal(JSON.parse(raw).issued_at,f.issued);
 assert.match(f.elements.status.textContent,/貼り戻しJSON完全一致/);assert.equal(f.elements.pasteback.value,'');
});
test('quotes, backslashes, slash, plus, percent and ampersand survive actual handler',async()=>{
 const code='FIXTURE_"\\/+=%&';const f=fixture(code);await f.copy();assert.equal(JSON.parse(f.payload()).code,code);f.paste(f.payload());assert.match(f.elements.status.textContent,/完全一致/);
});
test('truncation, extra quotes, callback URL, other clipboard contents fail pasteback',async()=>{
 for(const change of [s=>s.slice(1),s=>JSON.stringify(s),()=> 'https://example.invalid/?code=FIXTURE',()=> 'FIXTURE_WRITER_NOT_A_SECRET']){
  const f=fixture();await f.copy();f.paste(change(f.payload()));assert.match(f.elements.status.textContent,/停止/);assert.equal(f.copies(),1);
 }
});
test('no execution approval means zero copies',async()=>{const f=fixture();f.elements.approved.checked=false;await f.copy();assert.equal(f.copies(),0);assert.equal(f.payload(),null);});
test('unknown clipboard write is terminal and does not leak underlying error',async()=>{const f=fixture('FIXTURE',true);await f.copy();await f.copy();assert.equal(f.copies(),1);assert.doesNotMatch(f.elements.status.textContent,/PRIVATE_FIXTURE/);});
test('double click is refused',async()=>{const f=fixture();await f.copy();await f.copy();assert.equal(f.copies(),1);});
test('page clear destroys pasteback comparison context',async()=>{const f=fixture();await f.copy();const p=f.payload();f.elements.clear.handlers.click();f.paste(p);assert.match(f.elements.status.textContent,/停止/);});
test('current HTML embeds tested core and correct CSP, no network/storage/logging',()=>{
 const html=fs.readFileSync('readiness/oauth-handoff-local-r2.html','utf8');const core=fs.readFileSync('readiness/oauth-handoff-local-r2.cjs','utf8');assert.ok(html.includes(core));
 const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];const h=crypto.createHash('sha256').update(script).digest('base64');assert.ok(html.includes('script-src &#x27;sha256-'+h+'&#x27;'));
 assert.ok(html.includes("connect-src &#x27;none&#x27;"));assert.doesNotMatch(script,/\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage|indexedDB|console)\b/);
 assert.doesNotMatch(html,/<(?:form|iframe|img)\b|<script[^>]+src=/i);
});
