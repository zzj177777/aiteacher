import {useEffect,useState,type FormEvent} from 'react';
import {ArrowRight,Check,Clock3,Layers3,LoaderCircle,Route,Sparkles} from 'lucide-react';
import type {CourseContext} from './ChatApp';
import RichText from './RichText';

export type RoadmapSection={id:string;position:number;title:string;objective:string;outcomes:string[];prerequisites:{id:string;title:string}[];estimated_minutes:number;status:'not_started'|'learning'|'confirmed';session:{id:string;confirmed_nodes:number;total_nodes:number;completed:boolean}|null};
type Inputs={goal:string;background:string;scope:string;lesson_minutes:number;section_limit:number};
export type CourseRoadmapData={revision:number;status:string;plan:{goal:string;assumptions:string[]}|null;inputs:Inputs|null;error:string|null;sections:RoadmapSection[];confirmed_sections:number;next_section_id:string|null};
type Costs={call_count:number;prompt_tokens:number;completion_tokens:number;estimated_costs:Record<string,number>;unpriced_calls:number};

async function request(path:string,token:string,body?:unknown){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'课程规划暂未完成，请重试。');return data;
}

export default function CourseRoadmap({course,token,initial,onOpen,opening,onChange}:{course:CourseContext;token:string;initial:CourseRoadmapData;onOpen:(section:RoadmapSection)=>void;opening:string;onChange:(courseId:string,data:CourseRoadmapData)=>void}){
 const [roadmap,setRoadmap]=useState(initial),[formOpen,setFormOpen]=useState(!initial.plan),[busy,setBusy]=useState(false),[error,setError]=useState(''),[costs,setCosts]=useState<Costs|null>(null);
 const draftKey=`aiteacher.curriculum.draft.${course.id}`;
 const [inputs,setInputs]=useState<Inputs>(()=>{let draft=null;try{draft=JSON.parse(sessionStorage.getItem(draftKey)||'null');}catch{/* Optional draft. */}return {...{goal:course.description||course.title,background:'',scope:'',lesson_minutes:25,section_limit:12},...initial.inputs,...draft};});
 useEffect(()=>{try{sessionStorage.setItem(draftKey,JSON.stringify(inputs));}catch{/* The form works without a draft. */}},[inputs,draftKey]);
 useEffect(()=>{setRoadmap(initial);},[initial]);
 useEffect(()=>{onChange(course.id,roadmap);},[course.id,roadmap,onChange]);
 useEffect(()=>{
  if(roadmap.status!=='planning')return;let alive=true;let timer:ReturnType<typeof setTimeout>;
  async function poll(){try{const data=await request(`/api/courses/${course.id}`,token);if(!alive)return;setRoadmap(data.curriculum);setError('');if(data.curriculum.status==='ready')setFormOpen(false);if(data.curriculum.status==='planning')timer=setTimeout(poll,1200);}catch{if(alive){setError('暂时无法读取规划进度，正在重试。');timer=setTimeout(poll,2000);}}}
  timer=setTimeout(poll,700);return()=>{alive=false;clearTimeout(timer);};
 },[roadmap.status,course.id,token]);
 useEffect(()=>{let alive=true;request(`/api/courses/${course.id}/usage`,token).then(data=>{if(alive)setCosts(data);}).catch(()=>{});return()=>{alive=false;};},[course.id,token,roadmap.revision]);
 const planning=busy||roadmap.status==='planning',started=roadmap.sections.some(section=>section.session),next=roadmap.sections.find(section=>section.id===roadmap.next_section_id);
 async function submit(event:FormEvent){event.preventDefault();if(planning)return;setBusy(true);setError('');try{const result=await request(`/api/courses/${course.id}/curriculum`,token,{...inputs,goal:inputs.goal.trim(),expected_revision:roadmap.revision});setRoadmap(result.curriculum);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <section className="course-roadmap" aria-label="大课程学习路线">
  <div className="roadmap-heading"><div><span className="course-eyebrow"><Route size={15}/>大课定方向，小课一步步学</span><h2>课程学习路线</h2><p>{roadmap.plan?'按推荐顺序学习，也可以回到任意小节复习。':'先规划整门课的小节，再在每一节里安排具体教学节点。'}</p></div>{roadmap.plan&&!planning&&<button className="course-secondary" disabled={started} title={started?'已有学习记录，保留原路线；可在下方添加补充小课。':'开始学习前可以调整目标，重新规划。'} onClick={()=>setFormOpen(value=>!value)}>调整规划</button>}</div>
  {(error||roadmap.error)&&<p className="course-error" role="alert">{error||roadmap.error}</p>}
  {planning&&<div className="roadmap-planning" role="status"><LoaderCircle size={20}/><div><strong>正在划分小节，安排先后顺序…</strong><p>规划会保存在这门课程里，可以稍后回来查看。</p></div></div>}
  {formOpen&&!planning&&<form className="roadmap-form" onSubmit={submit}>
   <div className="roadmap-form-intro"><Sparkles size={19}/><div><strong>先说清楚，这门课想走到哪里</strong><p>课程名称确定学科范围，你的目标决定这次路线的边界。</p></div></div>
   <label>大课程学习目标<textarea value={inputs.goal} maxLength={500} rows={2} required placeholder="例如：学会初二上学期的数学，能独立完成基础题。" onChange={e=>setInputs(old=>({...old,goal:e.target.value}))}/></label>
   <div className="roadmap-field-grid"><label>学习范围或教材 <small>选填</small><input value={inputs.scope} maxLength={500} placeholder="例如：初二上学期；教材版本或章节" onChange={e=>setInputs(old=>({...old,scope:e.target.value}))}/></label><label>目前基础 <small>选填</small><input value={inputs.background} maxLength={500} placeholder="例如：分数运算不熟，函数还没学过" onChange={e=>setInputs(old=>({...old,background:e.target.value}))}/></label></div>
   <div className="roadmap-form-footer"><label>每节约<select value={inputs.lesson_minutes} onChange={e=>setInputs(old=>({...old,lesson_minutes:Number(e.target.value)}))}>{[15,25,40,60].map(value=><option value={value} key={value}>{value} 分钟</option>)}</select></label><label>最多规划<select value={inputs.section_limit} onChange={e=>setInputs(old=>({...old,section_limit:Number(e.target.value)}))}>{[8,12,20,24].map(value=><option value={value} key={value}>{value} 节</option>)}</select></label><button className="course-primary" disabled={started||!inputs.goal.trim()} type="submit"><Sparkles size={16}/>{roadmap.plan?'重新规划小节':'生成课程路线'}</button></div><small className="roadmap-form-hint">数量是上限，会按内容合理划分。未提供教材时，先按通用内容规划并注明假设。</small>
  </form>}
  {roadmap.plan&&<>
   <div className="roadmap-overview"><div><strong><RichText text={roadmap.plan.goal}/></strong><span>{roadmap.confirmed_sections} / {roadmap.sections.length} 节已确认理解</span><div className="roadmap-progress"><i style={{width:`${roadmap.confirmed_sections/roadmap.sections.length*100}%`}}/></div></div>{next?<button className="course-primary" disabled={planning||!!opening||roadmap.status!=='ready'} onClick={()=>onOpen(next)}>{opening===next.id?'正在打开…':next.session?`继续第 ${next.position} 节`:'按顺序开始'}<ArrowRight size={16}/></button>:<span className="roadmap-all-done"><Check size={18}/>本轮路线已走完，可回看复习</span>}</div>
   <div className="roadmap-section-grid">{roadmap.sections.map(section=><article key={section.id} className={`roadmap-section ${section.status}${section.id===next?.id?' recommended':''}`} data-section-id={section.id}>
    <div className="roadmap-section-heading"><span className="roadmap-order">{section.status==='confirmed'?<Check size={17}/>:String(section.position).padStart(2,'0')}</span><span className="roadmap-section-status">{section.status==='confirmed'?'节点已确认':section.status==='learning'?'学习中':section.id===next?.id?'推荐下一节':'待学习'}</span><small><Clock3 size={12}/>{section.estimated_minutes} 分钟</small></div>
    <h3><RichText text={section.title}/></h3><p><RichText text={section.objective}/></p><ul>{section.outcomes.map(outcome=><li key={outcome}><RichText text={outcome}/></li>)}</ul>
    {section.prerequisites.length>0&&<p className="roadmap-prerequisites"><Layers3 size={12}/>前置：{section.prerequisites.map(item=>item.title).join('、')}</p>}
    <div className="roadmap-section-footer"><small>{section.session?.total_nodes?`${section.session.confirmed_nodes} / ${section.session.total_nodes} 个教学节点`:'进入后规划本节教学节点'}</small><button className="course-secondary" disabled={planning||!!opening||roadmap.status!=='ready'} onClick={()=>onOpen(section)}>{opening===section.id?'正在打开…':section.status==='confirmed'||section.session?.completed?'回顾本节':section.session?'继续本节':'开始本节'}<ArrowRight size={14}/></button></div>
   </article>)}</div>
   <details className="roadmap-assumptions"><summary>规划依据与假设</summary><p>自述基础：{roadmap.inputs?.background||'尚未提供，需在学习中确认。'}</p><p>范围：{roadmap.inputs?.scope||'未指定教材范围，按课程名称和目标规划。'}</p>{roadmap.plan.assumptions.map(item=><p key={item}><RichText text={item}/></p>)}<p>前置关系是规划依据，节点进度来自学生确认，不代表已测评掌握。</p></details>
  </>}
  {costs&&costs.call_count>0&&<details className="roadmap-costs"><summary>大课规划用量 · {costs.call_count} 次模型调用</summary><p>输入 {costs.prompt_tokens} / 输出 {costs.completion_tokens} tokens；{Object.entries(costs.estimated_costs).map(([currency,value])=>`${currency} ${value.toFixed(6)}`).join('，')||'费用暂不可估算'}。未计价 {costs.unpriced_calls} 次。估算不是供应商账单。</p></details>}
 </section>;
}
