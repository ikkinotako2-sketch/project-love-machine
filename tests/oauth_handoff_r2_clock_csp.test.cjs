'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const crypto=require('node:crypto');
const path=require('node:path');
const core=require('../readiness/oauth-handoff-local-r2.cjs');
const coreText=fs.readFileSync(path.join(__dirname,'../readiness/oauth-handoff-local-r2.cjs'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../readiness/oauth-handoff-local-r2.html'),'utf8');
const config={client_id:'123-fixture.apps.googleusercontent.com',redirect_uri:'https://developers.google.com/oauthplayground',state:'D'.repeat(43)};
const callback='https://developers.google.com/oauthplayground/?code=OFFLINE_FIXTURE&state='+config.state;
const issued=core.timestamp('2026-10-24','21:00:00');
test('inline handoff matches standalone source and declared CSP hash',()=>{
 const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
 assert.ok(script,'inline script must exist');
 assert.ok(script.includes(coreText.trimEnd()),'core source must match inline module');
 const digest=crypto.createHash('sha256').update(script,'utf8').digest('base64');
 assert.ok(html.includes('script-src &#x27;sha256-'+digest+'&#x27;'));
 assert.ok(html.includes('connect-src &#x27;none&#x27;'));
 assert.ok(html.includes('form-action &#x27;none&#x27;'));
});
test('nonfinite clock stops and consumes local pasteback once',async()=>{
 let now=issued+1,raw;
 const s=core.session(config,()=>now);
 await s.copy(callback,'2026-10-24','21:00:00',async payload=>{raw=payload});
 now=Infinity;
 assert.throws(()=>s.verifyPaste(raw),/LOCAL_300_SECOND_STOP/);
 now=issued+2;
 assert.throws(()=>s.verifyPaste(raw),/PASTEBACK_NOT_READY_STOP/);
});
test('pasteback clock called once, not twice',async()=>{
 let calls=0,raw;
 const s=core.session(config,()=>{calls++;return issued+1});
 await s.copy(callback,'2026-10-24','21:00:00',async p=>{raw=p});
 assert.equal(s.verifyPaste(raw),'PASTEBACK_EXACT_JSON_CONFIRMED');
 assert.equal(calls,2);
});
test('300-second boundary fails closed',async()=>{
 let now=issued+299,raw;
 const s=core.session(config,()=>now);
 await s.copy(callback,'2026-10-24','21:00:00',async p=>{raw=p});
 assert.equal(s.verifyPaste(raw),'PASTEBACK_EXACT_JSON_CONFIRMED');
 now=issued+300;
 assert.throws(()=>s.verifyPaste(raw),/LOCAL_300_SECOND_STOP/);
});
