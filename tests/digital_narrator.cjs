const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync('src/digitalNarrator.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 const pending=[],events=[],errors=[],plays=[],revoked=[];let objectId=0;
 class Audio{constructor(){this.paused=true;this.src='';Audio.instance=this;}play(){this.paused=false;plays.push(this.src);return Promise.resolve();}pause(){this.paused=true;}load(){}removeAttribute(){this.src='';}}
 const context={exports:{},Audio,fetch:(url,options)=>new Promise(resolve=>pending.push({url,body:JSON.parse(options.body),resolve,signal:options.signal})),URL:{createObjectURL:()=>`blob:${++objectId}`,revokeObjectURL:url=>revoked.push(url)},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},AbortController,Uint8Array,Math};
 vm.runInNewContext(code,context);
 const mouth={current:0};const narrator=new context.exports.DigitalNarrator(mouth,(status,message)=>events.push({status,id:message?.id}),e=>errors.push(e));
 function finishFetch(index,chunks=1,ok=true){pending[index].resolve({ok,headers:{get:()=>String(chunks)},blob:async()=>({}),json:async()=>({detail:'voice failed'})});}
 return {narrator,pending,events,errors,plays,revoked,mouth,finishFetch,audio:()=>Audio.instance};
}
const cred={session_id:'session-a',token:'secret'},message=id=>({id,agent:'lecturer',text:'教学内容'});
(async()=>{
 {const f=fixture();f.narrator.enqueue(cred,message('a'));f.narrator.enqueue(cred,message('b'));assert.equal(f.pending.length,1);f.finishFetch(0,2);await tick();assert.equal(f.plays.length,1);f.audio().onended();await tick();assert.equal(f.pending.length,2);assert.equal(f.pending[1].body.chunk,1);f.finishFetch(1,2);await tick();f.audio().onended();await tick();assert.equal(f.pending[2].body.message_id,'b');assert.equal(f.pending[2].body.chunk,0);f.finishFetch(2);await tick();f.audio().onended();await tick();assert.equal(f.errors.length,0);assert.equal(f.events.at(-1).status,'idle');f.narrator.dispose();}
 {const f=fixture();f.narrator.enqueue(cred,message('old'));f.narrator.stop();assert.equal(f.pending[0].signal.aborted,true);f.narrator.enqueue({session_id:'session-b',token:'other'},message('new'));f.finishFetch(1);await tick();assert.equal(f.plays.length,1);const current=f.audio().src;f.finishFetch(0);await tick();assert.equal(f.plays.length,1);assert.equal(f.audio().src,current);assert.ok(!f.revoked.includes(current));assert.equal(f.events.filter(e=>e.status==='speaking').at(-1).id,'new');f.narrator.dispose();}
 {const f=fixture();f.narrator.enqueue(cred,message('old'));f.finishFetch(0,3);await tick();f.narrator.stop();f.narrator.enqueue(cred,message('new'));f.finishFetch(1);await tick();assert.equal(f.pending.length,2);assert.equal(f.plays.length,2);assert.equal(typeof f.audio().onended,'function');assert.equal(f.events.filter(e=>e.status==='speaking').at(-1).id,'new');f.narrator.dispose();assert.equal(f.mouth.current,0);}
 {const f=fixture();f.narrator.enqueue(cred,message('failed'));f.finishFetch(0,1,false);await tick();assert.equal(f.errors.length,1);assert.equal(f.plays.length,0);f.narrator.enqueue(cred,message('retry'));f.finishFetch(1);await tick();assert.equal(f.plays.length,1);f.narrator.dispose();}
 {const f=fixture();let completed=0;f.narrator.enqueue(cred,{...message('board-step'),board_id:'board-1',step_id:'step-1',onComplete:()=>completed++});assert.ok(f.pending[0].url.endsWith('/boards/board-1/speech'));assert.equal(f.pending[0].body.step_id,'step-1');assert.equal(f.pending[0].body.message_id,undefined);f.finishFetch(0,2);await tick();assert.equal(completed,0);f.audio().onended();await tick();f.finishFetch(1,2);await tick();assert.equal(completed,0);f.audio().onended();await tick();assert.equal(completed,1);f.narrator.dispose();}
 {const f=fixture();let completed=0;f.narrator.enqueue(cred,{...message('board-stop'),board_id:'board-1',step_id:'step-1',onComplete:()=>completed++});f.finishFetch(0);await tick();f.narrator.stop();await tick();assert.equal(completed,0);f.narrator.dispose();}
 console.log('Digital narration verified: ordered chunks, cancellation, stale session isolation, board-specific speech and question pause after the last audio chunk.');
})().catch(e=>{console.error(e);process.exitCode=1;});
