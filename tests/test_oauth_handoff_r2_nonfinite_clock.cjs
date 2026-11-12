'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {session,timestamp}=require('../readiness/oauth-handoff-local-r2.cjs');
const config={client_id:'123-fixture.apps.googleusercontent.com',state:'D'.repeat(43),redirect_uri:'https://developers.google.com/oauthplayground'};
const callback='https://developers.google.com/oauthplayground/?code=DUMMY&state='+config.state;
const issued=timestamp('2026-10-24','21:00');
for(const invalid of [NaN,Infinity,-Infinity,'bad-clock',undefined]){
  test('non-finite pasteback clock stops and consumes local handoff '+String(invalid),async()=>{
    let now=issued+1,payload;
    const handoff=session(config,()=>now);
    await handoff.copy(callback,'2026-10-24','21:00',async p=>{payload=p});
    now=invalid;
    assert.throws(()=>handoff.verifyPaste(payload),/LOCAL_300_SECOND_STOP/);
    now=issued+2;
    assert.throws(()=>handoff.verifyPaste(payload),/PASTEBACK_NOT_READY_STOP/);
  });
}
test('pasteback uses one clock reading and accepts 299 seconds but not 300',async()=>{
  let now=issued+1,readings=0,payload;
  const handoff=session(config,()=>{readings++;return now});
  await handoff.copy(callback,'2026-10-24','21:00',async p=>{payload=p});
  now=issued+299;
  assert.equal(handoff.verifyPaste(payload),'PASTEBACK_EXACT_JSON_CONFIRMED');
  assert.equal(readings,2);
  const expired=session(config,()=>now);
  await expired.copy(callback,'2026-10-24','21:00',async()=>{});
  now=issued+300;
  assert.throws(()=>expired.verifyPaste(payload),/LOCAL_300_SECOND_STOP/);
});
