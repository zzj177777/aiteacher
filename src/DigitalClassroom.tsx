import {lazy,Suspense,useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ArrowRight,BookOpen,Check,ChevronDown,Headphones,MessageCircle,Pause,Play,Plus,Send,Sparkles,Volume2,VolumeX} from 'lucide-react';
import DigitalAvatar,{defaultCharacter,type DigitalCharacter} from './DigitalAvatar';
import {DigitalNarrator,type VoiceStatus} from './digitalNarrator';
import RichText from './RichText';
import type {DrawingSpec} from './TeachingDrawing';
import StepBoard from './StepBoard';
import type {NarrationMessage} from './digitalNarrator';
import './digital-classroom.css';
const TeachingDrawing=lazy(()=>import('./TeachingDrawing'));

type Credential={session_id:string;token:string;title:string};
type Message={id:string;agent:string;text:string;kind?:string;status?:string;to_agent?:string;visuals?:DrawingSpec[];visual_error?:string;topic_choices?:{id:string;title:string;description:string}[]};
type Snapshot={revision:number;working:boolean;completed:boolean;active_agent:string;messages:Message[];profile:{goal:string};plan:{id:string;goal:string;nodes:{id:string;title:string;status:string;delivered:boolean}[]}|null;pending_question:{question:string}|null};
type Result={session_id?:string;token?:string;snapshot:Snapshot};
const sessionKey='aiteacher.digital.sessions.v1',activeKey='aiteacher.digital.active.v1';
const names:Record<string,string>={planner:'教学安排',lecturer:'老师讲解',assessment:'随堂练习',student:'你',drawing:'教学绘图'};
function narratable(m:Message){return ['planner','lecturer','assessment'].includes(m.agent)&&m.status==='ai'&&m.kind!=='handoff';}
async function request(path:string,credential:Credential|null,body?:unknown){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(credential?{Authorization:`Bearer ${credential.token}`}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const data=await response.json();if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'请求没有完成，请重试。'),{status:response.status});return data as Result;
}

export default function DigitalClassroom(){
 const [credential,setCredential]=useState<Credential|null>(null),[snapshot,setSnapshot]=useState<Snapshot|null>(null),[history,setHistory]=useState<Credential[]>([]);
 const [input,setInput]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
 const [voice,setVoice]=useState(true),[voiceStatus,setVoiceStatus]=useState<VoiceStatus>('idle'),[voiceError,setVoiceError]=useState(''),[speakingId,setSpeakingId]=useState('');
 const [showHandoffs,setShowHandoffs]=useState(false);
 const [transcript,setTranscript]=useState(false),[showComposer,setShowComposer]=useState(false);
 const boardScroll=useRef<HTMLDivElement>(null),originalDetails=useRef<HTMLDetailsElement>(null);
 const [characters,setCharacters]=useState<DigitalCharacter[]>([]),[characterId,setCharacterId]=useState('miku'),[characterError,setCharacterError]=useState('');
 const character=characters.find(c=>c.id===characterId&&c.available)||defaultCharacter;
 const restoredMessages=useRef(new Set<string>());
 const mouth=useRef(0),narrator=useRef<DigitalNarrator|null>(null),active=useRef(''),revision=useRef(-1),seen=useRef(new Set<string>()),locked=useRef(false),voiceEnabled=useRef(true),tail=useRef<HTMLDivElement>(null);
 const current=snapshot?.plan?.nodes.find(n=>n.status==='current');
 const visible=snapshot?.messages.filter(m=>m.kind!=='handoff'&&m.status!=='pending'&&m.status!=='cancelled')||[];
 const handoffs=snapshot?.messages.filter(m=>m.kind==='handoff')||[];
 const latestTeacher=[...visible].reverse().find(m=>m.agent!=='student'&&(m.status==='ai'||m.status==='failed'||m.status==='local'&&m.kind!=='receipt'));
 const boardSource=latestTeacher?.agent==='lecturer'&&latestTeacher.status==='ai'?latestTeacher:undefined;
 const done=snapshot?.plan?.nodes.filter(n=>n.status==='completed').length||0;

 function voiceController(){
  if(!narrator.current)narrator.current=new DigitalNarrator(mouth,(status,message)=>{setVoiceStatus(status);if(message)setSpeakingId(message.id);else if(status==='idle')setSpeakingId('');},setVoiceError);
  return narrator.current;
 }
 function stop(){narrator.current?.stop();}
 function apply(next:Snapshot,sid:string,restoring=false){
  if(active.current!==sid||next.revision<revision.current)return;
  revision.current=next.revision;if(restoring)restoredMessages.current=new Set(next.messages.map(m=>m.id));setSnapshot(next);
  for(const m of next.messages){
   if(!narratable(m)||seen.current.has(m.id))continue;seen.current.add(m.id);
   if(!restoring&&voiceEnabled.current&&m.agent!=='lecturer'){const cred=credentialRef.current;if(cred?.session_id===sid)voiceController().enqueue(cred,m);}
  }
 }
 const credentialRef=useRef<Credential|null>(null);
 function selectCredential(value:Credential|null){credentialRef.current=value;setCredential(value);active.current=value?.session_id||'';revision.current=-1;seen.current=new Set();restoredMessages.current=new Set();}
 function save(items:Credential[]){try{localStorage.setItem(sessionKey,JSON.stringify(items));setHistory(items);}catch{setError('浏览器无法保存恢复入口，请保持本页打开。');}}
 async function restore(cred:Credential){
  stop();selectCredential(cred);setSnapshot(null);setError('');setVoiceError('');setLoading(true);
  try{const result=await request(`/api/sessions/${cred.session_id}`,cred);apply(result.snapshot,cred.session_id,true);}
  catch(e){if(active.current===cred.session_id)setError((e as Error).message);}
  finally{if(active.current===cred.session_id)setLoading(false);}
 }
 useEffect(()=>{
  let items:Credential[]=[];
  try{const parsed=JSON.parse(localStorage.getItem(sessionKey)||'[]');if(Array.isArray(parsed))items=parsed.filter(c=>c&&typeof c.session_id==='string'&&typeof c.token==='string'&&typeof c.title==='string');setHistory(items);const saved=localStorage.getItem(activeKey);const prior=items.find(c=>c.session_id===saved);if(prior){void restore(prior);return;}}
  catch{setError('恢复入口暂时无法读取，可以开始一节新课。');}
  setLoading(false);
 },[]);
 useEffect(()=>()=>{narrator.current?.dispose();narrator.current=null;},[]);
 useEffect(()=>{
  let alive=true;
  fetch('/api/digital-human/characters').then(async response=>{if(!response.ok)throw new Error();return response.json();}).then(data=>{
   if(!alive)return;const options=data.characters as DigitalCharacter[];setCharacters(options);
   let saved='';try{saved=localStorage.getItem('aiteacher.digital.character.v1')||'';}catch{/* Optional preference. */}
   setCharacterId(options.some(c=>c.id===saved&&c.available)?saved:options.find(c=>c.id==='miku'&&c.available)?.id||options.find(c=>c.available)?.id||'mao');
  }).catch(()=>{if(alive)setCharacterError('形象列表暂未加载，可继续上课。');});
  return()=>{alive=false;};
 },[]);
 function chooseCharacter(id:string){setCharacterId(id);try{localStorage.setItem('aiteacher.digital.character.v1',id);}catch{/* The current selection still works. */}}
 useEffect(()=>{
  if(!credential||!snapshot?.working)return;const sid=credential.session_id;
  const timer=setInterval(async()=>{if(locked.current)return;try{const result=await request(`/api/sessions/${sid}`,credential);apply(result.snapshot,sid);}catch{if(active.current===sid)setError('正在重新连接课堂，已保存的内容不会丢失。');}},1200);
  return()=>clearInterval(timer);
 },[credential?.session_id,snapshot?.working]);
 useEffect(()=>{if(!boardSource)tail.current?.scrollIntoView({behavior:'smooth',block:'end'});},[snapshot?.messages.length]);
 useEffect(()=>{if(boardSource&&boardScroll.current)boardScroll.current.scrollTop=0;setTranscript(false);setShowComposer(false);},[boardSource?.id]);
 function fresh(){stop();selectCredential(null);setSnapshot(null);setInput('');setError('');setVoiceError('');try{localStorage.removeItem(activeKey);}catch{/* Optional navigation. */}}
 async function send(type:string,text?:string,recipient='auto'){
  if(locked.current||loading)return;locked.current=true;setBusy(true);setError('');setVoiceError('');stop();if(voiceEnabled.current)voiceController().unlock();
  try{
   let cred=credentialRef.current,state=snapshot;
   if(!cred){
    const result=await request('/api/sessions',null,{mode:'chat',title:(text||input).slice(0,100)||'数字人小课'});
    cred={session_id:result.session_id!,token:result.token!,title:(text||input).slice(0,32)||'数字人小课'};selectCredential(cred);state=result.snapshot;apply(state,cred.session_id,true);save([cred,...history]);
   }
   if(!state)throw new Error('请先重新读取课堂，或开始新课。');
   try{localStorage.setItem(activeKey,cred.session_id);}catch{/* Existing session remains usable. */}
   const result=await request(`/api/sessions/${cred.session_id}/events`,cred,{expected_revision:state.revision,idempotency_key:crypto.randomUUID(),type,payload:type==='chat_message'?{text:text??input,recipient}:type==='chat_choose_topic'?{choice_id:text}:{}});
   apply(result.snapshot,cred.session_id);if(type==='chat_message')setInput('');
  }catch(e){setError((e as Error).message);if((e as {status?:number}).status===409&&credentialRef.current){const cred=credentialRef.current;try{apply((await request(`/api/sessions/${cred.session_id}`,cred)).snapshot,cred.session_id);}catch{/* Original error is actionable. */}}}
  finally{locked.current=false;setBusy(false);}
 }
 function submit(event:FormEvent){event.preventDefault();if(input.trim())void send('chat_message');}
 function replay(message?:Message){const m=message||[...visible].reverse().find(narratable);if(!m||!credential)return;stop();setVoiceError('');voiceController().unlock();voiceController().enqueue(credential,m);}
 function toggleVoice(){const enabled=!voice;setVoice(enabled);voiceEnabled.current=enabled;setVoiceError('');if(!enabled)stop();else voiceController().unlock();}
 function renderMessage(m:Message){return <article key={m.id} className={`digital-message ${m.agent} ${speakingId===m.id?'is-narrating':''} ${m.status==='failed'?'failed':''}`} data-message-id={m.id}><div className="digital-message-label"><span>{names[m.agent]||m.agent}</span>{narratable(m)&&<button aria-label={`重听${names[m.agent]||'老师'}内容`} onClick={()=>replay(m)}><Volume2 size={13}/>{speakingId===m.id?'讲解中':'重听'}</button>}</div><div className="digital-message-body"><RichText text={m.text}/></div>{m.visual_error&&<p>{m.visual_error}</p>}{m.visuals?.map(v=><Suspense key={v.id} fallback={<p>正在准备教学图…</p>}><TeachingDrawing spec={v}/></Suspense>)}{m.topic_choices&&<div className="digital-topic-choices">{m.topic_choices.map(choice=><button key={choice.id} disabled={busy||snapshot?.working||snapshot?.completed||!!snapshot?.plan} onClick={()=>void send('chat_choose_topic',choice.id)}><strong>{choice.title}</strong><small>{choice.description}</small></button>)}</div>}</article>;}
 function speakBoard(message:NarrationMessage){if(!credentialRef.current)return;stop();setVoiceError('');voiceController().unlock();voiceController().enqueue(credentialRef.current,message);}
 function openOriginal(){setTranscript(true);setTimeout(()=>originalDetails.current?.scrollIntoView({behavior:'smooth',block:'start'}),0);}
 const teaching=voiceStatus==='speaking',speaking=voiceStatus==='speaking'||voiceStatus==='loading';
 return <main className={`digital-classroom${boardSource?' has-step-board':''}`}>
  <header className="digital-header"><a href="/" className="digital-back"><ArrowLeft size={17}/>文字课堂</a><div className="digital-brand"><span><Sparkles size={20}/></span><div><strong>数字人课堂</strong><small>有板书，也有陪你讲明白的老师</small></div></div><div className="digital-header-actions">{history.length>0&&<label className="digital-history"><BookOpen size={15}/><select aria-label="恢复数字人课程" value={credential?.session_id||''} disabled={busy||loading} onChange={e=>{const cred=history.find(c=>c.session_id===e.target.value);if(cred)void restore(cred);}}><option value="" disabled>之前的小课</option>{history.map(c=><option key={c.session_id} value={c.session_id}>{c.title}</option>)}</select><ChevronDown size={13}/></label>}<button disabled={busy||loading} onClick={fresh}><Plus size={16}/>新课</button></div></header>
  <div className="digital-layout">
   <aside className="digital-teacher-panel" aria-label="数字人老师"><div className="digital-room-tag"><span/> 一对一 · 专属教室</div><DigitalAvatar mouth={mouth} speaking={teaching} character={character}/><section className="digital-character-picker" aria-label="角色形象选择"><label htmlFor="digital-character">老师形象<select id="digital-character" aria-label="老师形象" value={character.id} onChange={e=>chooseCharacter(e.target.value)}>{characters.length?characters.map(c=><option key={c.id} value={c.id} disabled={!c.available}>{c.name} · {c.mode==='portrait'?'静态形象':'动态形象'}{!c.available?'（未安装）':''}</option>):<option value="mao">Mao</option>}</select></label><small>{character.note||'可动形象 · 语音驱动口型'}</small><small>配音：晓晓 · 不是角色原声</small><details><summary>素材来源与使用说明</summary><p>{character.credit}</p><p>{character.id==='miku'?'仅作本地技术体验，商业使用需另行确认角色授权。':'This content uses sample data owned and copyrighted by Live2D Inc. The sample data are utilized in accordance with terms and conditions set by Live2D Inc. This content itself is created at the author’s sole discretion.'}</p><a href={character.source_url} target="_blank" rel="noopener noreferrer">官方素材说明 ↗</a></details>{characterError&&<small role="alert">{characterError}</small>}</section><div className="digital-voice-panel"><div><Headphones size={18}/><span>{voiceStatus==='loading'?'正在准备声音…':teaching?'老师正在讲解':voice?'语音讲解已开启':'已切换为安静学习'}</span><button onClick={toggleVoice} aria-label={voice?'关闭自动语音':'开启自动语音'} aria-pressed={voice}>{voice?<Volume2 size={18}/>:<VolumeX size={18}/>}</button></div><div className="digital-voice-actions"><button disabled={!speaking} onClick={stop}><Pause size={14}/>暂停讲解</button>{!boardSource&&<button disabled={!visible.some(narratable)} onClick={()=>replay()}><Play size={14}/>重听刚才</button>}</div><p>随时发消息打断老师。听完以后，由你决定是否继续。</p></div>{voiceError&&<div className="digital-voice-error" role="alert">{voiceError}{!boardSource&&<button onClick={()=>replay()}>重试播放</button>}{boardSource&&<span>请在板书右上角点击“重听这步”。</span>}</div>}</aside>
   <section className="digital-board-panel" aria-label="课堂板书">
    <div className="digital-board-heading"><div><span className="digital-eyebrow">TODAY'S LESSON</span><h1>{snapshot?.profile.goal||'今天，想弄懂什么？'}</h1></div><span className={`digital-state ${snapshot?.working?'working':''}`}>{snapshot?.working?'老师正在准备':snapshot?.completed?'本课已保存':current?'正在学习':'等你开口'}</span></div>
    {snapshot?.plan&&<details className="digital-route"><summary><span><BookOpen size={16}/>本课路线</span><small>{done} / {snapshot.plan.nodes.length} 已确认理解</small></summary><ol>{snapshot.plan.nodes.map((node,i)=><li key={node.id} className={node.status} aria-current={node.status==='current'?'step':undefined}><span>{node.status==='completed'?<Check size={12}/>:i+1}</span><div><RichText text={node.title}/></div></li>)}</ol><p>由你的确认记录进度；听完讲解不代表已经掌握。</p></details>}
    {error&&<div className="digital-error" role="alert">{error}{credential&&!snapshot&&<button onClick={()=>void restore(credential)}>重新读取课堂</button>}</div>}
    <div className="digital-board-scroll" ref={boardScroll}>
     {loading?<p className="digital-empty" role="status">正在打开课堂…</p>:!snapshot?<div className="digital-welcome"><span className="digital-welcome-icon"><MessageCircle size={29}/></span><h2>先从一个小问题开始。</h2><p>告诉老师想学什么、哪里没听懂，<br/>我们先安排一节小课，再一步一步讲。</p><div>{['我是初二学生，想弄懂一次函数','我是初学者，想学分数的意义'].map(text=><button key={text} disabled={busy} onClick={()=>void send('chat_message',text)}>{text}<ArrowRight size={15}/></button>)}</div><small>不用填长表单，边学边了解你。</small></div>:<>
      {boardSource&&credential?<StepBoard key={`${credential.session_id}:${boardSource.id}`} credential={credential} source={boardSource} disabled={busy||snapshot.working||snapshot.completed} voiceEnabled={voice} autoPlay={!restoredMessages.current.has(boardSource.id)} onSpeak={speakBoard} onStop={stop} onAsk={text=>void send('chat_message',text,'lecturer')} onContinue={()=>void send('chat_continue')} onOriginal={openOriginal}/>:latestTeacher?renderMessage(latestTeacher):null}
      <details className="digital-transcript" ref={originalDetails} open={transcript} onToggle={e=>setTranscript(e.currentTarget.open)}><summary>查看完整对话与授课原文 · {visible.length} 条</summary>{transcript&&visible.map(renderMessage)}</details>
      {snapshot.working&&<div className="digital-thinking" role="status"><span/><span/><span/> {names[snapshot.active_agent]||'老师'}正在准备内容，你可以继续发消息。</div>}
      {handoffs.length>0&&<details className="digital-handoffs" open={showHandoffs} onToggle={e=>setShowHandoffs(e.currentTarget.open)}><summary>查看教学 Agent 配合 · {handoffs.length}</summary>{handoffs.map(m=><p key={m.id}><strong>{names[m.agent]||m.agent}{m.to_agent?` → ${names[m.to_agent]||m.to_agent}`:''}</strong><span>{m.text}</span></p>)}</details>}
      <div ref={tail}/>
     </>}
    </div>
    <div className={`digital-composer${boardSource&&!showComposer?' compact':''}`}>{boardSource&&<button className="digital-ask-toggle" aria-expanded={showComposer} onClick={()=>setShowComposer(v=>!v)}><MessageCircle size={14}/>{showComposer?'收起提问输入框':'有疑问？随时向老师提问'}</button>}{boardSource&&<p className="digital-check-hint">本步作答请填板书里的答案框；下方用于随时向老师提问。</p>}<div className="digital-lesson-actions">{snapshot?.plan&&!snapshot.plan.nodes.some(n=>n.delivered)&&<button disabled={busy||snapshot.working||snapshot.completed} onClick={()=>void send('chat_message','按这个计划开始，从第一个节点讲起。')}><Play size={14}/>按计划开始</button>}<button disabled={!snapshot||busy||snapshot.working||snapshot.completed||!snapshot.plan} onClick={()=>void send('chat_example')}><Sparkles size={14}/>举个例子</button>{!boardSource&&<button className="digital-next" disabled={!current||busy||snapshot?.working||snapshot?.completed||!!snapshot?.pending_question} onClick={()=>void send('chat_continue')}>我明白了，继续<ArrowRight size={15}/></button>}</div>{snapshot?.pending_question&&<p className="digital-answer-hint">轮到你啦，在下方作答。想换个方向也可以直接告诉老师。</p>}<form onSubmit={submit}><textarea aria-label="给数字人老师发消息" rows={2} maxLength={4000} value={input} disabled={loading||snapshot?.completed} onChange={e=>setInput(e.target.value)} placeholder={snapshot?.completed?'这节课已保存，可以新建一节课继续。':snapshot?'哪里不懂就问，也可以回答老师的问题…':'想学什么？也可以告诉老师你是几年级。'} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(input.trim())void send('chat_message');}}}/><button type="submit" aria-label="发送给数字人老师" disabled={busy||loading||!input.trim()||snapshot?.completed}><Send size={18}/></button></form><div className="digital-composer-footer"><span>{snapshot?.working?'发送消息会打断并替代当前生成':'Enter 发送 · Shift + Enter 换行'}</span>{snapshot&&!snapshot.completed&&<button disabled={busy} onClick={()=>void send('chat_end')}>结束并保存</button>}{snapshot?.completed&&<button onClick={fresh}>开始新课 →</button>}</div></div>
   </section>
  </div>
 </main>;
}
