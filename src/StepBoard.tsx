import {lazy,Suspense,useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ArrowRight,Check,HelpCircle,Play,RotateCcw} from 'lucide-react';
import RichText from './RichText';
import {parseChoiceQuestion,selectedChoices,choiceAnswer} from './boardQuestion';
import type {DrawingSpec} from './TeachingDrawing';
import type {NarrationMessage} from './digitalNarrator';
import './step-board.css';
const TeachingDrawing=lazy(()=>import('./TeachingDrawing'));

type Credential={session_id:string;token:string};
export type BoardSource={id:string;text:string;visuals?:DrawingSpec[]};
type Step={id:string;title:string;board:string;focus:string;narration:string;question:string;source_quote:string;visual_ids:string[]};
type CheckResult={id:string;step_id:string;answer:string;status:string;verdict?:string;feedback?:string;error?:string;skipped:boolean};
type Board={id:string;source_message_id:string;status:string;error?:string;result:{title:string;steps:Step[]}|null;checks:Record<string,CheckResult>};
const cleared=(check:CheckResult|undefined)=>check?.status==='completed'&&(check.verdict==='correct'||check.verdict==='skipped');
const labels:Record<string,string>={correct:'这一步答对了',partial:'已经接近了，再试一下',incorrect:'换个角度再想想',uncertain:'还需要一点说明',not_answer:'这是一个问题，可以向老师提问',skipped:'已标记稍后再练'};

export default function StepBoard({credential,source,disabled,voiceEnabled,autoPlay=true,onSpeak,onStop,onAsk,onContinue,onOriginal}:{credential:Credential;source:BoardSource;disabled:boolean;voiceEnabled:boolean;autoPlay?:boolean;onSpeak:(message:NarrationMessage)=>void;onStop:()=>void;onAsk:(text:string)=>void;onContinue:()=>void;onOriginal:()=>void}){
 const [board,setBoard]=useState<Board|null>(null),[index,setIndex]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [questionVisible,setQuestionVisible]=useState(false),[answer,setAnswer]=useState(''),[checking,setChecking]=useState(false),[checkError,setCheckError]=useState('');
 const root=useRef<HTMLElement>(null),entered=useRef(false),spoken=useRef(new Set<string>()),epoch=useRef(0),live=useRef(true),current=useRef('');
 const callbacks=useRef({onSpeak,onStop,onAsk,onContinue,onOriginal});callbacks.current={onSpeak,onStop,onAsk,onContinue,onOriginal};
 const step=board?.result?.steps[index];current.current=step?.id||'';
 const check=step?board?.checks[step.id]:undefined;
 const choiceQuestion=step?parseChoiceQuestion(step.question):null;
 const selected=choiceQuestion?selectedChoices(choiceQuestion.options,answer):[];
 const total=board?.result?.steps.length||0;
 const storageKey=`aiteacher.digital.board.view.${credential.session_id}.${source.id}`;

 async function api<T>(path:string,body?:unknown,signal?:AbortSignal):Promise<T>{
  const response=await fetch(`/api/sessions/${credential.session_id}${path}`,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${credential.token}`,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),signal});
  const data=await response.json();if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'板书请求失败，请重试。'),{status:response.status});return data as T;
 }
 useEffect(()=>{live.current=true;return()=>{live.current=false;epoch.current++;callbacks.current.onStop();};},[]);
 useEffect(()=>{
  let alive=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let polls=0;
  setLoading(true);setError('');setBoard(null);spoken.current=new Set();
  function accept(value:Board){
   if(!alive)return;
   if(value.status==='pending'){
    if(polls++>70){setError('板书还在整理中，可以稍后重试或先看原文。');setLoading(false);return;}
    timer=setTimeout(()=>{void load(false);},1200);return;
   }
   if(value.status!=='completed'||!value.result){setError(value.error||'板书暂未生成成功。');setLoading(false);return;}
   let position=0;
   try{const saved=JSON.parse(localStorage.getItem(storageKey)||'null');if(saved?.board_id===value.id&&Number.isInteger(saved.index))position=Math.max(0,Math.min(saved.index,value.result.steps.length-1));}catch{/* Optional presentation preference. */}
   const firstOpen=value.result.steps.findIndex(s=>!cleared(value.checks[s.id]));
   if(firstOpen>=0)position=Math.min(position,firstOpen);
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
  epoch.current++;callbacks.current.onStop();setAnswer(step?board?.checks[step.id]?.answer||'':'');setCheckError('');setChecking(false);
  if(!board||!step)return;
  root.current?.closest('.digital-board-scroll')?.scrollTo({top:0});
  try{localStorage.setItem(storageKey,JSON.stringify({board_id:board.id,index}));}catch{/* Optional presentation preference. */}
  const hadCheck=!!board.checks[step.id],shouldSpeak=autoPlay||entered.current;entered.current=true;setQuestionVisible(hadCheck||!voiceEnabled||!shouldSpeak);
  const key=board.id+':'+step.id;
  if(!hadCheck&&shouldSpeak&&voiceEnabled&&!spoken.current.has(key)&&!disabled){spoken.current.add(key);playStep();}
 },[board?.id,step?.id]);
 useEffect(()=>{if(!voiceEnabled)setQuestionVisible(true);},[voiceEnabled]);
 function playStep(){
  if(!step||!board)return;callbacks.current.onStop();const stamp=++epoch.current,stepId=step.id;setQuestionVisible(false);
  callbacks.current.onSpeak({id:`board:${board.id}:${step.id}`,agent:'lecturer',text:step.narration,board_id:board.id,step_id:step.id,
   onComplete:()=>{if(live.current&&epoch.current===stamp&&current.current===stepId)setQuestionVisible(true);}});
 }
 function revealQuestion(){epoch.current++;callbacks.current.onStop();setQuestionVisible(true);}
 function navigate(next:number){epoch.current++;callbacks.current.onStop();setIndex(next);}
 async function submit(skip=false){
  if(!board||!step||checking||disabled||(!skip&&!answer.trim()))return;
  const boardId=board.id,stepId=step.id,stamp=epoch.current;
  callbacks.current.onStop();setChecking(true);setCheckError('');
  const body={step_id:step.id,answer:skip?'':answer,idempotency_key:crypto.randomUUID(),skip};
  try{
   let value=await api<CheckResult>(`/boards/${boardId}/answers`,body);
   if(value.status==='pending')throw new Error('这次回答仍在处理中，请稍后重新打开本段板书查看。');
   if(value.status!=='completed')throw new Error(value.error||'回答未能检查，请重试。');
   if(!live.current||stamp!==epoch.current||current.current!==stepId)return;
   setBoard(old=>old?.id===boardId?{...old,checks:{...old.checks,[stepId]:value}}:old);
  }catch(e){if(live.current&&stamp===epoch.current)setCheckError((e as Error).message);}
  finally{if(live.current&&current.current===stepId)setChecking(false);}
 }
 function formSubmit(e:FormEvent){e.preventDefault();void submit();}
 if(loading)return <section className="step-board-loading" aria-label="逐步板书"><span className="step-board-kicker">正在整理这段讲解</span><h2>把重点拆成几小步…</h2><p>每步一块短板书，一个小问题。</p><button type="button" onClick={onOriginal}>先看授课原文</button></section>;
 if(error||!board?.result||!step)return <section className="step-board-error" role="alert"><h2>这段板书暂时没准备好</h2><p>{error}</p><div><button disabled={disabled} onClick={()=>setRetry(v=>v+1)}>重新整理板书</button><button onClick={onOriginal}>展开原文继续学习</button></div></section>;
 const focusStart=step.board.indexOf(step.focus);
 const finished=board.result.steps.every(s=>cleared(board.checks[s.id]));
 return <section ref={root} className="step-board" aria-label="逐步互动板书" data-board-id={board.id} data-step-id={step.id}>
  <div className="step-board-navigation"><button aria-label="回看上一步板书" disabled={index===0||checking||disabled} onClick={()=>navigate(index-1)}><ArrowLeft size={16}/>上一步</button><span>第 <strong>{index+1}</strong> / {total} 小步</span><button aria-label="重听这一步" disabled={checking||disabled} onClick={playStep}><RotateCcw size={15}/>重听这步</button></div>
  <div className="step-board-progress" role="progressbar" aria-label="本段板书阅读位置" aria-valuemin={0} aria-valuemax={total} aria-valuenow={index+1}><i style={{width:`${(index+1)/total*100}%`}}/></div>
  <div className="step-board-content"><span className="step-board-kicker">这一步，只弄懂一件事</span><h2>{step.title}</h2><div className="step-board-writing"><RichText text={step.board} annotations={focusStart<0?[]:[{id:step.id,index:0,start:focusStart,end:focusStart+step.focus.length}]}/></div>
   {step.visual_ids.map(id=>{const spec=source.visuals?.find(v=>v.id===id);return spec?<Suspense key={id} fallback={<p>正在准备本步的图…</p>}><TeachingDrawing spec={spec}/></Suspense>:null;})}
  </div>
  {!questionVisible?<div className="step-board-listening"><span><Play size={15}/>老师讲完这一小步后，会停下来问你</span><button disabled={checking} onClick={revealQuestion}>我想自己看，显示问题</button></div>:<section className="step-board-question" aria-label="本步理解检查"><div className="step-board-question-heading"><span><HelpCircle size={17}/>轮到你试一试</span><small>只检查这一小步</small></div><div className="step-board-question-text"><RichText text={choiceQuestion?.prompt||step.question}/></div>
   {choiceQuestion&&<fieldset className="step-board-choices" disabled={checking||disabled||check?.verdict==='correct'}><legend>{choiceQuestion.multiple?'多选 · 可以选择多个选项':'单选 · 点击一个选项'}</legend>{choiceQuestion.options.map(option=><label key={option.id} className={`step-board-choice${selected.includes(option.id)?' selected':''}`}><input type={choiceQuestion.multiple?'checkbox':'radio'} name={`board-choice-${step.id}`} value={option.id} checked={selected.includes(option.id)} onChange={()=>{const next=choiceQuestion.multiple?(selected.includes(option.id)?selected.filter(id=>id!==option.id):[...selected,option.id]):[option.id];setAnswer(choiceAnswer(choiceQuestion.options,next));}}/><span className="step-board-choice-letter">{option.id}</span><span className="step-board-choice-text"><RichText text={option.text}/></span></label>)}</fieldset>}
   {check&&<div className={`step-board-feedback ${check.verdict}`} role="status"><strong>{labels[check.verdict||'']||'本步反馈'}</strong><p><RichText text={check.feedback||''}/></p><small>{check.skipped?'稍后可回来练习。':'模型判断，不代表长期掌握。'}</small></div>}
   {check?.verdict!=='correct'&&<form onSubmit={formSubmit}>{!choiceQuestion&&<label className="step-board-answer-label">你的回答<textarea aria-label="本步问题的回答" rows={2} maxLength={1200} value={answer} onChange={e=>setAnswer(e.target.value)} disabled={checking||disabled} placeholder="简单说说你的想法，或者写出答案…"/></label>}<div className="step-board-answer-actions"><button className="step-board-submit" disabled={checking||disabled||!answer.trim()}>{checking?'正在检查…':check?'再试一次':'检查这一步'}</button><button type="button" disabled={checking||disabled} onClick={()=>onAsk(`我在这段授课的第${index+1}小步卡住了：${step.title}。板书是：${step.board}。问题是：${step.question}。请只补讲这一步，不推进到下一知识点。`)}>这一步没懂，问老师</button><button type="button" disabled={checking||disabled} onClick={()=>void submit(true)}>暂时跳过，稍后再练</button></div></form>}
   {checkError&&<p className="step-board-check-error" role="alert">{checkError}</p>}
   {cleared(check)&&index<total-1&&<button className="step-board-next" disabled={checking||disabled} onClick={()=>navigate(index+1)}>下一小步<ArrowRight size={16}/></button>}
   {index===total-1&&finished&&<div className="step-board-finished"><span><Check size={16}/>这段板书已走完</span>{board.result.steps.some(s=>board.checks[s.id]?.skipped)&&<p>有问题暂时跳过，建议先回看补练；跳过不会记录为答对。</p>}<button disabled={disabled} onClick={()=>{callbacks.current.onStop();onContinue();}}>我确认理解，继续课程<ArrowRight size={16}/></button></div>}
  </section>}
  <details className="step-board-narration"><summary>看本步讲稿与原文依据</summary><p><RichText text={step.narration}/></p><blockquote><RichText text={step.source_quote}/></blockquote></details>
 </section>;
}
