import {useEffect, useId, useState} from 'react';
import {ArrowRight, BookOpen, Check, CheckCircle2, Clock3, Compass, GraduationCap, MessageCircle, Sparkles, Target} from 'lucide-react';
import './intake.css';

export type LearningIntakeData = {
  topic:string; goals:string[]; stage:string; grade:string; background:string;
  time_budget:string; textbook:string; chapter:string; exam_scope:string; exam_date:string;
};
const empty:LearningIntakeData={topic:'',goals:[],stage:'',grade:'',background:'',time_budget:'',textbook:'',chapter:'',exam_scope:'',exam_date:''};
const draftKey='aiteacher.intake.draft.v1';
const goals=[{label:'入门理解',hint:'从容易懂的地方开始',icon:Compass},{label:'跟上课堂',hint:'配合教材与学校进度',icon:BookOpen},{label:'备考提分',hint:'围绕考试查漏补缺',icon:Target},{label:'解决具体问题',hint:'弄懂一道题或一个难点',icon:MessageCircle}];
const grades:Record<string,string[]>={'小学':['一年级','二年级','三年级','四年级','五年级','六年级'],'初中':['初一','初二','初三'],'高中':['高一','高二','高三'],'大学':['大一','大二','大三','大四','研究生']};
function loadDraft():LearningIntakeData {
  try {const raw=JSON.parse(sessionStorage.getItem(draftKey)||'null');if(!raw||typeof raw!=='object')return {...empty};return {...empty,...Object.fromEntries(Object.keys(empty).map(key=>[key,key==='goals'?Array.isArray(raw.goals)?raw.goals.filter((g:unknown)=>goals.some(item=>item.label===g)):[]:typeof raw[key]==='string'?raw[key]:'']))} as LearningIntakeData;}catch{return {...empty};}
}

export default function LearningIntake({busy,onSubmit,onSkip,onCancel}:{busy:boolean;onSubmit:(data:LearningIntakeData)=>Promise<boolean>;onSkip:()=>void;onCancel?:()=>void}){
  const [data,setData]=useState<LearningIntakeData>(loadDraft);
  const [attempted,setAttempted]=useState(false);
  const uid=useId();
  useEffect(()=>{try{sessionStorage.setItem(draftKey,JSON.stringify(data));}catch{/* Form remains usable if browser storage is unavailable. */}},[data]);
  const update=(key:keyof LearningIntakeData,value:string)=>setData(old=>({...old,[key]:value}));
  const count=Number(!!data.topic.trim())+Number(!!data.goals.length)+Number(!!data.stage);
  const topicError=attempted&&!data.topic.trim(),goalError=attempted&&!data.goals.length,stageError=attempted&&!data.stage;
  async function submit(e:React.FormEvent){
    e.preventDefault();setAttempted(true);
    if(count<3){requestAnimationFrame(()=>document.getElementById(!data.topic.trim()?`${uid}-topic`:!data.goals.length?`${uid}-goal-0`:`${uid}-stage-0`)?.focus());return;}
    const payload={...data,topic:data.topic.trim(),grade:grades[data.stage]?.includes(data.grade)?data.grade:'',textbook:data.goals.includes('跟上课堂')?data.textbook.trim():'',chapter:data.goals.includes('跟上课堂')?data.chapter.trim():'',exam_scope:data.goals.includes('备考提分')?data.exam_scope.trim():'',exam_date:data.goals.includes('备考提分')?data.exam_date:''};
    if(await onSubmit(payload)){try{sessionStorage.removeItem(draftKey);}catch{/* Optional local draft. */}}
  }
  return <section className="intake-shell" aria-label="学习初始化">
    <aside className="intake-intro">
      <div className="intake-eyebrow"><span/> 为你安排的学习，从这里开始</div>
      <h2>先认识你，<br/>再一起学明白<span>。</span></h2>
      <p className="intake-lead">告诉我你想走到哪里。<br/>我们一起找到适合你的第一步。</p>
      <div className="intake-journey" aria-label="学习安排流程">
        {[{icon:Compass,title:'了解你的目标',text:'你来选择想学的内容',active:true},{icon:BookOpen,title:'商量学习路线',text:'先看计划，再决定怎么开始'},{icon:CheckCircle2,title:'边学，边调整',text:'从实际作答中逐步了解你'}].map((step,i)=><div className={`intake-journey-step${step.active?' active':''}`} key={step.title}><span className="intake-step-icon"><step.icon size={19}/></span><div><small>0{i+1}</small><strong>{step.title}</strong><p>{step.text}</p></div></div>)}
      </div>
      <div className="intake-note"><Sparkles size={17}/><p>不用证明自己已经会了。<br/>“不清楚”“没学过”，都是有用的起点。</p></div>
    </aside>
    <form className="intake-card" onSubmit={submit} noValidate>
      <div className="intake-card-heading"><div><span className="intake-kicker">你的学习起点</span><h3>今天，我们学点什么？</h3></div><span className="intake-time"><Clock3 size={14}/> 约 1 分钟</span></div>
      <div className="intake-progress"><span>完成 3 项，就可以开始</span><span aria-live="polite">{count} / 3</span><div><i style={{width:`${count/3*100}%`}}/></div></div>
      <fieldset disabled={busy} className="intake-fields">
        <div className="intake-field"><label htmlFor={`${uid}-topic`}><span className="intake-number">01</span>你想学什么？<span className="intake-required">必填</span></label><textarea id={`${uid}-topic`} value={data.topic} onChange={e=>update('topic',e.target.value)} rows={2} maxLength={300} placeholder="输入一个科目、知识点，或粘贴想弄懂的题目…" aria-invalid={topicError} aria-describedby={topicError?`${uid}-topic-error`:undefined}/>{topicError&&<p id={`${uid}-topic-error`} className="intake-field-error">先告诉我想学的内容。</p>}</div>
        <fieldset className="intake-choice-field" aria-describedby={goalError?`${uid}-goal-error`:undefined}><legend><span className="intake-number">02</span>这次想达到什么目标？<span className="intake-optional">可多选</span></legend><div className="intake-goal-grid">{goals.map((goal,i)=>{const selected=data.goals.includes(goal.label);return <button id={`${uid}-goal-${i}`} key={goal.label} type="button" aria-pressed={selected} className={`intake-goal${selected?' selected':''}`} onClick={()=>setData(old=>({...old,goals:selected?old.goals.filter(g=>g!==goal.label):[...old.goals,goal.label]}))}><span className="intake-goal-icon"><goal.icon size={18}/></span><span><strong>{goal.label}</strong><small>{goal.hint}</small></span><span className="intake-check">{selected&&<Check size={12}/>}</span></button>;})}</div>{goalError&&<p id={`${uid}-goal-error`} className="intake-field-error">请选择至少一个学习目标。</p>}</fieldset>
        <fieldset className="intake-choice-field" aria-describedby={stageError?`${uid}-stage-error`:undefined}><legend><span className="intake-number">03</span>你目前处于哪个阶段？<span className="intake-required">必填</span></legend><div className="intake-stage-options">{['小学','初中','高中','大学','自主学习'].map((stage,i)=><button id={`${uid}-stage-${i}`} type="button" key={stage} aria-pressed={data.stage===stage} onClick={()=>setData(old=>({...old,stage,grade:''}))}>{stage}</button>)}</div>{grades[data.stage]&&<label className="intake-grade">具体年级 <span>可选</span><select aria-label="具体年级" value={data.grade} onChange={e=>update('grade',e.target.value)}><option value="">暂不填写</option>{grades[data.stage].map(grade=><option key={grade}>{grade}</option>)}</select></label>}{stageError&&<p id={`${uid}-stage-error`} className="intake-field-error">请选择一个学习阶段。</p>}</fieldset>
        {(data.goals.includes('跟上课堂')||data.goals.includes('备考提分'))&&<div className="intake-followups"><p><GraduationCap size={16}/> 再补充一点，让安排更贴近你 <span>均可跳过</span></p>{data.goals.includes('跟上课堂')&&<div className="intake-input-pair"><label>教材版本<input value={data.textbook} maxLength={100} placeholder="不确定也没关系" onChange={e=>update('textbook',e.target.value)}/></label><label>当前章节或进度<input value={data.chapter} maxLength={200} placeholder="学校最近学到哪里？" onChange={e=>update('chapter',e.target.value)}/></label></div>}{data.goals.includes('备考提分')&&<div className="intake-input-pair"><label>考试范围<input value={data.exam_scope} maxLength={300} placeholder="考试科目、章节或重点" onChange={e=>update('exam_scope',e.target.value)}/></label><label>考试日期<input type="date" value={data.exam_date} onChange={e=>update('exam_date',e.target.value)}/></label></div>}</div>}
        <details className="intake-extra"><summary>补充基础与学习时间 <span>选填</span></summary><label htmlFor={`${uid}-background`}>学过哪些内容？哪里容易卡住？</label><textarea id={`${uid}-background`} rows={2} maxLength={600} value={data.background} placeholder="可以简单说说，也可以写“不清楚”…" onChange={e=>update('background',e.target.value)}/><fieldset className="intake-choice-field"><legend>这次有多少时间？</legend><div className="intake-duration">{['10 分钟','20 分钟','40 分钟','不限'].map(time=><button key={time} type="button" aria-pressed={data.time_budget===time} onClick={()=>update('time_budget',data.time_budget===time?'':time)}>{time}</button>)}</div></fieldset></details>
        <div className="intake-submit"><button type="submit" className="intake-primary">{busy?'正在提交…':'生成我的学习计划'}{!busy&&<ArrowRight size={18}/>}</button><p>先形成初步计划，再一起确认。自述不会直接当作已掌握。</p></div>
      </fieldset>
      <div className="intake-card-footer"><button disabled={busy} type="button" onClick={onSkip}><MessageCircle size={15}/> 想边聊边说？直接聊天</button>{onCancel&&<button type="button" disabled={busy} onClick={onCancel}>返回当前课堂</button>}</div>
    </form>
  </section>;
}
