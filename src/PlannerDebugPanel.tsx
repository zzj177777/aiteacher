import {useEffect,useRef,useState} from 'react';
import {Bug,Copy,Maximize2,RefreshCw,X} from 'lucide-react';
import './planner-debug.css';

type Credential={session_id:string;token:string};
type Trace={id:string;job_id:string;at:string;status:string;duration_ms:number;request:Record<string,unknown>|null;response:unknown;error:{code:string;stage:string;message:string}|null};
type Traces={calls:Trace[];limit:number};
const json=(value:unknown)=>JSON.stringify(value,null,2);
function readable(value:unknown){if(typeof value!=='string')return json(value);try{return json(JSON.parse(value));}catch{return value;}}

function DebugPayload({call,view}:{call:Trace;view:'request'|'response'}){
 if(view==='request'){
  if(!call.request)return <p className="debug-empty">{call.status==='failed'?'请求尚未发出就已失败。':'正在准备模型请求…'}</p>;
  const messages=call.request.messages as {role:string;content:unknown}[]|undefined;
  const {messages:_,...parameters}=call.request;
  return <div className="debug-payload">{messages?.map((message,index)=><details key={index} open={message.role==='user'}><summary>{message.role==='system'?'系统提示词':message.role==='user'?'发给模型的问题与上下文':message.role}<span>{message.role}</span></summary><pre>{readable(message.content)}</pre></details>)}<details><summary>工具定义与调用参数</summary><pre>{json(parameters)}</pre></details><details><summary>完整请求 JSON</summary><pre>{json(call.request)}</pre></details></div>;
 }
 if(call.response==null)return <p className="debug-empty">{call.status==='failed'?'没有收到可展示的有效 JSON 回复；原因见上方。':'等待大模型返回…'}</p>;
 const response=call.response as {choices?:{finish_reason?:string;message?:{content?:string;tool_calls?:{id?:string;function?:{name?:string;arguments?:unknown}}[]}}[]};
 const choices=Array.isArray(response?.choices)?response.choices.filter(choice=>choice&&typeof choice==='object').map(choice=>({...choice,message:choice.message&&typeof choice.message==='object'?{...choice.message,content:typeof choice.message.content==='string'?choice.message.content:'',tool_calls:Array.isArray(choice.message.tool_calls)?choice.message.tool_calls.filter(call=>call&&typeof call==='object'&&call.function&&typeof call.function==='object'):[]}:undefined})):[];
 const hasMessage=choices.some(choice=>choice.message?.content||choice.message?.tool_calls?.length);
 return <div className="debug-payload">{choices.map((choice,index)=><div key={index}>{choice.message?.content&&<section className="debug-answer"><strong>模型直接回复 · content</strong><pre>{choice.message.content}</pre></section>}{choice.message?.tool_calls?.map((call,i)=><section className="debug-answer" key={call.id||i}><strong>工具调用 · {typeof call.function?.name==='string'?call.function.name:'未返回名称'}</strong><small>arguments 原文，未经过工具解析或改写</small><pre>{typeof call.function?.arguments==='string'?call.function.arguments:json(call.function?.arguments)}</pre></section>)}</div>)}<details open={!hasMessage}><summary>原始响应 JSON</summary><pre>{json(call.response)}</pre></details></div>;
}

export default function PlannerDebugPanel({credential,revision,working}:{credential:Credential;revision:number;working:boolean}){
 const [data,setData]=useState<Traces|null>(null),[error,setError]=useState(''),[selected,setSelected]=useState('');
 const [view,setView]=useState<'request'|'response'>('request'),[refresh,setRefresh]=useState(0),[copied,setCopied]=useState('');
 const dialog=useRef<HTMLDialogElement>(null);const opener=useRef<HTMLButtonElement>(null);const copyTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
 useEffect(()=>{setData(null);setSelected('');setView('request');setCopied('');dialog.current?.close();return()=>{if(copyTimer.current)clearTimeout(copyTimer.current);};},[credential.session_id]);
 useEffect(()=>{
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
  async function update(){
   try{const response=await fetch(`/api/sessions/${credential.session_id}/debug/planner`,{headers:{Authorization:`Bearer ${credential.token}`},signal:controller.signal});if(!response.ok)throw new Error('暂时无法读取调试记录');const result=await response.json() as Traces;if(!controller.signal.aborted){setData(result);setError('');}}
   catch{if(!controller.signal.aborted)setError('调试记录暂时无法读取，可点击刷新重试。');}
   finally{if(working&&!controller.signal.aborted)timer=setTimeout(update,1200);}
  }
  void update();return()=>{controller.abort();if(timer)clearTimeout(timer);};
 },[credential.session_id,credential.token,revision,working,refresh]);
 const call=data?.calls.find(item=>item.id===selected)||data?.calls[0];
 const status=call?({preparing:'准备请求',pending:'等待回复',completed:'调用完成',failed:'调用失败'}[call.status]||call.status):'';
 async function copy(){if(!call)return;try{await navigator.clipboard.writeText(json(view==='request'?call.request:call.response));setCopied('已复制');}catch{setCopied('复制失败，请在放大窗口中手动选择');}if(copyTimer.current)clearTimeout(copyTimer.current);copyTimer.current=setTimeout(()=>setCopied(''),2500);}
 const content=<>
  <div className="debug-tools"><button type="button" onClick={()=>setRefresh(n=>n+1)} aria-label="刷新安排调试"><RefreshCw size={13}/>刷新</button><button type="button" disabled={!call||(view==='request'?!call.request:call.response==null)} onClick={copy}><Copy size={13}/>复制{view==='request'?'请求':'回复'}</button></div>
  {copied&&<small role="status" className="debug-copy-status">{copied}</small>}
  {error&&<p className="debug-fetch-error" role="alert">{error}</p>}
  {!data&&!error?<p role="status">正在读取调试记录…</p>:!call?<p className="debug-empty">还没有记录。下一次调用教学安排 Agent 时，会在这里显示实际请求与原始回复。历史调用无法补录。</p>:<>
   <label className="debug-call-selector">查看调用<select aria-label="选择安排 Agent 调用" value={selected&&data?.calls.some(c=>c.id===selected)?selected:''} onChange={e=>{setSelected(e.target.value);setCopied('');}}><option value="">自动跟随最新调用</option>{data?.calls.map((c,i)=><option key={c.id} value={c.id}>{i===0?'最新 · ':''}{new Date(c.at).toLocaleTimeString('zh-CN')} · {c.status==='failed'?'失败':c.status==='completed'?'完成':'进行中'} · {c.id.slice(0,6)}</option>)}</select></label>
   <div className="debug-call-meta"><span className={`debug-state ${call.status}`}>{status}</span><span>{new Date(call.at).toLocaleTimeString('zh-CN')}{call.status==='completed'||call.status==='failed'?` · ${(call.duration_ms/1000).toFixed(2)} 秒`:''}</span></div>
   <small className="debug-job">回合 {call.job_id?.slice(0,8)||'未关联'} · 调用 {call.id.slice(0,8)}</small>
   {call.error&&<div className="debug-call-error"><strong>{call.error.code}</strong><p>{call.error.message}</p></div>}
   <div className="debug-tabs" role="group" aria-label="安排调试内容"><button type="button" aria-pressed={view==='request'} onClick={()=>{setView('request');setCopied('');}}>发送给模型</button><button type="button" aria-pressed={view==='response'} onClick={()=>{setView('response');setCopied('');}}>模型原始回复</button></div>
   <DebugPayload call={call} view={view}/>
  </>}
  <p className="debug-footnote">保留本会话最近 {data?.limit||30} 次安排调用；失败和被替代的调用也会记录。密钥、私有评分标准和内部推理字段已隐藏。调用完成不代表整轮教学执行成功。</p>
 </>;
 return <details className="planner-debug" open><summary><Bug size={15}/>安排 Agent 调试<span>{data?.calls.length||0}</span></summary><div className="debug-panel-heading"><span>实际请求 / 原始返回</span><button type="button" ref={opener} onClick={()=>dialog.current?.showModal()} aria-label="放大安排调试"><Maximize2 size={13}/>放大</button></div><div className="debug-inline-content">{content}</div><dialog ref={dialog} className="planner-debug-dialog" aria-labelledby="planner-debug-title" onClose={()=>opener.current?.focus()}><div className="debug-dialog-heading"><div><span>开发调试</span><h2 id="planner-debug-title">教学安排 Agent · 请求与回复</h2></div><button type="button" onClick={()=>dialog.current?.close()} aria-label="关闭调试大窗"><X size={20}/></button></div>{content}</dialog></details>;
}
