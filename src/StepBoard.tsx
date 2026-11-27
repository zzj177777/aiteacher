import {lazy,Suspense,useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ArrowRight,Check,HelpCircle,RotateCcw,Play,Pause} from 'lucide-react';
import RichText from './RichText';
import BoardFailure,{type BoardDiagnostic,type BoardAttempt} from './BoardFailure';
import {parseChoiceQuestion,selectedChoices,choiceAnswer} from './boardQuestion';
import type {DrawingSpec} from './TeachingDrawing';
import type {NarrationMessage,SpeechCue,SyncState} from './digitalNarrator';
import WhiteboardSurface from './WhiteboardSurface';
import AttentionText from './AttentionText';
import {attentionSentences,attentionDelay} from './attentionModel';
import './attention-text.css';
import {useBoardAttention,AttentionStatus} from './useBoardAttention';
import {whiteboardBlocks} from './whiteboardBlocks';
import './step-board.css';
import './whiteboard.css';
import DetourBoard,{type Detour,type ReturnAnchor} from './DetourBoard';
import BoardHelp from './BoardHelp';
import BoardRecovery,{type RecoveryReport} from './BoardRecovery';
import type {TeacherStyle} from './TeacherStylePicker';
import './board-detour.css';
const TeachingDrawing=lazy(()=>import('./TeachingDrawing'));

type Credential={session_id:string;token:string};
export type BoardSource={teacher_style?:TeacherStyle;id:string;text:string;visuals?:DrawingSpec[]};
type Step={id:string;title:string;board:string;focus:string;narration:string;question?:string;source_quote:string;visual_ids:string[]};
type CheckResult={assessment_id?:string;id:string;step_id:string;answer:string;status:string;verdict?:string;feedback?:string;error?:string;diagnostic?:BoardDiagnostic;skipped:boolean};
type Board={recovery?:RecoveryReport;id:string;source_message_id:string;status:string;error?:string;diagnostic?:BoardDiagnostic;result:{title:string;steps:Step[]}|null;checks:Record<string,CheckResult>;understood_step_ids?:string[]};
type Assessment={id:string;agent:'assessment';status:string;step_id:string;question?:string;message?:string;error?:string;diagnostic?:BoardDiagnostic};
const cleared=(check:CheckResult|undefined)=>check?.status==='completed'&&(check.verdict==='correct'||check.verdict==='skipped');
const labels:Record<string,string>={correct:'这一步答对了',partial:'已经接近了，再试一下',incorrect:'换个角度再想想',uncertain:'还需要一点说明',not_answer:'这是一个问题，可以向老师提问',skipped:'已标记稍后再练'};

export default function StepBoard({credential,source,disabled,voiceEnabled,autoPlay=true,onSpeak,onStop,onAsk,onContinue,onOriginal,onRefresh}:{credential:Credential;source:BoardSource;disabled:boolean;voiceEnabled:boolean;autoPlay?:boolean;onSpeak:(message:NarrationMessage)=>void;onStop:()=>void;onAsk:(text:string)=>void;onContinue:()=>void;onOriginal:()=>void;onRefresh:()=>Promise<void>}){
 const [board,setBoard]=useState<Board|null>(null),[index,setIndex]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [questionReady,setQuestionReady]=useState(false),[answer,setAnswer]=useState(''),[checking,setChecking]=useState(false),[checkError,setCheckError]=useState('');
 const [assessment,setAssessment]=useState<Assessment|null>(null),[assessmentLoading,setAssessmentLoading]=useState(false),[assessmentError,setAssessmentError]=useState(''),[assessmentRetry,setAssessmentRetry]=useState(0);
 const [attempts,setAttempts]=useState<BoardAttempt[]>([]);
 const [attentionEnabled,setAttentionEnabled]=useState(()=>{try{return JSON.parse(localStorage.getItem('aiteacher.digital.attention.v1')||'{}').enabled!==false;}catch{return true;}});
 const [attentionPlaying,setAttentionPlaying]=useState(false);
 const [syncState,setSyncState]=useState<SyncState|'idle'>('idle'),[spokenRange,setSpokenRange]=useState<SpeechCue|null>(null);
 const [view,setView]=useState({stepId:'',page:0,revealed:1});
 const [detour,setDetour]=useState<Detour|null>(null),[branchLoading,setBranchLoading]=useState(true),[helpOpen,setHelpOpen]=useState(false),[quote,setQuote]=useState(''),[confusion,setConfusion]=useState(''),[helpBusy,setHelpBusy]=useState(false),[helpError,setHelpError]=useState(''),[bridge,setBridge]=useState('');
 const [readingBusy,setReadingBusy]=useState(false);
 const branchAutoPlay=useRef(false),selection=useRef({key:'',text:''}),helpKey=useRef(''),resumeAnchor=useRef<ReturnAnchor|null>(null),returnSpeech=useRef<NarrationMessage|null>(null),sourceEpoch=useRef(0);
 const root=useRef<HTMLElement>(null),entered=useRef(false),spoken=useRef(new Set<string>()),epoch=useRef(0),live=useRef(true),current=useRef('');
 const callbacks=useRef({onSpeak,onStop,onAsk,onContinue,onOriginal,onRefresh});callbacks.current={onSpeak,onStop,onAsk,onContinue,onOriginal,onRefresh};
 const step=board?.result?.steps[index];current.current=step?.id||'';
 const priorCheck=step?board?.checks[step.id]:undefined;
 const check=priorCheck?.assessment_id===assessment?.id?priorCheck:undefined;
 const choiceQuestion=assessment?.question?parseChoiceQuestion(assessment.question):null;
 const selected=choiceQuestion?selectedChoices(choiceQuestion.options,answer):[];
 const blocks=attentionEnabled?attentionSentences(step?.board||''):whiteboardBlocks(step?.board||'');
 const figures=step?.visual_ids.flatMap(id=>{const drawing=source.visuals?.find(v=>v.id===id);return drawing?[drawing]:[];})||[];
 const questionPage=figures.length+1,feedbackPage=questionPage+1;
 const page=view.stepId===step?.id?view.page:0;
 const total=board?.result?.steps.length||0;
 const storageKey=`aiteacher.digital.board.view.${credential.session_id}.${source.id}`;
 const attention=useBoardAttention(credential,board?.id,undefined,board?.status==='completed'&&!detour);
 const teachingMarks=attention.record?.result?.steps.find(s=>s.step_id===step?.id)?.marks||[];

 async function api<T>(path:string,body?:unknown,signal?:AbortSignal):Promise<T>{
  const response=await fetch(`/api/sessions/${credential.session_id}${path}`,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${credential.token}`,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),signal});
  const data=await response.json();if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'板书请求失败，请重试。'),{status:response.status});return data as T;
 }
 useEffect(()=>{live.current=true;return()=>{live.current=false;epoch.current++;callbacks.current.onStop();};},[]);
 useEffect(()=>{
  let alive=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let polls=0;
  sourceEpoch.current++;setLoading(true);setError('');setBoard(null);setAssessment(null);setAssessmentError('');setAssessmentRetry(0);setAttempts([]);spoken.current=new Set();setDetour(null);setBranchLoading(true);setHelpOpen(false);setHelpBusy(false);setReadingBusy(false);setBridge('');setQuote('');setConfusion('');setHelpError('');selection.current={key:'',text:''};returnSpeech.current=null;resumeAnchor.current=null;entered.current=false;
  function accept(value:Board){
   if(!alive)return;
   if(value.status==='pending'){
    if(polls++>70){setError('板书还在整理中，可以稍后重试或先看原文。');setLoading(false);return;}
    timer=setTimeout(()=>{void load(false);},1200);return;
   }
   if(value.status!=='completed'||!value.result){setBoard(value);setError(value.error||'板书暂未生成成功。');setLoading(false);return;}
   let position=0;
   try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved?.board_id===value.id&&Number.isInteger(saved.index))position=Math.max(0,Math.min(saved.index,value.result.steps.length-1));}catch{/* Optional presentation preference. */}
   setIndex(position);setBoard(value);setLoading(false);
  }
  async function load(create:boolean){try{
   let value:Board;
   if(create){try{value=await api<Board>(`/boards/source/${source.id}`,undefined,controller.signal);}catch(e){if((e as {status?:number}).status!==404)throw e;value=await api<Board>('/boards',{message_id:source.id},controller.signal);}}
   else value=await api<Board>(`/boards/source/${source.id}`,undefined,controller.signal);
   if(retry&&value.status==='failed')value=await api<Board>('/boards',{message_id:source.id,retry:true},controller.signal);
   accept(value);
  }catch(e){if(alive&&(e as Error).name!=='AbortError'){setError((e as Error).message);setLoading(false);}}}
  void load(true);
  return()=>{alive=false;controller.abort();if(timer)clearTimeout(timer);};
 },[credential.session_id,source.id,retry]);
 useEffect(()=>{
  if(!board||!step||index!==total-1||page<questionPage)return;
  let alive=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let polls=0;
  setAssessmentLoading(true);setAssessmentError('');
  async function load(first:boolean){try{
   let value:Assessment;
   try{value=await api<Assessment>(`/boards/${board!.id}/assessment`,undefined,controller.signal);}
   catch(e){if((e as {status?:number}).status!==404)throw e;value=await api<Assessment>(`/boards/${board!.id}/assessment`,{},controller.signal);}
   if(first&&assessmentRetry&&value.status==='failed')value=await api<Assessment>(`/boards/${board!.id}/assessment`,{retry:true},controller.signal);
   if(!alive)return;setAssessment(value);
   if(value.status==='pending'){
    if(polls++>75)throw new Error('测评 Agent 仍在准备，请稍后重试。');
    timer=setTimeout(()=>void load(false),1200);return;
   }
   if(value.status!=='completed')setAssessmentError(value.error||'测评题未准备好，请重试。');
   else await callbacks.current.onRefresh();
   if(alive)setAssessmentLoading(false);
  }catch(e){if(alive&&(e as Error).name!=='AbortError'){setAssessmentError((e as Error).message);setAssessmentLoading(false);}}}
  void load(true);
  return()=>{alive=false;controller.abort();if(timer)clearTimeout(timer);};
 },[board?.id,step?.id,page>=questionPage,assessmentRetry]);
 useEffect(()=>{
  if(!error)return;let alive=true;const controller=new AbortController();
  void api<{attempts:BoardAttempt[]}>(`/boards/source/${source.id}/diagnostics`,undefined,controller.signal).then(data=>{if(alive)setAttempts(data.attempts);}).catch(()=>{});
  return()=>{alive=false;controller.abort();};
 },[error,source.id,retry]);
 useEffect(()=>{
  epoch.current++;callbacks.current.onStop();setAnswer(step?board?.checks[step.id]?.answer||'':'');setCheckError('');setChecking(false);
  if(!board||!step)return;
  let saved:{board_id?:string;index?:number;page?:number;revealed?:number;text_mode?:string}={};
  try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}');}catch{/* Optional preference. */}
  const anchor=resumeAnchor.current?.step_id===step.id?resumeAnchor.current:null;resumeAnchor.current=null;
  if(anchor)saved={board_id:board.id,index,page:anchor.page,revealed:anchor.revealed,text_mode:anchor.text_mode};
  const resume=saved?.board_id===board.id&&saved.index===index;
  const compatible=attentionEnabled?saved?.text_mode==='sentence':saved?.text_mode!=='sentence';
  // Old per-page checks remain in history; only the final board hosts the section check.
  const savedPage=resume&&Number.isInteger(saved.page)?Math.max(0,Math.min(saved.page!,feedbackPage)):0;
  setView({stepId:step.id,page:index<total-1&&savedPage>=questionPage?0:savedPage,revealed:resume&&compatible&&Number.isInteger(saved.revealed)?Math.max(1,Math.min(saved.revealed!,blocks.length)):1});
  const hadCheck=!!board.checks[step.id],shouldSpeak=autoPlay||entered.current;entered.current=true;setQuestionReady(hadCheck||!voiceEnabled||!shouldSpeak);
  const key=board.id+':'+step.id;
  if(!anchor&&!hadCheck&&shouldSpeak&&voiceEnabled&&!spoken.current.has(key)&&!disabled){spoken.current.add(key);playStep();}
 },[board?.id,step?.id]);
 useEffect(()=>{if(!voiceEnabled)setQuestionReady(true);},[voiceEnabled]);
 useEffect(()=>{if(board&&step&&view.stepId===step.id){try{localStorage.setItem(storageKey,JSON.stringify({board_id:board.id,index,page:view.page,revealed:view.revealed,text_mode:attentionEnabled?'sentence':'blocks'}));}catch{/* Optional preference. */}}},[board?.id,step?.id,view,index,attentionEnabled]);
 useEffect(()=>{setAttentionPlaying(false);},[step?.id,page,disabled,attentionEnabled]);
 useEffect(()=>{
  const pause=()=>{if(document.hidden)setAttentionPlaying(false);};document.addEventListener('visibilitychange',pause);
  return()=>document.removeEventListener('visibilitychange',pause);
 },[]);
 useEffect(()=>{
  if(voiceEnabled||['loading','playing','paused'].includes(syncState)||!attentionPlaying||!attentionEnabled||page!==0||disabled||detour||helpOpen||!step||view.stepId!==step.id)return;
  if(view.revealed>=blocks.length){setAttentionPlaying(false);return;}
  const stepId=step.id;
  const timer=setTimeout(()=>setView(old=>old.stepId===stepId&&old.page===0?{...old,revealed:Math.min(blocks.length,old.revealed+1)}:old),attentionDelay(blocks[Math.max(0,view.revealed-1)].text));
  return()=>clearTimeout(timer);
 },[voiceEnabled,syncState,attentionPlaying,attentionEnabled,page,disabled,detour?.id,helpOpen,step?.id,view.stepId,view.revealed,blocks.length]);
 useEffect(()=>{
  if(!board||board.status!=='completed')return;
  let alive=true;const controller=new AbortController();setBranchLoading(true);
  void api<{detour:Detour|null}>(`/boards/${board.id}/detours/active`,undefined,controller.signal).then(value=>{if(alive){branchAutoPlay.current=false;setDetour(value.detour);if(value.detour)callbacks.current.onStop();}}).catch(e=>{if(alive&&(e as Error).name!=='AbortError')setHelpError('补讲记录恢复失败，请刷新后再试。');}).finally(()=>{if(alive)setBranchLoading(false);});
  return()=>{alive=false;controller.abort();};
 },[board?.id]);
 useEffect(()=>{
  if(!board||detour?.status!=='pending')return;
  let alive=true;const controller=new AbortController();
  const timer=setTimeout(()=>{void api<Detour>(`/boards/${board.id}/detours/${detour.id}`,undefined,controller.signal).then(value=>{if(alive)setDetour(value);}).catch(e=>{if(alive&&(e as Error).name!=='AbortError')setHelpError('补讲状态暂时无法读取，可以重开课堂恢复。');});},1200);
  return()=>{alive=false;clearTimeout(timer);controller.abort();};
 },[board?.id,detour]);
 useEffect(()=>{
  const capture=()=>{
   const chosen=window.getSelection();if(!chosen||chosen.isCollapsed||!chosen.rangeCount)return;
   const range=chosen.getRangeAt(0),element=range.commonAncestorContainer.nodeType===Node.ELEMENT_NODE?range.commonAncestorContainer as Element:range.commonAncestorContainer.parentElement;
   const surface=element?.closest('.whiteboard-surface'),owner=surface?.closest<HTMLElement>('.whiteboard');
   if(!surface||!owner||owner.dataset.boardId!==board?.id)return;
   const fragment=range.cloneContents();fragment.querySelectorAll('.katex-mathml,math,annotation').forEach(node=>node.remove());
   const text=(fragment.textContent||'').trim().slice(0,600),key=owner.dataset.stepId||'';if(!text)return;
   selection.current={key,text};if(helpOpen&&helpKey.current===key)setQuote(text);
  };
  document.addEventListener('selectionchange',capture);return()=>document.removeEventListener('selectionchange',capture);
 },[board?.id,helpOpen]);
 useEffect(()=>{if(!detour&&returnSpeech.current){const message=returnSpeech.current;returnSpeech.current=null;if(voiceEnabled)callbacks.current.onSpeak(message);}},[detour?.id]);
 function openHelp(key=step?.id||''){
  callbacks.current.onStop();setAttentionPlaying(false);setHelpError('');
  if(helpKey.current!==key){setQuote(selection.current.key===key?selection.current.text:'');setConfusion('');helpKey.current=key;}
  else if(selection.current.key===key)setQuote(selection.current.text);
  setHelpOpen(true);
 }
 async function requestHelp(){
  if(!board||!step||helpBusy||(!quote.trim()&&!confusion.trim()))return;
  const stamp=sourceEpoch.current,bid=board.id;
  const anchor=detour?.anchor||{step_id:step.id,index,page,revealed:view.revealed,text_mode:attentionEnabled?'sentence' as const:'blocks' as const,title:step.title};
  callbacks.current.onStop();setAttentionPlaying(false);setHelpBusy(true);setHelpError('');
  try{
   const value=await api<Detour>(`/boards/${bid}/detours`,{step_id:anchor.step_id,anchor:{page:anchor.page,revealed:anchor.revealed,text_mode:anchor.text_mode},quote,question:confusion,idempotency_key:crypto.randomUUID(),previous_detour_id:detour?.id||null});
   if(!live.current||stamp!==sourceEpoch.current)return;
   branchAutoPlay.current=true;setDetour(value);setHelpOpen(false);setBridge('');setBoard(old=>old?{...old,understood_step_ids:(old.understood_step_ids||[]).filter(id=>id!==anchor.step_id)}:old);
  }catch(e){if(live.current&&stamp===sourceEpoch.current)setHelpError((e as Error).message);}
  finally{if(live.current&&stamp===sourceEpoch.current)setHelpBusy(false);}
 }
 async function leaveDetour(understood:boolean){
  if(!board||!detour||helpBusy)return;const stamp=sourceEpoch.current,record=detour;setHelpBusy(true);setHelpError('');callbacks.current.onStop();
  try{
   await api(`/boards/${board.id}/detours/${record.id}/return`,{understood});
   if(!live.current||stamp!==sourceEpoch.current)return;
   const anchor=record.anchor;resumeAnchor.current=anchor;spoken.current.add(`${board.id}:${anchor.step_id}`);
   try{localStorage.setItem(storageKey,JSON.stringify({board_id:board.id,index:anchor.index,page:anchor.page,revealed:anchor.revealed,text_mode:anchor.text_mode}));}catch{/* Server return anchor remains durable. */}
   setIndex(anchor.index);setView({stepId:anchor.step_id,page:anchor.page,revealed:anchor.revealed});setHelpOpen(false);
   setBridge(understood?(record.result?.return_transition||`刚才补充了这个困惑。现在回到“${anchor.title}”，从原处继续。`):`先回到“${anchor.title}”原来的位置。刚才的困惑已保留，还可以再补讲。`);
   if(understood&&record.result){const first=record.result.steps[0];returnSpeech.current={id:`return:${record.id}`,agent:'lecturer',text:record.result.return_transition,board_id:board.id,step_id:first.id,detour_id:record.id,detour_part:'return'};}
   setDetour(null);
  }catch(e){if(live.current&&stamp===sourceEpoch.current)setHelpError((e as Error).message);}
  finally{if(live.current&&stamp===sourceEpoch.current)setHelpBusy(false);}
 }
 async function continueTeaching(){
  if(!board||!step||readingBusy||helpBusy||helpOpen||disabled||branchLoading)return;
  setAttentionPlaying(false);callbacks.current.onStop();
  if(page<figures.length){setView(old=>({...old,page:page+1}));return;}
  const stamp=sourceEpoch.current;setReadingBusy(true);setCheckError('');
  try{
   const value=await api<{understood_step_ids:string[]}>(`/boards/${board.id}/understood`,{step_id:step.id});
   if(!live.current||stamp!==sourceEpoch.current)return;
   setBoard(old=>old?{...old,understood_step_ids:value.understood_step_ids}:old);
   setBridge('');if(index<total-1)navigate(index+1);else revealQuestion();
  }catch(e){if(live.current&&stamp===sourceEpoch.current)setCheckError((e as Error).message);}
  finally{if(live.current&&stamp===sourceEpoch.current)setReadingBusy(false);}
 }
 function toggleAttention(){
  callbacks.current.onStop();setSpokenRange(null);setSyncState('idle');
  const enabled=!attentionEnabled;setAttentionPlaying(false);setAttentionEnabled(enabled);setView(old=>({...old,revealed:1}));
  try{localStorage.setItem('aiteacher.digital.attention.v1',JSON.stringify({enabled}));}catch{/* Optional display preference. */}
 }
 function playStep(){
  if(!step||!board)return;setAttentionPlaying(false);callbacks.current.onStop();setView({stepId:step.id,page:0,revealed:0});setSpokenRange(null);setSyncState('loading');const stamp=++epoch.current,stepId=step.id;setQuestionReady(false);
  callbacks.current.onSpeak({id:`board:${board.id}:${step.id}`,agent:'lecturer',text:step.narration,board_id:board.id,step_id:step.id,
   board_units:blocks.map(unit=>({start:unit.start,end:unit.start+unit.text.length})),
   onProgress:cue=>{if(!live.current||epoch.current!==stamp||current.current!==stepId)return;setSpokenRange(cue);if(cue)setView(old=>old.stepId===stepId&&old.page===0?{...old,revealed:Math.max(old.revealed,cue.last_unit+1)}:old);},
   onSyncState:state=>{if(!live.current||epoch.current!==stamp||current.current!==stepId)return;setSyncState(state);if(state==='unavailable'||state==='finished')setView(old=>old.stepId===stepId?{...old,revealed:blocks.length}:old);},
   onComplete:()=>{if(live.current&&epoch.current===stamp&&current.current===stepId)setQuestionReady(true);}});
 }
 function revealQuestion(){epoch.current++;callbacks.current.onStop();setQuestionReady(true);if(step)setView({stepId:step.id,page:questionPage,revealed:blocks.length});}
 function navigate(next:number){epoch.current++;callbacks.current.onStop();setIndex(next);}
 async function submit(skip=false){
  if(!board||!step||!assessment||assessment.status!=='completed'||checking||disabled||(!skip&&!answer.trim()))return;
  const boardId=board.id,stepId=step.id,stamp=epoch.current;
  callbacks.current.onStop();setChecking(true);setCheckError('');
  const body={assessment_id:assessment.id,step_id:step.id,answer:skip?'':answer,idempotency_key:crypto.randomUUID(),skip};
  try{
   let value=await api<CheckResult>(`/boards/${boardId}/answers`,body);
   if(value.status==='pending')throw new Error('这次回答仍在处理中，请稍后重新打开本段板书查看。');
   if(value.status!=='completed')throw new Error((value.error||'回答未能检查，请重试。')+(value.diagnostic?`（${value.diagnostic.code}，诊断编号 ${value.diagnostic.id.slice(0,8)}）`:''));
   if(!live.current||stamp!==epoch.current||current.current!==stepId)return;
   await callbacks.current.onRefresh();
   if(!live.current||stamp!==epoch.current||current.current!==stepId)return;
   setBoard(old=>old?.id===boardId?{...old,checks:{...old.checks,[stepId]:value}}:old);
   setView(old=>({...old,page:feedbackPage}));
  }catch(e){if(live.current&&stamp===epoch.current)setCheckError((e as Error).message);}
  finally{if(live.current&&current.current===stepId)setChecking(false);}
 }
 function formSubmit(e:FormEvent){e.preventDefault();void submit();}
 if(loading)return <section className="step-board-loading" aria-label="逐步板书"><span className="step-board-kicker">正在整理这段讲解</span><h2>把重点拆成几小步…</h2><p>逐块讲清楚，小结后再检查理解。</p><button type="button" onClick={onOriginal}>先看授课原文</button></section>;
 if(error||!board?.result||!step)return <section className="step-board-error" role="alert"><h2>暂用授课原文继续学习</h2><p>{error}</p><BoardFailure diagnostic={board?.diagnostic} attempts={attempts}/><BoardRecovery report={board?.recovery}/><details className="board-original-fallback" open><summary>保留的授课原文</summary><div><RichText text={source.text}/></div></details><div><button disabled={disabled} onClick={()=>setRetry(v=>v+1)}>重新整理板书</button><button onClick={onOriginal}>展开原文继续学习</button></div></section>;
 function turn(next:number){callbacks.current.onStop();setView(old=>({...old,page:next}));}
 function nextWriting(){
  callbacks.current.onStop();setAttentionPlaying(false);
  if(view.revealed<blocks.length)setView(old=>({...old,revealed:old.revealed+1}));
 }
 const onQuestion=page===questionPage,onFeedback=page===feedbackPage;
 const helpPanel=helpOpen&&<BoardHelp quote={quote} question={confusion} busy={helpBusy} error={helpError} onQuote={setQuote} onQuestion={setConfusion} onClose={()=>setHelpOpen(false)} onSubmit={()=>void requestHelp()}/>;
 if(detour)return <><DetourBoard key={detour.id} record={detour} credential={credential} boardId={board.id} messageId={source.id} voiceEnabled={voiceEnabled} autoPlay={branchAutoPlay.current} busy={helpBusy||helpOpen||disabled} onSpeak={onSpeak} onStop={onStop} onHelp={openHelp} onReturn={value=>void leaveDetour(value)}/>{!helpOpen&&helpError&&<p className="whiteboard-check-error" role="alert">{helpError}</p>}{helpPanel}</>;
 return <><section ref={root} className="step-board whiteboard" aria-label="固定课堂白板" data-message-id={source.id} data-board-id={board.id} data-step-id={step.id} data-page={page}>
  <div className="whiteboard-toolbar"><button aria-label="回看上一步板书" disabled={index===0||checking||helpBusy||helpOpen||disabled} onClick={()=>navigate(index-1)}><ArrowLeft size={15}/>上一块</button><div className="whiteboard-counter"><span>白板 <strong>{index+1}</strong> / {total}</span>{source.teacher_style&&<span className="teacher-style-badge">本段：{source.teacher_style.name}</span>}<BoardRecovery report={board.recovery}/></div><button aria-label="重听这一步" disabled={checking||helpBusy||helpOpen||disabled} onClick={playStep}><RotateCcw size={14}/>重听这步</button></div>
  {bridge&&<div className="main-return-bridge" role="status"><span>接回主线</span><div className="return-bridge-text"><RichText text={bridge}/></div><button aria-label="收起衔接说明" onClick={()=>setBridge('')}>×</button></div>}
  <div className="whiteboard-title"><div><span className="step-board-kicker">{onFeedback?'看看本小节的反馈':onQuestion?'这一小节讲完了，试一道题':page>0?'用一张图看明白':'这块白板，只弄懂一件事'}</span><h2><RichText text={onQuestion||onFeedback?'测评 Agent · 小节检查':step.title}/></h2></div><span className="whiteboard-page-label">{onFeedback?'小结反馈':onQuestion?'小结检查':page>0?`图 ${page} / ${figures.length}`:`${attentionEnabled?'句子':'板书'} ${Math.min(view.revealed,blocks.length)} / ${blocks.length}`}</span></div>
  {(onQuestion||onFeedback)&&<div className="assessment-agent-label"><strong>测评 Agent</strong><span>独立出题与判答 · 白板呈现</span></div>}
  {onQuestion&&assessmentLoading&&<p role="status">测评 Agent 正在根据本小节讲解准备题目…</p>}
  {onQuestion&&assessmentError&&<div role="alert"><p>{assessmentError}</p>{assessment?.diagnostic&&<BoardFailure diagnostic={assessment.diagnostic} attempts={[]}/>}<button disabled={assessmentLoading} onClick={()=>setAssessmentRetry(v=>v+1)}>重试测评</button></div>}
  {page===0&&<div className="attention-controls" aria-label="文字呈现实验控制"><button className="attention-experiment" aria-pressed={attentionEnabled} onClick={toggleAttention}>逐句呈现{attentionEnabled?' 开':' 关'}</button>{attentionEnabled&&<div className="attention-player"><button aria-label="回看上一句" disabled={view.revealed<=1||checking||disabled} onClick={()=>{callbacks.current.onStop();setAttentionPlaying(false);setView(old=>({...old,revealed:Math.max(1,old.revealed-1)}));}}><ArrowLeft size={13}/>上一句</button><button aria-label={attentionPlaying?'暂停句子播放':'自动播放句子'} aria-pressed={attentionPlaying} disabled={view.revealed>=blocks.length||checking||disabled} onClick={()=>{if(voiceEnabled)playStep();else setAttentionPlaying(v=>!v);}}>{attentionPlaying?<Pause size={13}/>:<Play size={13}/>} {voiceEnabled?'语音跟读':attentionPlaying?'暂停':'自动'}</button><button disabled={checking||view.revealed>=blocks.length} onClick={nextWriting}>下一句<ArrowRight size={13}/></button><button disabled={checking} onClick={()=>{callbacks.current.onStop();setAttentionPlaying(false);setView(old=>({...old,revealed:blocks.length}));}}>看全文</button></div>}{!attentionEnabled&&<button disabled={view.revealed>=blocks.length} onClick={nextWriting}>写下一笔</button>}</div>}
  {page===0&&<AttentionStatus state={attention} stepId={step.id}/>}{page===0&&<div className="board-sync-status" role="status">{syncState==='loading'?'正在准备语音与板书对齐…':syncState==='playing'?'跟随老师讲解，内容自动展开':syncState==='paused'?'已暂停，文字进度也已暂停':syncState==='unavailable'?'本段同步暂不可用，已展开全文，可继续阅读或重听':'可重听并跟随语音逐块阅读'}</div>}
  <WhiteboardSurface pageKey={`${step.id}:${page}`}>
   {page===0?<AttentionText units={blocks} revealed={view.revealed} marks={teachingMarks} spokenRange={spokenRange}/>:

    page<questionPage?<Suspense fallback={<p>正在准备本页图示…</p>}><TeachingDrawing key={figures[page-1].id} spec={figures[page-1]}/></Suspense>:
    onQuestion?<section className="whiteboard-exercise" aria-label="本小节理解检查"><div className="step-board-question-text"><RichText text={choiceQuestion?.prompt||assessment?.question||''}/></div>
     {choiceQuestion?<fieldset className="step-board-choices" disabled={checking||disabled||assessmentLoading||assessment?.status!=='completed'||check?.verdict==='correct'}><legend>{choiceQuestion.multiple?'多选 · 可以选择多个选项':'单选 · 点击一个选项'}</legend>{choiceQuestion.options.map(option=><label key={option.id} className={`step-board-choice${selected.includes(option.id)?' selected':''}`}><input type={choiceQuestion.multiple?'checkbox':'radio'} name={`board-choice-${step.id}`} value={option.id} checked={selected.includes(option.id)} onChange={()=>{const next=choiceQuestion.multiple?(selected.includes(option.id)?selected.filter(id=>id!==option.id):[...selected,option.id]):[option.id];setAnswer(choiceAnswer(choiceQuestion.options,next));}}/><span className="step-board-choice-letter">{option.id}</span><span className="step-board-choice-text"><RichText text={option.text}/></span></label>)}</fieldset>:
      <form id={`answer-${step.id}`} onSubmit={formSubmit}><label className="step-board-answer-label">你的回答<textarea aria-label="本小节问题的回答" rows={3} maxLength={1200} value={answer} onChange={e=>setAnswer(e.target.value)} disabled={checking||disabled||assessmentLoading||assessment?.status!=='completed'||check?.verdict==='correct'} placeholder="简单说说你的想法，或者写出答案…"/></label></form>}
    </section>:
    <section className={`whiteboard-result ${check?.verdict||''}`} aria-label="本小节答题反馈"><span className="whiteboard-result-icon">{check?.verdict==='correct'?<Check size={32}/>:<HelpCircle size={32}/>}</span><h3>{labels[check?.verdict||'']||'这一步还没有作答'}</h3><div className="whiteboard-result-text"><RichText text={check?.feedback||'先看题目，试着说出你的想法。'}/></div>{check?.answer&&<p className="whiteboard-submitted"><span>你的回答</span><RichText text={check.answer}/></p>}<small>{check?.skipped?'这题可以回来补练，跳过不代表掌握。':'单题反馈不代表长期掌握。'}</small></section>}
  </WhiteboardSurface>
  {checkError&&<p className="whiteboard-check-error" role="alert">{checkError}</p>}
  {!helpOpen&&helpError&&<p className="whiteboard-check-error" role="alert">{helpError}</p>}
  <footer className="whiteboard-footer"><div className="whiteboard-footer-left">
   {page>0?<button disabled={checking||readingBusy} onClick={()=>turn(onFeedback?questionPage:page-1)}><ArrowLeft size={14}/>{onFeedback?'看题目':'回看'}</button>:<button onClick={onOriginal}>讲稿与记录</button>}
  </div><div className="whiteboard-footer-right">
   <button className="whiteboard-confused" disabled={checking||helpBusy||readingBusy||disabled||branchLoading} onClick={()=>openHelp()}>没懂</button>
   {!onQuestion&&!onFeedback?<><span className="whiteboard-voice-hint">{branchLoading?'正在恢复课堂…':questionReady?'按自己的节奏继续':'可以随时停下来问'}</span><button className="whiteboard-primary" disabled={checking||readingBusy||helpBusy||helpOpen||disabled||branchLoading} onClick={()=>void continueTeaching()}>{readingBusy?'正在保存…':'听懂了，继续'}<ArrowRight size={15}/></button></>:
    onQuestion?<><button disabled={checking||disabled||assessmentLoading||assessment?.status!=='completed'} onClick={()=>void submit(true)}>稍后再练</button>{check?.verdict==='correct'?<button className="whiteboard-primary" onClick={()=>turn(feedbackPage)}>查看反馈<ArrowRight size={15}/></button>:<button className="whiteboard-primary" disabled={checking||disabled||assessmentLoading||assessment?.status!=='completed'||!answer.trim()} onClick={()=>void submit()}>{checking?'正在检查…':'检查本小节'}</button>}</>:
    cleared(check)?<>{check?.skipped&&<button onClick={()=>turn(questionPage)}>回来补答</button>}<button className="whiteboard-primary" disabled={disabled} onClick={()=>{callbacks.current.onStop();onContinue();}}>继续课程<ArrowRight size={15}/></button></>:
    <><button disabled={checking||disabled} onClick={()=>onAsk('请根据刚才测评的回答和反馈，针对我的薄弱点补讲，先不要推进下一节点。')}>请老师补讲</button><button className="whiteboard-primary" disabled={checking||disabled} onClick={()=>turn(questionPage)}>再试一次<ArrowRight size={15}/></button></>}
  </div></footer>
 </section>{helpPanel}</>;
}
