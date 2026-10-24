'use strict';
// The actual standalone HTML handler, with dummy public pins and a mock clipboard.
const fs = require('node:fs');
const vm = require('node:vm');
module.exports = function fixture(code='FIXTURE_CODE_NOT_VALID', clipboardError=false) {
  const config={client_id:'123-fixture.apps.googleusercontent.com',state:'D'.repeat(43),redirect_uri:'https://developers.google.com/oauthplayground'};
  const issued=1792843200; // 2026-10-24 21:00 JST; virtual time only
  const elements={};
  for(const id of ['callback','date','time','approved','copy','clear','status','pasteback','verify'])
    elements[id]={value:'',checked:false,disabled:false,textContent:'',handlers:{},addEventListener(event,handler){this.handlers[event]=handler;}};
  let copies=0, payload=null;
  const html=fs.readFileSync('readiness/oauth-handoff-local-r2.html','utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/const CONFIG=.*?;/,'const CONFIG='+JSON.stringify(config)+';');
  class Clock extends Date { static now(){return (issued+10)*1000;} }
  const context={URL,URLSearchParams,Date:Clock,Intl,location:{protocol:'file:'},document:{getElementById:id=>elements[id]},navigator:{clipboard:{writeText:async raw=>{copies++;if(clipboardError)throw Error('PRIVATE_FIXTURE');payload=raw;}}},addEventListener(){}};
  context.window=context;
  vm.runInNewContext(script,context,{timeout:1000});
  elements.date.value='2026-10-24';elements.time.value='21:00:00';elements.approved.checked=true;
  const url=new URL(config.redirect_uri);url.search=new URLSearchParams({code,state:config.state});elements.callback.value=url.href;
  return {config,issued,elements,copy:()=>elements.copy.handlers.click(),paste:raw=>{elements.pasteback.value=raw;elements.verify.handlers.click();},payload:()=>payload,copies:()=>copies};
};
if(require.main===module)(async()=>{const f=module.exports(process.argv[2]||'FIXTURE_CODE_NOT_VALID');await f.copy();f.paste(f.payload());if(!f.elements.status.textContent.startsWith('貼り戻しJSON完全一致'))throw Error('FIXTURE_ROUNDTRIP_FAILED');process.stdout.write(f.payload());})();
