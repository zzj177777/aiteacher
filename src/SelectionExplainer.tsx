import React,{useEffect,useRef,useState} from 'react';
import RichText from './RichText';

type SelectionInfo={text:string;message_id:string;left:number;top:number};
type Credential={session_id:string;token:string};

export default function SelectionExplainer({credential}:{credential:Credential|null}){
 const [selection,setSelection]=useState<SelectionInfo|null>(null);
 const [quote,setQuote]=useState<SelectionInfo|null>(null);
 const [open,setOpen]=useState(false);const [loading,setLoading]=useState(false);
 const [answer,setAnswer]=useState('');const [error,setError]=useState('');
 const controller=useRef<AbortController|null>(null);const serial=useRef(0);
 const closeRef=useRef<HTMLButtonElement>(null);
 function close(){serial.current++;controller.current?.abort();setOpen(false);setLoading(false);}
 useEffect(()=>{
  setSelection(null);setOpen(false);serial.current++;controller.current?.abort();
  function capture(){
   const selected=window.getSelection();const text=selected?.toString().trim()??'';
   if(!selected||selected.isCollapsed||!text||text.length>2000||!selected.rangeCount){setSelection(null);return;}
   const range=selected.getRangeAt(0);const ancestor=range.commonAncestorContainer;
   const element=ancestor.nodeType===Node.ELEMENT_NODE?ancestor as Element:ancestor.parentElement;
   const article=element?.closest<HTMLElement>('.conversation-message[data-message-id]');
   if(!article?.closest('.conversation')){setSelection(null);return;}
   const rect=range.getBoundingClientRect();
   if(!rect.width&&!rect.height){setSelection(null);return;}
   setSelection({text,message_id:article.dataset.messageId!,left:Math.max(8,Math.min(rect.left,window.innerWidth-150)),top:Math.max(8,Math.min(rect.bottom+7,window.innerHeight-48))});
  }
  function hide(){setSelection(null);}
  document.addEventListener('selectionchange',capture);
  window.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);
  return()=>{document.removeEventListener('selectionchange',capture);window.removeEventListener('scroll',hide,true);window.removeEventListener('resize',hide);serial.current++;controller.current?.abort();};
 },[credential?.session_id]);
 useEffect(()=>{if(open)closeRef.current?.focus();},[open]);
 useEffect(()=>{if(!open)return;const escape=(e:KeyboardEvent)=>{if(e.key==='Escape')close();};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[open]);
 async function explain(pick:SelectionInfo){
  if(!credential)return;
  controller.current?.abort();const abort=new AbortController();controller.current=abort;const id=++serial.current;
  setQuote(pick);setOpen(true);setLoading(true);setError('');setAnswer('');setSelection(null);window.getSelection()?.removeAllRanges();
  try{
   const response=await fetch(`/api/sessions/${credential.session_id}/explain`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential.token}`},body:JSON.stringify({text:pick.text,message_id:pick.message_id})});
   const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'解释暂不可用，请重试。');
   if(serial.current===id)setAnswer(data.text);
  }catch(e){if(serial.current===id&&!abort.signal.aborted)setError((e as Error).message);}
  finally{if(serial.current===id)setLoading(false);}
 }
 return <>
  {selection&&credential&&<button type="button" className="selection-explain-trigger" style={{left:selection.left,top:selection.top}} onMouseDown={e=>e.preventDefault()} onClick={()=>explain(selection)}>解释选中内容</button>}
  {open&&<aside className="selection-explain-panel" role="dialog" aria-modal="false" aria-label="选中内容解释"><header><strong>简要解释</strong><button ref={closeRef} type="button" aria-label="关闭解释" onClick={close}>×</button></header><blockquote>{quote?.text}</blockquote><div className="selection-explain-body" aria-live="polite">{loading?<p role="status">正在结合上下文解释…</p>:error?<><p role="alert">{error}</p><button type="button" onClick={()=>quote&&explain(quote)}>重新解释</button></>:<p><RichText text={answer}/></p>}</div><footer>结合所选原文 · 不改变课堂进度 · Esc 关闭</footer></aside>}
 </>;
}
