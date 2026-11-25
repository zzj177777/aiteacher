export type NarrationMessage={id:string;text:string;agent:string;board_id?:string;step_id?:string;onComplete?:()=>void};
export type NarrationCredential={session_id:string;token:string};
export type VoiceStatus='idle'|'loading'|'speaking'|'blocked';

/** Serial playback with explicit cancellation. Audio completion never changes a lesson. */
export class DigitalNarrator {
 private audio=new Audio();private context?:AudioContext;private analyser?:AnalyserNode;
 private controller?:AbortController;private objectUrl='';private epoch=0;private pumping:number|null=null;
 private queue:{credential:NarrationCredential;message:NarrationMessage}[]=[];
 private finishPlayback?:()=>void;private frame=0;
 constructor(private mouth:{current:number},private update:(status:VoiceStatus,message?:NarrationMessage)=>void,private failed:(message:string)=>void){this.audio.preload='auto';}
 unlock(){
  try{
   if(!this.context){this.context=new AudioContext();this.analyser=this.context.createAnalyser();this.analyser.fftSize=256;this.context.createMediaElementSource(this.audio).connect(this.analyser);this.analyser.connect(this.context.destination);}
   void this.context.resume().catch(()=>{});
  }catch{/* Playback is still usable without lip synchronization. */}
 }
 enqueue(credential:NarrationCredential,message:NarrationMessage){this.queue.push({credential,message});void this.pump();}
 stop(){
  this.epoch++;this.queue=[];this.pumping=null;this.controller?.abort();this.audio.pause();this.finishPlayback?.();this.finishPlayback=undefined;
  this.audio.onended=null;this.audio.onerror=null;this.audio.removeAttribute('src');this.audio.load();if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);this.objectUrl='';
  cancelAnimationFrame(this.frame);this.mouth.current=0;this.update('idle');
 }
 private trackMouth(){
  const data=new Uint8Array(128);
  const tick=()=>{if(this.audio.paused){this.mouth.current=0;return;}if(this.analyser){this.analyser.getByteTimeDomainData(data);const rms=Math.sqrt(data.reduce((sum,v)=>sum+((v-128)/128)**2,0)/data.length);this.mouth.current=Math.min(1,rms*5);}this.frame=requestAnimationFrame(tick);};tick();
 }
 private async pump(){
  const epoch=this.epoch;if(this.pumping===epoch)return;this.pumping=epoch;
  try{
   while(this.queue.length&&epoch===this.epoch){
    const {credential,message}=this.queue.shift()!;let chunks=1;
    for(let chunk=0;chunk<chunks&&epoch===this.epoch;chunk++){
     this.controller=new AbortController();this.update('loading',message);
     const isBoard=!!message.board_id&&!!message.step_id;
     const response=await fetch(isBoard?`/api/sessions/${credential.session_id}/boards/${message.board_id}/speech`:`/api/sessions/${credential.session_id}/digital-speech`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential.token}`},body:JSON.stringify(isBoard?{step_id:message.step_id,chunk}:{message_id:message.id,chunk}),signal:this.controller.signal});
     if(!response.ok){const data=await response.json();throw new Error(data.detail||'语音生成失败，可以继续看板书。');}
     chunks=Math.max(1,Math.min(301,Number(response.headers.get('X-Speech-Chunks'))||1));
     const blob=await response.blob();if(epoch!==this.epoch)return;
     this.objectUrl=URL.createObjectURL(blob);this.audio.src=this.objectUrl;
     await new Promise<void>((resolve,reject)=>{
      const cleanup=()=>{if(epoch!==this.epoch)return;this.audio.onended=null;this.audio.onerror=null;this.finishPlayback=undefined;cancelAnimationFrame(this.frame);this.mouth.current=0;};
      this.finishPlayback=()=>{cleanup();resolve();};this.audio.onended=()=>{cleanup();resolve();};this.audio.onerror=()=>{cleanup();reject(new Error('音频无法播放，请点击重听。'));};
      this.audio.play().then(()=>{if(epoch===this.epoch){this.update('speaking',message);this.trackMouth();}}).catch(e=>{cleanup();reject(e);});
     });
     if(epoch!==this.epoch)return;
     if(this.objectUrl){URL.revokeObjectURL(this.objectUrl);this.objectUrl='';}
    }
    if(epoch===this.epoch)message.onComplete?.();
   }
  }catch(e){if(epoch===this.epoch&&(e as Error).name!=='AbortError'){this.queue=[];this.update((e as Error).name==='NotAllowedError'?'blocked':'idle');this.failed((e as Error).name==='NotAllowedError'?'浏览器需要一次点击才能播放声音，请点击「重听」。':(e as Error).message);}}
  finally{if(this.pumping===epoch){this.pumping=null;this.mouth.current=0;this.update('idle');}}
 }
 dispose(){this.stop();void this.context?.close();}
}
