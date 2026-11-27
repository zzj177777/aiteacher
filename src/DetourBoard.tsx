import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,RotateCcw} from 'lucide-react';
import RichText from './RichText';
import AttentionText from './AttentionText';
import WhiteboardSurface from './WhiteboardSurface';
import {attentionSentences} from './attentionModel';
import type {NarrationMessage,SpeechCue,SyncState} from './digitalNarrator';
import {useBoardAttention,AttentionStatus} from './useBoardAttention';
import BoardRecovery,{type RecoveryReport} from './BoardRecovery';
import type {TeacherStyle} from './TeacherStylePicker';

export type ReturnAnchor={step_id:string;index:number;page:number;revealed:number;text_mode:'sentence'|'blocks';title:string};
export type Detour={teacher_style?:TeacherStyle;recovery?:RecoveryReport;id:string;status:string;resolution:string;anchor:ReturnAnchor;quote:string;question:string;error?:string;result:null|{title:string;intro:string;return_transition:string;steps:{id:string;title:string;board:string;focus:string;narration:string}[]}};

export default function DetourBoard({record,credential,boardId,messageId,voiceEnabled,autoPlay,busy,onSpeak,onStop,onHelp,onReturn}:{record:Detour;credential:{session_id:string;token:string};boardId:string;messageId:string;voiceEnabled:boolean;autoPlay:boolean;busy:boolean;onSpeak:(message:NarrationMessage)=>void;onStop:()=>void;onHelp:(contextKey:string)=>void;onReturn:(understood:boolean)=>void}){
 const key=`aiteacher.digital.detour.view.${record.id}`;
 const [saved]=useState(()=>{try{return JSON.parse(localStorage.getItem(key)||'{}');}catch{return {};}});
 const [index,setIndex]=useState(()=>Math.max(0,Math.min(Number.isInteger(saved.index)?saved.index:0,Math.max(0,(record.result?.steps.length||1)-1)))),[revealed,setRevealed]=useState(()=>Math.max(1,Number.isInteger(saved.revealed)?saved.revealed:1));
 const entered=useRef(false),callbacks=useRef({onSpeak,onStop});callbacks.current={onSpeak,onStop};
 const [spokenRange,setSpokenRange]=useState<SpeechCue|null>(null),[syncState,setSyncState]=useState<SyncState|'idle'>('idle');
 const generation=useRef(0),live=useRef(true);
 const steps=record.result?.steps||[],step=steps[index],units=attentionSentences(step?.board||'');
 const attention=useBoardAttention(credential,boardId,record.id,record.status==='completed');
 const teachingMarks=attention.record?.result?.steps.find(s=>s.step_id===step?.id)?.marks||[];
 useEffect(()=>{
  if(!step)return;callbacks.current.onStop();
  if(voiceEnabled&&(autoPlay||entered.current))speak();entered.current=true;
 },[step?.id]);
 useEffect(()=>{live.current=true;return()=>{live.current=false;generation.current++;callbacks.current.onStop();};},[]);
 useEffect(()=>{if(step){try{localStorage.setItem(key,JSON.stringify({index,revealed}));}catch{/* Optional preference. */}}},[index,revealed,step?.id]);
 function speak(){if(!step)return;callbacks.current.onStop();const stamp=++generation.current;setRevealed(0);setSpokenRange(null);setSyncState('loading');callbacks.current.onSpeak({id:`detour:${record.id}:${step.id}`,text:step.narration,agent:'lecturer',board_id:boardId,step_id:step.id,detour_id:record.id,
  board_units:units.map(unit=>({start:unit.start,end:unit.start+unit.text.length})),
  onProgress:cue=>{if(!live.current||generation.current!==stamp)return;setSpokenRange(cue);if(cue)setRevealed(old=>Math.max(old,cue.last_unit+1));},
  onSyncState:state=>{if(!live.current||generation.current!==stamp)return;setSyncState(state);if(state==='finished'||state==='unavailable')setRevealed(units.length);}});}
 function next(){if(index<steps.length-1){setIndex(v=>v+1);setRevealed(1);}else onReturn(true);}
 return <section className="whiteboard detour-board" aria-label="补讲支线白板" data-message-id={messageId} data-board-id={boardId} data-step-id={step?.id||record.id} data-detour-id={record.id} data-page={index}>
  <div className="whiteboard-toolbar"><div className="whiteboard-counter"><span className="detour-badge">补讲支线 · 原位置已保存</span>{record.teacher_style&&<span className="teacher-style-badge">{record.teacher_style.name}</span>}<BoardRecovery report={record.recovery}/></div><button disabled={busy} onClick={()=>onReturn(false)}>先回主线<ArrowRight size={14}/></button></div>
  <div className="detour-origin">主线暂停在：<strong><RichText text={record.anchor.title}/></strong></div>
  {record.status==='pending'?<div className="detour-loading" role="status"><h2>老师正在针对困惑准备补讲…</h2><p>这次只补当前卡住的地方，讲完再回到原白板。</p></div>:
   record.status!=='completed'||!step?<div className="detour-loading" role="alert"><h2>补讲暂时没准备好</h2><p>{record.error}</p><button onClick={()=>onHelp(record.id)}>保留困惑，重新补讲</button></div>:<>
    <div className="whiteboard-title"><div><span className="step-board-kicker">{index===0?record.result?.intro:'沿着刚才的补充再看一步'}</span><h2><RichText text={step.title}/></h2></div><span className="whiteboard-page-label">补讲 {index+1} / {steps.length}</span></div>
    <div className="attention-controls"><span>只解决这一个困惑</span><div className="attention-player"><button disabled={index===0} onClick={()=>{setIndex(v=>v-1);setRevealed(1);}}><ArrowLeft size={13}/>上一块</button><button onClick={speak}><RotateCcw size={13}/>重听</button><button disabled={revealed>=units.length} onClick={()=>{onStop();setRevealed(v=>Math.min(v+1,units.length));}}>下一句</button><button onClick={()=>{onStop();setRevealed(units.length);}}>看全文</button></div></div>
    <AttentionStatus state={attention} stepId={step.id}/><div className="board-sync-status" role="status">{syncState==='loading'?'正在准备补讲语音同步…':syncState==='paused'?'语音与文字已暂停':syncState==='unavailable'?'同步暂不可用，可手动阅读':'补讲按语音进度展开'}</div>
    <WhiteboardSurface pageKey={`${record.id}:${step.id}`}><AttentionText units={units} revealed={Math.min(revealed,units.length)} marks={teachingMarks} spokenRange={spokenRange}/></WhiteboardSurface>
   </>}
  <footer className="whiteboard-footer"><span className="detour-footer-note">补清这里，再接回原来的思路</span><div className="whiteboard-footer-right"><button className="whiteboard-confused" disabled={busy||record.status==='pending'} onClick={()=>onHelp(step?.id||record.id)}>没懂</button><button className="whiteboard-primary" disabled={busy||record.status!=='completed'} onClick={next}>听懂了，{index===steps.length-1?'回到主线':'继续'}<ArrowRight size={15}/></button></div></footer>
 </section>;
}
