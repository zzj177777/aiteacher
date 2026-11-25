import React,{useEffect,useState} from 'react';
type Call={id:string;agent?:string;model:string;status:string;prompt_tokens?:number;completion_tokens?:number;duration_ms:number;estimated_cost:number|null;currency:string;error_code?:string};
type Usage={call_count:number;failed_calls:number;prompt_tokens:number;completion_tokens:number;usage_unknown_calls:number;unpriced_calls:number;estimated_costs:Record<string,number>;duration_ms:number;recent_calls:Call[]};
const agentNames:Record<string,string>={board_designer:'板书编排',board_check:'本步理解检查',planner:'教学安排 Agent',lecturer:'授课 Agent',assessment:'测评 Agent',plain_language:'通俗讲解 Agent',explainer:'选中解释助手',course_guard:'课程范围检查'};
export default function UsagePanel({credential,revision}:{credential:{session_id:string;token:string};revision:number}){
 const [usage,setUsage]=useState<Usage|null>(null);const [error,setError]=useState('');const [refresh,setRefresh]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();setError('');setUsage(null);
  fetch(`/api/sessions/${credential.session_id}/usage`,{headers:{Authorization:`Bearer ${credential.token}`},signal:controller.signal})
   .then(async r=>{if(!r.ok)throw new Error();return r.json() as Promise<Usage>;})
   .then(data=>{if(!controller.signal.aborted)setUsage(data);}).catch(()=>{if(!controller.signal.aborted)setError('成本记录暂时无法读取');});
  return()=>controller.abort();
 },[credential.session_id,credential.token,revision,refresh]);
 const money=(amount:number)=>amount.toFixed(6);
 return <details onToggle={e=>{if(e.currentTarget.open)setRefresh(n=>n+1);}}><summary>模型用量与估算成本{usage?` · ${usage.call_count} 次调用`:''}</summary>
  <button type="button" onClick={()=>setRefresh(n=>n+1)}>刷新用量</button>
  {error?<p role="alert">{error}</p>:!usage?<p>正在读取…</p>:<>
   <p>输入 {usage.prompt_tokens} / 输出 {usage.completion_tokens} tokens；调用失败 {usage.failed_calls} 次；累计调用耗时 {(usage.duration_ms/1000).toFixed(1)} 秒。</p>
   <p>{Object.entries(usage.estimated_costs).map(([currency,cost])=>`${currency} ${money(cost)}`).join('；')||'费用暂不可估算'}。未计价 {usage.unpriced_calls} 次；缺少完整用量 {usage.usage_unknown_calls} 次。</p>
   <small>按配置单价估算，非供应商账单；未知用量不按零费用计算。仅统计启用记录后的调用，失败或被替代的请求也可能产生费用。</small>
   <ol>{usage.recent_calls.map(c=><li key={c.id}>{agentNames[c.agent||'']||c.agent||'未关联角色'} · {c.model} · {c.status==='failed'?`失败 ${c.error_code||''}`:'模型调用完成'}<br/>输入 {c.prompt_tokens??'未知'} / 输出 {c.completion_tokens??'未知'} · {(c.duration_ms/1000).toFixed(2)} 秒 · {c.estimated_cost===null?'费用未知':`${c.currency} ${money(c.estimated_cost)}`}</li>)}</ol>
  </>}
 </details>;
}
