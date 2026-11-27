import {useEffect,useRef,useState} from 'react';
import type {TeachingMark} from './attentionModel';

type Credential={session_id:string;token:string};
export type AttentionRecord={id:string;status:string;error?:string;diagnostic?:{code:string};result:null|{steps:{step_id:string;marks:TeachingMark[]}[]}};

export function useBoardAttention(credential:Credential,boardId:string|undefined,detourId?:string,ready=true){
 const [record,setRecord]=useState<AttentionRecord|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[attempt,setAttempt]=useState(0);
 const usedAttempt=useRef(0);
 useEffect(()=>{
  setRecord(null);setError('');setLoading(false);if(!boardId||!ready)return;
  let alive=true,timer:ReturnType<typeof setTimeout>|undefined,polls=0,forceRetry=attempt>usedAttempt.current;usedAttempt.current=attempt;const controller=new AbortController();setLoading(true);
  const base=`/api/sessions/${credential.session_id}/boards/${boardId}/attention`;
  async function request(create:boolean,retry=false){
   const response=await fetch(base+(create?'':detourId?`?detour_id=${encodeURIComponent(detourId)}`:''),{method:create?'POST':'GET',headers:{Authorization:`Bearer ${credential.token}`,'Content-Type':'application/json'},...(create?{body:JSON.stringify({detour_id:detourId||null,retry})}:{}),signal:controller.signal});
   const data=await response.json();
   if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'教学标注暂不可用。'),{status:response.status});
   return data as AttentionRecord;
  }
  async function load(create=false){try{
   let value:AttentionRecord;
   try{value=await request(create);}catch(e){if(!create&&(e as {status?:number}).status===404)value=await request(true);else throw e;}
   if(forceRetry&&value.status==='failed'){forceRetry=false;value=await request(true,true);}forceRetry=false;
   if(!alive)return;setRecord(value);
   if(value.status==='pending'){
    if(polls++>=65){setLoading(false);setError('标注仍在处理中，可以继续阅读，稍后重新读取。');return;}
    timer=setTimeout(()=>void load(),1200);
   }else setLoading(false);
  }catch(e){if(alive&&(e as Error).name!=='AbortError'){setLoading(false);setError((e as Error).message);}}}
  void load();return()=>{alive=false;controller.abort();if(timer)clearTimeout(timer);};
 },[credential.session_id,credential.token,boardId,detourId,ready,attempt]);
 return {record,error,loading,retry:()=>setAttempt(n=>n+1)};
}

export function AttentionStatus({state,stepId}:{state:ReturnType<typeof useBoardAttention>;stepId?:string}){
 const {record,error,loading,retry}=state;
 const failed=!!error||record?.status==='failed';
 const marks=record?.result?.steps.find(s=>s.step_id===stepId)?.marks||[];
 return <div className={`attention-agent-status${failed?' failed':''}`} aria-label="教学标注状态"><span className="attention-agent-name">教学标注 Agent</span><span role={loading?'status':undefined}>{loading?'正在分析讲稿，正文可继续阅读':failed?'标注暂不可用，正文照常显示':record?.status==='completed'?(marks.length?`本块 ${marks.length} 处教学标记`:'本块未安排标记'):'尚未安排标记'}</span>{failed&&<><button onClick={retry}>{record?.status==='pending'?'重新读取':'重新分析'}</button><details><summary>原因</summary><p>{error||record?.error}{record?.diagnostic?.code?`（${record.diagnostic.code}）`:''}</p></details></>}</div>;
}
