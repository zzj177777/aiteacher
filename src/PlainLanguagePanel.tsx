import {createContext,useCallback,useContext,useEffect,useLayoutEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {ArrowUpRight,Lightbulb,Sparkles} from 'lucide-react';
import RichText,{type TextAnnotation} from './RichText';
import './plain-language.css';

type Credential={session_id:string;token:string};
type Source={id:string;agent:string;text:string;status?:string;kind?:string;objective?:string};
type Concept={term:string;quote:string;why_difficult?:string;explanation:string;example:string;boundary:string};
type Explanation={id:string;source_message_id:string;format_version?:number;status:string;result:{takeaway:string;concepts:Concept[]}|null;error:{code:string;message:string}|null};
type NotesContext={records:Record<string,Explanation>;busy:Set<string>;errors:Record<string,string>;loading:boolean;latestId:string;request:(id:string)=>void;refresh:()=>void};
const Notes=createContext<NotesContext>({records:{},busy:new Set(),errors:{},loading:false,latestId:'',request:()=>{},refresh:()=>{}});
const isLecture=(source:Source)=>source.agent==='lecturer'&&source.status==='ai'&&source.kind!=='handoff';

export default function PlainLanguageProvider({credential,messages,working,children}:{credential:Credential|null;messages:Source[];working:boolean;children:ReactNode}){
 const [records,setRecords]=useState<Record<string,Explanation>>({}),[busy,setBusy]=useState<Set<string>>(new Set()),[errors,setErrors]=useState<Record<string,string>>({}),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0);
 const latestId=messages.filter(isLecture).at(-1)?.id||'';
 const posts=useRef(new Map<string,AbortController>()),readVersion=useRef(0);
 useEffect(()=>()=>{for(const request of posts.current.values())request.abort();},[]);
 useEffect(()=>{
  if(!credential||!latestId){setLoading(false);return;}
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined,misses=0;
  async function read(){
   let wait=working;const version=readVersion.current;
   try{
    const response=await fetch(`/api/sessions/${credential!.session_id}/plain-language`,{headers:{Authorization:`Bearer ${credential!.token}`},signal:controller.signal});
    if(!response.ok)throw new Error();const data=await response.json() as {explanations:Explanation[]};
    if(!controller.signal.aborted&&version===readVersion.current){setRecords(Object.fromEntries(data.explanations.map(record=>[record.source_message_id,record])));setErrors(old=>({...old,[latestId]:''}));}
    wait=working||data.explanations.some(record=>record.status==='pending')||(!data.explanations.some(record=>record.source_message_id===latestId)&&++misses<=8);
   }catch{if(!controller.signal.aborted)setErrors(old=>({...old,[latestId]:'批注暂时无法读取，可以重试。'}));}
   finally{if(!controller.signal.aborted){setLoading(false);if(wait)timer=setTimeout(read,1200);}}
  }
  void read();return()=>{controller.abort();if(timer)clearTimeout(timer);};
 },[credential?.session_id,credential?.token,latestId,working,refresh]);
 const request=useCallback(async(id:string)=>{
  if(!credential||posts.current.has(id))return;const controller=new AbortController();posts.current.set(id,controller);readVersion.current++;
  setBusy(old=>new Set(old).add(id));setErrors(old=>({...old,[id]:''}));
  try{
   const response=await fetch(`/api/sessions/${credential.session_id}/plain-language`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${credential.token}`},body:JSON.stringify({message_id:id}),signal:controller.signal});
   const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'批注生成未成功。');
   if(!controller.signal.aborted){setRecords(old=>({...old,[id]:data}));setRefresh(value=>value+1);}
  }catch(error){if(!controller.signal.aborted)setErrors(old=>({...old,[id]:(error as Error).message}));}
  finally{posts.current.delete(id);if(!controller.signal.aborted)setBusy(old=>{const next=new Set(old);next.delete(id);return next;});}
 },[credential?.session_id,credential?.token]);
 return <Notes.Provider value={{records,busy,errors,loading,latestId,request,refresh:()=>setRefresh(value=>value+1)}}>{children}</Notes.Provider>;
}

function annotations(source:Source,record?:Explanation){
 if(record?.status!=='completed'||!record.result)return [];
 return record.result.concepts.map(concept=>({...concept,start:source.text.indexOf(concept.quote)})).filter(concept=>concept.quote&&concept.start>=0).sort((a,b)=>a.start-b.start).map((concept,index)=>({...concept,index,id:`${record.id}-${index}`,end:concept.start+concept.quote.length}));
}

export function AnnotatedRichText({source}:{source:Source}){
 const {records}=useContext(Notes);
 const ranges:TextAnnotation[]=isLecture(source)?annotations(source,records[source.id]):[];
 return <RichText text={source.text} annotations={ranges}/>;
}

type Link={index:number;top:number;startX:number;startY:number;endX:number;endY:number;anchored:boolean};
type Layout={height:number;links:Link[]};
const colors=['#b99743','#699690','#8c81b0'];

export function AnnotatedMessage({source,children}:{source:Source;children:ReactNode}){
 const context=useContext(Notes),record=context.records[source.id];
 const items=useMemo(()=>annotations(source,record),[source.text,record]);
 const row=useRef<HTMLDivElement>(null),rail=useRef<HTMLElement>(null);
 const [layout,setLayout]=useState<Layout>({height:0,links:[]}),[active,setActive]=useState<number|null>(null);
 const lecture=isLecture(source),pending=context.busy.has(source.id)||record?.status==='pending'||context.loading&&context.latestId===source.id;
 useLayoutEffect(()=>{
  if(!lecture||!row.current||!rail.current)return;
  let frame=0,disposed=false;
  const round=(number:number)=>Math.round(number*10)/10;
  function measure(){
   if(disposed||!row.current||!rail.current)return;
   if(!window.matchMedia('(min-width:1000px)').matches){setLayout(old=>old.height||old.links.length?{height:0,links:[]}:old);return;}
   const article=row.current.querySelector<HTMLElement>('.conversation-message');if(!article)return;
   const rowRect=row.current.getBoundingClientRect(),articleRect=article.getBoundingClientRect(),railRect=rail.current.getBoundingClientRect();
   let bottom=0;const links:Link[]=[];
   for(const card of rail.current.querySelectorAll<HTMLElement>('[data-callout-index]')){
    const index=Number(card.dataset.calloutIndex),item=items[index];
    const anchors=item?[...article.querySelectorAll<HTMLElement>(`[data-plain-ids~="${CSS.escape(item.id)}"]`)]:[];
    const rects=anchors.flatMap(anchor=>[...anchor.getClientRects()]).filter(rect=>rect.width>0&&rect.height>0);
    const end=rects.at(-1),startY=end?end.top+end.height/2-rowRect.top:38;
    const top=Math.max(8,startY-27,bottom?bottom+18:0),height=card.getBoundingClientRect().height;
    links.push({index,top:round(top),startX:round(articleRect.right-rowRect.left+5),startY:round(startY),endX:round(railRect.left-rowRect.left-5),endY:round(top+27),anchored:!!end});
    bottom=top+height;
   }
   const next={height:Math.ceil(Math.max(articleRect.height,bottom+8)),links};
   setLayout(old=>JSON.stringify(old)===JSON.stringify(next)?old:next);
  }
  const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const observer=new ResizeObserver(schedule);
  const article=row.current.querySelector<HTMLElement>('.conversation-message');if(article)observer.observe(article);
  for(const card of rail.current.querySelectorAll<HTMLElement>('[data-callout-index]'))observer.observe(card);
  window.addEventListener('resize',schedule);document.fonts?.addEventListener('loadingdone',schedule);document.fonts?.ready.then(()=>{if(!disposed)schedule();});schedule();
  return()=>{disposed=true;cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',schedule);document.fonts?.removeEventListener('loadingdone',schedule);};
 },[lecture,record?.id,record?.status,items,pending,context.errors[source.id],children]);
 if(!lecture)return <>{children}</>;
 function locate(index:number){
  const item=items[index];if(!item)return;
  const anchor=row.current?.querySelector<HTMLElement>(`[data-plain-ids~="${CSS.escape(item.id)}"]`);
  setActive(index);anchor?.scrollIntoView({block:'center',behavior:'smooth'});anchor?.focus({preventScroll:true});
 }
 const position=(index:number)=>{const link=layout.links.find(link=>link.index===index);return link?{top:link.top}:undefined;};
 const error=context.errors[source.id];
 return <div ref={row} className="annotated-lecture" data-annotated-message-id={source.id} data-active-annotation={active??undefined} style={layout.height?{minHeight:layout.height}:undefined} onPointerOver={event=>{const target=(event.target as Element).closest<HTMLElement>('[data-plain-indexes]');if(target&&row.current?.contains(target))setActive(Number(target.dataset.plainIndexes?.split(' ')[0]));}} onPointerLeave={()=>setActive(null)}>
  {children}
  <svg className="plain-annotation-arrows" width="100%" height="100%" aria-hidden="true"><defs>{items.map(item=><marker id={`plain-arrow-${item.id}`} key={item.id} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill={colors[item.index%3]}/></marker>)}</defs>{layout.links.filter(link=>link.anchored&&link.index>=0).map(link=>{const item=items[link.index];if(!item)return null;return <g key={item.id} data-link-index={link.index}><circle cx={link.startX} cy={link.startY} r="2.5" fill={colors[link.index%3]}/><path className="plain-annotation-link" d={`M${link.startX},${link.startY} C${link.startX+20},${link.startY} ${link.endX-20},${link.endY} ${link.endX},${link.endY}`} stroke={colors[link.index%3]} fill="none" markerEnd={`url(#plain-arrow-${item.id})`}/></g>;})}</svg>
  <aside ref={rail} className="plain-annotation-rail" aria-label="通俗讲解" data-source-message-id={source.id}>
   {record?.status==='completed'&&items.length?items.map(item=><article key={item.id} className={`plain-callout plain-callout-color-${item.index%3}`} data-callout-index={item.index} data-annotation-id={item.id} style={position(item.index)} onPointerEnter={()=>setActive(item.index)} onFocus={()=>setActive(item.index)}>
    <div className="plain-callout-label"><Lightbulb size={13}/><span>说人话 · {String(item.index+1).padStart(2,'0')}</span><small>通俗讲解 Agent</small></div>
    <h3>{item.term}</h3>
    {item.why_difficult&&<p className="plain-difficulty"><span>可能卡在</span>{item.why_difficult}</p>}
    <p className="plain-definition"><RichText text={item.explanation}/></p>
    {item.example&&<details className="plain-example"><summary>看个直观例子</summary><p><RichText text={item.example}/></p>{item.boundary&&<small><RichText text={`类比边界：${item.boundary}`}/></small>}</details>}
    {!item.example&&item.boundary&&<small className="plain-boundary"><RichText text={item.boundary}/></small>}
    <details className="plain-source"><summary>这条批注对应的原文</summary><blockquote><RichText text={item.quote}/></blockquote></details>
    <button className="plain-locate" type="button" onClick={()=>locate(item.index)}>定位这句话<ArrowUpRight size={12}/></button>
    {(record.format_version||1)<2&&item.index===items.length-1&&<button className="plain-upgrade" type="button" onClick={()=>context.request(source.id)}>补充难点分析</button>}
   </article>):<div className="plain-callout-status" data-callout-index="-1" style={position(-1)}>
    {pending?<div className="plain-loading" role="status"><Sparkles size={16}/><strong>正在找出难懂的句子…</strong><span>定位原文 → 分别解释</span></div>:record?.status==='failed'?<div className="plain-error"><p>这段批注暂未生成成功。</p><small>{record.error?.message}</small><button type="button" onClick={()=>context.request(source.id)}>重新生成</button></div>:record?.status==='completed'?<p className="plain-no-difficulty">这段暂未标出需要额外解释的难点。</p>:<button className="plain-add-note" type="button" onClick={()=>context.request(source.id)}><Sparkles size={14}/>为这段加通俗批注</button>}
   </div>}
   {error&&<div className="plain-read-error plain-callout-status" data-callout-index="-2" style={position(-2)} role="alert"><span>{error}</span><button type="button" onClick={context.refresh}>重新读取</button></div>}
  </aside>
 </div>;
}
