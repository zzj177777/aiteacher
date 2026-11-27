import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import RichText from './RichText';
import './selection-explainer.css';

type SelectionInfo={text:string;message_id:string;board_id?:string;step_id?:string;detour_id?:string;left:number;top:number;owner:HTMLElement;identity:string;host:HTMLElement|null};
type Credential={session_id:string;token:string};
const identity=(element:HTMLElement)=>['messageId','boardId','stepId','detourId','page'].map(key=>element.dataset[key]||'').join(':');

export default function SelectionExplainer({credential,mode='chat',contextKey='',onExplain}:{credential:Credential|null;mode?:'chat'|'digital';contextKey?:string;onExplain?:()=>void}){
 const [selection,setSelection]=useState<SelectionInfo|null>(null);
 const [quote,setQuote]=useState<SelectionInfo|null>(null);
 const [open,setOpen]=useState(false);const [loading,setLoading]=useState(false);
 const [answer,setAnswer]=useState('');const [error,setError]=useState('');
 const controller=useRef<AbortController|null>(null);const serial=useRef(0);
 const closeRef=useRef<HTMLButtonElement>(null);
 function close(){serial.current++;controller.current?.abort();setOpen(false);setLoading(false);}
 useEffect(()=>{
  setSelection(null);setQuote(null);setOpen(false);setLoading(false);setAnswer('');setError('');serial.current++;controller.current?.abort();
  function capture(){
   const selected=window.getSelection();
   if(!credential||!selected||selected.isCollapsed||!selected.rangeCount){setSelection(null);return;}
   const range=selected.getRangeAt(0);const ancestor=range.commonAncestorContainer;
   const element=ancestor.nodeType===Node.ELEMENT_NODE?ancestor as Element:ancestor.parentElement;
   const article=element?.closest<HTMLElement>(mode==='digital'?'.whiteboard[data-message-id],.digital-message[data-message-id]':'.conversation-message[data-message-id]');
   if(!article||!article.closest(mode==='digital'?'.digital-classroom':'.conversation')){setSelection(null);return;}
   if(mode==='digital'&&!element?.closest('.whiteboard-surface,.whiteboard-title,.detour-origin,.main-return-bridge,.digital-message-body')){setSelection(null);return;}
   // KaTeX contains a hidden MathML copy. Send only the visible selection once.
   const fragment=range.cloneContents();fragment.querySelectorAll('.katex-mathml,math,annotation').forEach(node=>node.remove());
   const text=(fragment.textContent||'').trim();
   if(!text||text.length>2000){setSelection(null);return;}
   const rect=range.getBoundingClientRect();
   if(!rect.width&&!rect.height){setSelection(null);return;}
   setSelection({text,message_id:article.dataset.messageId!,...(article.dataset.boardId?{board_id:article.dataset.boardId,step_id:article.dataset.stepId}:{}),...(article.dataset.detourId?{detour_id:article.dataset.detourId}:{}),left:Math.max(8,Math.min(rect.left,window.innerWidth-150)),top:Math.max(8,Math.min(rect.bottom+7,window.innerHeight-48)),owner:article,identity:identity(article),host:article.closest<HTMLElement>('dialog[open]')});
  }
  function hide(){setSelection(null);}
  document.addEventListener('selectionchange',capture);
  window.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);
  return()=>{document.removeEventListener('selectionchange',capture);window.removeEventListener('scroll',hide,true);window.removeEventListener('resize',hide);serial.current++;controller.current?.abort();};
 },[credential?.session_id,credential?.token,mode,contextKey]);
 useEffect(()=>{
  if(mode!=='digital'||(!selection&&!open))return;
  const invalid=(pick:SelectionInfo)=>!pick.owner.isConnected||identity(pick.owner)!==pick.identity;
  const observer=new MutationObserver(()=>{
   if(selection&&invalid(selection))setSelection(null);
   if(open&&quote&&invalid(quote))close();
  });
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-message-id','data-board-id','data-step-id','data-detour-id','data-page']});
  return()=>observer.disconnect();
 },[mode,selection,quote,open]);
 useEffect(()=>{if(open)closeRef.current?.focus();},[open]);
 useEffect(()=>{if(!open)return;const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close();}};document.addEventListener('keydown',escape,true);return()=>document.removeEventListener('keydown',escape,true);},[open]);
 async function explain(pick:SelectionInfo){
  if(!credential||!pick.owner.isConnected||identity(pick.owner)!==pick.identity){setSelection(null);return;}
  onExplain?.();
  controller.current?.abort();const abort=new AbortController();controller.current=abort;const id=++serial.current;
  setQuote(pick);setOpen(true);setLoading(true);setError('');setAnswer('');setSelection(null);window.getSelection()?.removeAllRanges();
  try{
   const response=await fetch(`/api/sessions/${credential.session_id}/explain`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential.token}`},body:JSON.stringify({text:pick.text,message_id:pick.message_id,...(pick.board_id?{board_id:pick.board_id,step_id:pick.step_id}:{}),...(pick.detour_id?{detour_id:pick.detour_id}:{})})});
   const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'解释暂不可用，请重试。');
   if(serial.current===id)setAnswer(data.text);
  }catch(e){if(serial.current===id&&!abort.signal.aborted)setError((e as Error).message);}
  finally{if(serial.current===id)setLoading(false);}
 }
 return createPortal(<>
  {selection&&credential&&<button type="button" className="selection-explain-trigger" style={{left:selection.left,top:selection.top}} onMouseDown={e=>e.preventDefault()} onClick={()=>explain(selection)}>解释选中内容</button>}
  {open&&<aside className="selection-explain-panel" role="dialog" aria-modal="false" aria-label="选中内容解释"><header><strong>简要解释</strong><button ref={closeRef} type="button" aria-label="关闭解释" onClick={close}>×</button></header><blockquote>{quote?.text}</blockquote><div className="selection-explain-body" aria-live="polite">{loading?<p role="status">正在结合上下文解释…</p>:error?<><p role="alert">{error}</p><button type="button" onClick={()=>quote&&explain(quote)}>重新解释</button></>:<p><RichText text={answer}/></p>}</div><footer>结合所选原文 · 不改变课堂进度 · Esc 关闭</footer></aside>}
 </>,(open?quote?.host:selection?.host)||document.body);
}
