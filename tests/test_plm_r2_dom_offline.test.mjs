// Offline-only DOM event harness. No credentials, clipboard writes, network, OAuth.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const html=readFileSync(new URL('../readiness/oauth-handoff-local-r2.html',import.meta.url),'utf8');
const matches=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(matches.length,1,'exactly one embedded script');
function scenario(protocol,approved=false){
  const elems=new Map(), listeners=new Map(), windowHandlers=new Map();
  const ids=['callback','date','time','approved','copy','pasteback','verify','clear','status'];
  for(const id of ids)elems.set(id,{
    value:'',checked:id==='approved'&&approved,disabled:false,textContent:'',
    addEventListener(type,fn){listeners.set(id+':'+type,fn);}
  });
  let attemptedClipboardWrites=0;
  const context={
    window:{addEventListener(type,fn){windowHandlers.set(type,fn);}},
    document:{getElementById(id){if(!elems.has(id))throw Error('MISSING_DOM_ID '+id);return elems.get(id);}},
    location:{protocol},
    navigator:{clipboard:{async writeText(){attemptedClipboardWrites++;throw Error('CLIPBOARD_MUST_NOT_BE_USED');}}},
    URL,Date,Intl,Set,JSON,Number,Object,Error,console
  };
  // Browser window === global object. Reflect that identity in the VM harness.
  context.window=context;
  context.addEventListener=(type,fn)=>windowHandlers.set(type,fn);
  runInNewContext(matches[0][1],context,{timeout:1500,filename:'oauth-handoff-local-r2.html'});
  return {elem:id=>elems.get(id),click:async id=>{const fn=listeners.get(id+':click');assert.ok(fn,'listener '+id);return fn();},pagehide:()=>windowHandlers.get('pagehide')?.(),clipboardWrites:()=>attemptedClipboardWrites};
}
test('preview mode blocks copy before any sensitive input',async()=>{
  const s=scenario('https:');
  assert.equal(s.elem('copy').disabled,true);
  await s.click('copy');
  assert.match(s.elem('status').textContent,/停止/);
  assert.equal(s.clipboardWrites(),0);
});
test('file mode still needs separate owner approval',async()=>{
  const s=scenario('file:');
  assert.equal(s.elem('copy').disabled,false);
  await s.click('copy');
  assert.match(s.elem('status').textContent,/承認が必要/);
  assert.equal(s.clipboardWrites(),0);
});
test('file mode rejects invalid callback without clipboard access',async()=>{
  const s=scenario('file:',true);
  s.elem('callback').value='INVALID_OFFLINE_FIXTURE';
  s.elem('date').value='2026-11-11';
  s.elem('time').value='00:00';
  await s.click('copy');
  assert.match(s.elem('status').textContent,/停止/);
  assert.equal(s.clipboardWrites(),0);
});
test('Clear and pagehide terminally disable the local handoff',async()=>{
  const s=scenario('file:');
  await s.click('clear');
  assert.equal(s.elem('copy').disabled,true);
  assert.equal(s.elem('time').value,'');
  assert.match(s.elem('status').textContent,/停止/);
  s.pagehide();
  assert.equal(s.clipboardWrites(),0);
});

test('unapproved local attempt erases callback and disables copy',async()=>{
  const s=scenario('file:');
  s.elem('callback').value='DUMMY_CALLBACK_NOT_A_REAL_CODE';
  await s.click('copy');
  assert.equal(s.elem('callback').value,'');
  assert.equal(s.elem('copy').disabled,true);
  assert.equal(s.clipboardWrites(),0);
});
test('invalid callback failure erases callback and disables copy',async()=>{
  const s=scenario('file:',true);
  s.elem('callback').value='INVALID_DUMMY_CALLBACK';
  s.elem('date').value='2026-11-11';
  s.elem('time').value='00:00';
  await s.click('copy');
  assert.equal(s.elem('callback').value,'');
  assert.equal(s.elem('copy').disabled,true);
  assert.equal(s.clipboardWrites(),0);
});
