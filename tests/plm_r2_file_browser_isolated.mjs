// Offline-only real-Chromium file:// smoke. Uses only Node built-ins and dummy invalid data.
// No OAuth exchange, clipboard write, external HTTP, YouTube or Cloudflare APIs.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const htmlPath = resolve(process.env.PLM_TEST_HTML_PATH || 'readiness/oauth-handoff-local-r2.html');
const known = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const chrome = process.env.CHROME_PATH || known.find(existsSync) || ['google-chrome','chromium'].map(name=>spawnSync('which',[name],{encoding:'utf8'})).find(r=>r.status===0)?.stdout.trim();
if (!chrome || !existsSync(chrome)) throw Error('ISOLATED_CHROME_BINARY_MISSING');
const html = await readFile(htmlPath,'utf8');
assert.ok(html.includes('Content-Security-Policy') && html.includes('PLMHandoff'), 'SOURCE_HTML_NOT_EXPECTED');
const profile = await mkdtemp(join(tmpdir(), 'plm-file-chrome-'));
let child, socket;
let requestCount=0, commandId=0;
const pending = new Map();
function delay(ms){return new Promise(r=>setTimeout(r,ms));}
async function waitForPort(){
 for(let i=0;i<120;i++){
  if(child.exitCode!==null) throw Error('CHROME_EXITED_BEFORE_DEBUG_PORT');
  try {const v=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0].trim();
   if(/^\d+$/.test(v)) return Number(v); } catch{}
  await delay(100);
 }
 throw Error('CHROME_DEBUG_PORT_TIMEOUT');
}
async function command(method,params={}){
 const id=++commandId;
 const promise=new Promise((resolve,reject)=>pending.set(id,{resolve,reject}));
 socket.send(JSON.stringify({id,method,params}));
 return promise;
}
async function evaluate(expression){
 const packet=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(packet.exceptionDetails) throw Error('CHROME_JS_EXCEPTION: '+JSON.stringify(packet.exceptionDetails));
 return packet.result?.value;
}
async function poll(expression,predicate=(x)=>Boolean(x)){
 let last;
 for(let i=0;i<80;i++){
  const val=await evaluate(expression);last=val;
  if(predicate(val))return val;
  await delay(100);
 }
 throw Error('CHROME_PAGE_READY_TIMEOUT '+JSON.stringify(last));
}
async function loadFile(){
 const nav=await command('Page.navigate',{url:pathToFileURL(htmlPath).href});
 if (nav.errorText) throw Error('CHROME_FILE_NAVIGATION_BLOCKED: '+nav.errorText);
 return poll("({protocol:location.protocol,ready:document.readyState,date:document.getElementById('date')?.value||'',copyDisabled:document.getElementById('copy')?.disabled})",v=>v?.protocol==='file:' && /^\d{4}-\d{2}-\d{2}$/.test(v.date));
}
const results=[];
function check(name,callback){callback();results.push({name,status:'PASS'});console.log('PASS '+name);}
try {
 child=spawn(chrome,[
  '--headless=new','--no-sandbox','--disable-gpu','--disable-extensions',
  '--disable-background-networking','--disable-component-update','--disable-sync',
  '--no-first-run','--no-default-browser-check',
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
  '--remote-allow-origins=*','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost',
  `--user-data-dir=${profile}`,'about:blank'
 ],{stdio:['ignore','ignore','pipe']});
 let stderr='';child.stderr.on('data',d=>stderr=(stderr+String(d)).slice(-2400));
 const port=await waitForPort();
 const tabs=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 const tab=tabs.find(x=>x.type==='page');
 if(!tab?.webSocketDebuggerUrl)throw Error('CHROME_PAGE_SOCKET_NOT_FOUND '+stderr);
 socket=new WebSocket(tab.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
 socket.addEventListener('message',e=>{
  const m=JSON.parse(e.data);
  if(m.id && pending.has(m.id)){const h=pending.get(m.id);pending.delete(m.id);if(m.error)h.reject(Error(JSON.stringify(m.error)));else h.resolve(m.result);}
  if(m.method==='Network.requestWillBeSent' && /^https?:/i.test(m.params?.request?.url||''))requestCount++;
 });
 await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
 const first=await loadFile();
 check('actual file:// origin and JS initializer',()=>{assert.equal(first.protocol,'file:');assert.match(first.date,/^\d{4}-\d{2}-\d{2}$/);assert.equal(first.copyDisabled,false);});
 const unapproved=await evaluate(`(() => {const id=x=>document.getElementById(x);id('callback').value='DUMMY_INVALID_DATA';id('copy').click();return {status:id('status').textContent,cleared:id('callback').value==='',disabled:id('copy').disabled};})()`);
 check('unapproved dummy copy is stopped and erased',()=>{assert.match(unapproved.status,/承認が必要/);assert.equal(unapproved.cleared,true);assert.equal(unapproved.disabled,true);});
 await loadFile();
 const invalid=await evaluate(`(async () => {const id=x=>document.getElementById(x);id('approved').checked=true;id('callback').value='INVALID_DUMMY_CALLBACK_ONLY';id('date').value='2026-11-16';id('time').value='00:00';id('copy').click();await new Promise(r=>setTimeout(r,50));return {status:id('status').textContent,cleared:id('callback').value==='',disabled:id('copy').disabled};})()`);
 check('invalid dummy callback fails closed and clears local entry',()=>{assert.match(invalid.status,/停止/);assert.equal(invalid.cleared,true);assert.equal(invalid.disabled,true);});
 await loadFile();
 const cleared=await evaluate(`(() => {const id=x=>document.getElementById(x);id('callback').value='DUMMY';id('time').value='00:00';id('clear').click();return {status:id('status').textContent,cleared:id('callback').value==='',timeEmpty:id('time').value==='',disabled:id('copy').disabled};})()`);
 check('Clear terminates and erases fields',()=>{assert.match(cleared.status,/停止/);assert.equal(cleared.cleared,true);assert.equal(cleared.timeEmpty,true);assert.equal(cleared.disabled,true);});
 await delay(100);
 check('no external HTTP(S) requests by tested page',()=>assert.equal(requestCount,0));
 console.log('PLM_REAL_FILE_BROWSER_OFFLINE_PASS '+JSON.stringify({tests:results.length,passed:results.length,external_requests:requestCount,chrome,source:'file:// local HTML; dummy data only'}));
} finally {
 for(const p of pending.values()) p.reject(Error('CHROME_CLEANUP'));
 socket?.close();
 if(child?.exitCode===null)child.kill('SIGTERM');
 await rm(profile,{recursive:true,force:true,maxRetries:3,retryDelay:100});
}