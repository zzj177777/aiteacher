export type SpeechCue={first_unit:number;last_unit:number;start:number;end:number|null};
export type SyncState='loading'|'playing'|'paused'|'unavailable'|'stopped'|'finished';
export type NarrationMessage={id:string;text:string;agent:string;board_id?:string;step_id?:string;detour_id?:string;detour_part?:'step'|'return';board_units?:{start:number;end:number}[];onProgress?:(cue:SpeechCue|null)=>void;onSyncState?:(state:SyncState)=>void;onComplete?:()=>void};
export type NarrationCredential={session_id:string;token:string};
export type VoiceStatus='idle'|'loading'|'speaking'|'paused'|'blocked';
type AudioPacket={blob:Blob;chunks:number;cue:SpeechCue|null;aligned:boolean};

/** Serial playback with explicit cancellation. Audio completion never changes a lesson. */
export class DigitalNarrator {
 private voiceId:string|undefined;
 private audio=new Audio();private context?:AudioContext;private analyser?:AnalyserNode;
 private controller?:AbortController;private objectUrl='';private epoch=0;private pumping:number|null=null;
 private queue:{credential:NarrationCredential;message:NarrationMessage}[]=[];
 private finishPlayback?:()=>void;private frame=0;
 private progress?:()=>void;private currentMessage?:NarrationMessage;
 private currentAligned=true;
 constructor(private mouth:{current:number},private update:(status:VoiceStatus,message?:NarrationMessage)=>void,private failed:(message:string)=>void){this.audio.preload='auto';}
 unlock(){
  try{
   if(!this.context){this.context=new AudioContext();this.analyser=this.context.createAnalyser();this.analyser.fftSize=256;this.context.createMediaElementSource(this.audio).connect(this.analyser);this.analyser.connect(this.context.destination);}
   void this.context.resume().catch(()=>{});
  }catch{/* Playback is still usable without lip synchronization. */}
 }
 enqueue(credential:NarrationCredential,message:NarrationMessage){this.queue.push({credential,message});void this.pump();}
 setVoice(voiceId:string){if(this.voiceId===voiceId)return;this.stop();this.voiceId=voiceId;}
 pause(){if(this.audio.paused||!this.currentMessage)return;this.audio.pause();cancelAnimationFrame(this.frame);this.mouth.current=0;this.currentMessage.onSyncState?.('paused');this.update('paused',this.currentMessage);}
 resume(){const message=this.currentMessage;if(!message||!this.audio.paused)return;const epoch=this.epoch;void this.audio.play().then(()=>{if(epoch!==this.epoch)return;message.onSyncState?.(this.currentAligned?'playing':'unavailable');this.update('speaking',message);this.trackMouth();}).catch(()=>{if(epoch===this.epoch)this.failed('播放暂未恢复，请点击重听。');});}
 stop(){
  this.currentMessage?.onProgress?.(null);this.currentMessage?.onSyncState?.('stopped');this.currentMessage=undefined;this.progress=undefined;
  this.epoch++;this.queue=[];this.pumping=null;this.controller?.abort();this.audio.pause();this.finishPlayback?.();this.finishPlayback=undefined;
  this.audio.onended=null;this.audio.onerror=null;this.audio.removeAttribute('src');this.audio.load();if(this.objectUrl)URL.revokeObjectURL(this.objectUrl);this.objectUrl='';
  cancelAnimationFrame(this.frame);this.mouth.current=0;this.update('idle');
 }
 private trackMouth(){
  const data=new Uint8Array(128);
  cancelAnimationFrame(this.frame);
  const tick=()=>{if(this.audio.paused){this.mouth.current=0;return;}this.progress?.();if(this.analyser){this.analyser.getByteTimeDomainData(data);const rms=Math.sqrt(data.reduce((sum,v)=>sum+((v-128)/128)**2,0)/data.length);this.mouth.current=Math.min(1,rms*5);}this.frame=requestAnimationFrame(tick);};tick();
 }
 private async pump(){
  const epoch=this.epoch;if(this.pumping===epoch)return;this.pumping=epoch;
  try{
   while(this.queue.length&&epoch===this.epoch){
    const {credential,message}=this.queue.shift()!;let chunks=1;this.currentMessage=message;
    const isBoard=!!message.board_id&&!!message.step_id,isSync=isBoard&&!!message.board_units?.length&&message.detour_part!=='return';
    message.onSyncState?.('loading');
    const loadChunk=async(chunk:number):Promise<AudioPacket>=>{
     this.controller=new AbortController();
     const response=await fetch(isBoard&&message.detour_id?`/api/sessions/${credential.session_id}/boards/${message.board_id}/detours/${message.detour_id}/speech`:isBoard?`/api/sessions/${credential.session_id}/boards/${message.board_id}/speech`:`/api/sessions/${credential.session_id}/digital-speech`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential.token}`},body:JSON.stringify({...(this.voiceId?{voice_id:this.voiceId}:{}),...(isSync?{synchronized:true,units:message.board_units}:{}),...(isBoard?{step_id:message.step_id,chunk,...(message.detour_id?{part:message.detour_part||'step'}:{})}:{message_id:message.id,chunk})}),signal:this.controller.signal});
     if(!response.ok){const data=await response.json();throw new Error(data.detail||'语音生成失败，可以继续看板书。');}
     if(isSync){
      const data=await response.json();
      if(typeof data.audio!=='string')throw new Error('同步语音格式异常，请重听。');
      const bytes=Uint8Array.from(atob(data.audio),char=>char.charCodeAt(0));
      const cue=data.cue as SpeechCue|null;
      if(cue&&(!Number.isInteger(cue.first_unit)||!Number.isInteger(cue.last_unit)||cue.first_unit<0||cue.last_unit<cue.first_unit||cue.last_unit>=message.board_units!.length||!Number.isFinite(cue.start)||cue.start<0||cue.end!==null&&(!Number.isFinite(cue.end)||cue.end<cue.start)))throw new Error('语音同步位置无效，请重听。');
      return {blob:new Blob([bytes],{type:'audio/mpeg'}),chunks:data.chunks,cue,aligned:data.aligned===true};
     }
     return {blob:await response.blob(),chunks:Number(response.headers.get('X-Speech-Chunks'))||1,cue:null,aligned:false};
    };
    let prefetched:Promise<{value:AudioPacket}|{error:unknown}>|undefined;
    for(let chunk=0;chunk<chunks&&epoch===this.epoch;chunk++){
     this.update('loading',message);
     const loaded=prefetched?await prefetched:{value:await loadChunk(chunk)};
     if(epoch!==this.epoch)return;if('error' in loaded)throw loaded.error;
     const packet=loaded.value;
     if(isSync&&(!Number.isInteger(packet.chunks)||packet.chunks<1||packet.chunks>10000))throw new Error('同步语音分段数量异常，请重听。');
     chunks=isSync?packet.chunks:Math.max(1,Math.min(301,packet.chunks||1));
     this.currentAligned=!isSync||packet.aligned;
     // One look-ahead request reduces gaps, with errors retained until that chunk is needed.
     prefetched=isSync&&chunk+1<chunks?loadChunk(chunk+1).then(value=>({value}),error=>({error})):undefined;
     if(isSync&&!packet.aligned)message.onSyncState?.('unavailable');
     let lastCueKey='';
     this.progress=()=>{const cue=packet.cue,time=this.audio.currentTime;const current=cue&&time>=cue.start&&(cue.end===null||time<cue.end)?cue:null;const key=current?`${current.first_unit}:${current.last_unit}`:'none';if(key!==lastCueKey){lastCueKey=key;message.onProgress?.(current);}};
     this.objectUrl=URL.createObjectURL(packet.blob);this.audio.src=this.objectUrl;
     await new Promise<void>((resolve,reject)=>{
      const cleanup=()=>{if(epoch!==this.epoch)return;this.audio.onended=null;this.audio.onerror=null;this.finishPlayback=undefined;cancelAnimationFrame(this.frame);this.mouth.current=0;this.progress=undefined;message.onProgress?.(null);};
      this.finishPlayback=()=>{cleanup();resolve();};this.audio.onended=()=>{cleanup();resolve();};this.audio.onerror=()=>{cleanup();reject(new Error('音频无法播放，请点击重听。'));};
      this.audio.play().then(()=>{if(epoch===this.epoch){if(!isSync||packet.aligned)message.onSyncState?.('playing');this.update('speaking',message);this.trackMouth();}}).catch(e=>{cleanup();reject(e);});
     });
     if(epoch!==this.epoch)return;
     if(this.objectUrl){URL.revokeObjectURL(this.objectUrl);this.objectUrl='';}
    }
    if(epoch===this.epoch){message.onSyncState?.(isSync&&!this.currentAligned?'unavailable':'finished');message.onComplete?.();this.currentMessage=undefined;}
   }
  }catch(e){if(epoch===this.epoch&&(e as Error).name!=='AbortError'){this.queue=[];this.currentMessage?.onProgress?.(null);this.currentMessage?.onSyncState?.('unavailable');this.currentMessage=undefined;this.progress=undefined;this.update((e as Error).name==='NotAllowedError'?'blocked':'idle');this.failed((e as Error).name==='NotAllowedError'?'浏览器需要一次点击才能播放声音，请点击「重听」。':(e as Error).message);}}
  finally{if(this.pumping===epoch){this.pumping=null;this.mouth.current=0;this.update('idle');}}
 }
 dispose(){this.stop();void this.context?.close();}
}
