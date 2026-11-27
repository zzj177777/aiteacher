import {useState,type FormEvent} from 'react';
import {ArrowRight,RotateCcw} from 'lucide-react';
import RichText from './RichText';
import WhiteboardSurface from './WhiteboardSurface';
import {parseChoiceQuestion,selectedChoices,choiceAnswer} from './boardQuestion';
import './whiteboard.css';
import './step-board.css';

/** Delivery only: the saved pending question belongs to the assessment agent. */
export default function AssessmentBoard({question,messageId,introduction,disabled,onAnswer,onHelp,onReplay}:{
 question:{id:string;question:string;objective?:string};messageId:string;introduction:string;disabled:boolean;
 onAnswer:(answer:string)=>void;onHelp:()=>void;onReplay:()=>void;
}){
 const [answer,setAnswer]=useState('');
 const choice=parseChoiceQuestion(question.question),selected=choice?selectedChoices(choice.options,answer):[];
 const instruction=introduction.endsWith(question.question)?introduction.slice(0,-question.question.length).trim():'';
 function submit(event:FormEvent){event.preventDefault();if(!disabled&&answer.trim())onAnswer(answer);}
 return <section className="whiteboard" aria-label="测评 Agent 白板" data-message-id={messageId}>
  <div className="whiteboard-toolbar"><span>独立测评 · {question.objective||'检查当前理解'}</span><button disabled={disabled} onClick={onReplay}><RotateCcw size={14}/>重听题目</button></div>
  <div className="whiteboard-title"><div><span className="step-board-kicker">先试一题，了解你现在的情况</span><h2>测评 Agent</h2></div><span className="whiteboard-page-label">诊断 / 随堂测评</span></div>
  <div className="assessment-agent-label"><strong>测评 Agent</strong><span>独立出题与判答 · 白板呈现</span></div>
  <WhiteboardSurface pageKey={question.id}>
   <section className="whiteboard-exercise" aria-label="测评题目">
    {instruction&&<div className="assessment-instruction"><RichText text={instruction}/></div>}
    <div className="step-board-question-text"><RichText text={choice?.prompt||question.question}/></div>
    {choice?<fieldset className="step-board-choices" disabled={disabled}><legend>{choice.multiple?'多选 · 可以选择多个选项':'单选 · 点击一个选项'}</legend>{choice.options.map(option=><label key={option.id} className={`step-board-choice${selected.includes(option.id)?' selected':''}`}><input type={choice.multiple?'checkbox':'radio'} name={`assessment-${question.id}`} value={option.id} checked={selected.includes(option.id)} onChange={()=>{const next=choice.multiple?(selected.includes(option.id)?selected.filter(id=>id!==option.id):[...selected,option.id]):[option.id];setAnswer(choiceAnswer(choice.options,next));}}/><span className="step-board-choice-letter">{option.id}</span><span className="step-board-choice-text"><RichText text={option.text}/></span></label>)}</fieldset>:
     <form id={`assessment-${question.id}`} onSubmit={submit}><label className="step-board-answer-label">你的回答<textarea aria-label="测评 Agent 题目回答" rows={3} maxLength={4000} value={answer} onChange={e=>setAnswer(e.target.value)} disabled={disabled} placeholder="写出答案，也可以说说你的思路…"/></label></form>}
   </section>
  </WhiteboardSurface>
  <footer className="whiteboard-footer"><small>一次作答用于了解当前情况，不等同长期掌握。</small><div className="whiteboard-footer-right"><button disabled={disabled} onClick={onHelp}>还不会，先请老师讲解</button><button className="whiteboard-primary" disabled={disabled||!answer.trim()} onClick={()=>onAnswer(answer)}>{disabled?'正在处理…':'交给测评 Agent 检查'}<ArrowRight size={15}/></button></div></footer>
 </section>;
}
