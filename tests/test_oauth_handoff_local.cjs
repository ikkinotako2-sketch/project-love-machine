'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const {timestamp, compose, session} = require('../readiness/oauth-handoff-local.cjs');
const config = {client_id:'123-fixture.apps.googleusercontent.com',state:'a'.repeat(43),redirect_uri:'https://developers.google.com/oauthplayground'};
const received = 1792676460;
const callback = (change={}) => {
  const u = new URL(config.redirect_uri);
  u.search = new URLSearchParams({code:'FIXTURE_CODE_NOT_A_CREDENTIAL',state:config.state,...change});
  return u.href;
};
const build = (url=callback(),now=received+1) => compose(config,url,'2026-10-22','22:41',now);
test('actual receipt minute is rounded down, never replaced by paste time',()=>{
  assert.equal(timestamp('2026-10-22','22:41'),received);
  assert.equal(timestamp('2026-10-22','22:41:15'),received+15);
  assert.equal(JSON.parse(build()).issued_at,received);
});
test('formatter matches existing executor exact handoff contract',()=>{
  const p=JSON.parse(build());
  assert.deepEqual(Object.keys(p).sort(),['client_id','code','issued_at','redirect_uri','state']);
  assert.equal(p.client_id,config.client_id);assert.equal(p.state,config.state);
});
test('300 second boundary rejects before any clipboard attempt',async()=>{
  let writes=0;const s=session(config,()=>received+300);
  await assert.rejects(s.copy(callback(),'2026-10-22','22:41',()=>writes++),/LOCAL_300_SECOND_STOP/);
  assert.equal(writes,0);
});
test('future receipt is rejected',()=>assert.throws(()=>build(callback(),received-1),/LOCAL_300_SECOND_STOP/));
test('wrong returned state is rejected without exposing it',()=>assert.throws(()=>build(callback({state:'PRIVATE_FIXTURE'})),e=>e.message==='RETURNED_STATE_MISMATCH'));
test('wrong redirect is rejected',()=>assert.throws(()=>build(callback().replace('developers.google.com','example.invalid')),/CALLBACK_TARGET_MISMATCH/));
test('duplicate fields are rejected',()=>assert.throws(()=>build(callback()+'&code=SECOND_FIXTURE'),/CALLBACK_FIELDS_INVALID/));
test('token response or provider error URL is rejected',()=>{
  for(const field of ['access_token','refresh_token','error']) assert.throws(()=>build(callback({[field]:'PRIVATE_FIXTURE'})),/CALLBACK_FIELDS_INVALID/);
});
test('invalid date and empty actual receipt time are rejected',()=>{
  for(const [d,t] of [['2026-02-30','12:00'],['2026-10-22',''],['2026-10-22','25:00']]) assert.throws(()=>timestamp(d,t));
});
test('copy executes once and preserves fixed source identity',async()=>{
  let count=0;const s=session(config,()=>received+10);
  assert.equal(await s.copy(callback(),'2026-10-22','22:41',async p=>{count++;assert.equal(JSON.parse(p).state,config.state);}), 'HANDOFF_COPIED_NOT_SAVED_NOT_EXCHANGED');
  await assert.rejects(s.copy(callback(),'2026-10-22','22:41',()=>count++),/LOCAL_HANDOFF_ALREADY_USED/);assert.equal(count,1);
});
test('clipboard unknown is not retried',async()=>{
  let count=0;const s=session(config,()=>received+10);
  await assert.rejects(s.copy(callback(),'2026-10-22','22:41',()=>{count++;throw Error('PRIVATE_FIXTURE');}),e=>e.message==='CLIPBOARD_UNKNOWN_NO_RETRY');
  await assert.rejects(s.copy(callback(),'2026-10-22','22:41',()=>count++),/LOCAL_HANDOFF_ALREADY_USED/);assert.equal(count,1);
});
test('HTML contains tested core and exact source CSP; no remote or retention adapters',()=>{
  const html=fs.readFileSync('readiness/oauth-handoff-local.html','utf8');
  const core=fs.readFileSync('readiness/oauth-handoff-local.cjs','utf8');
  assert.ok(html.includes(core));
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const hash=crypto.createHash('sha256').update(script).digest('base64');
  const csp=html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1].replaceAll('&#x27;',"'");
  assert.ok(csp.includes("script-src 'sha256-"+hash+"'"));
  assert.ok(csp.includes("connect-src 'none'"));assert.ok(csp.includes("form-action 'none'"));
  assert.doesNotMatch(script,/\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage|indexedDB|console)\b/);
  assert.doesNotMatch(html,/<(?:form|iframe|img)\b|<script[^>]+src=/i);
  assert.ok(html.includes('type="password"'));assert.ok(html.includes('autocomplete="off"'));
});
