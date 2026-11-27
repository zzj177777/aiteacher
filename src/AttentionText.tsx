import {useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {annotate} from 'rough-notation';
import RichText from './RichText';
import {attentionCues,type TeachingMark} from './attentionModel';
import type {BoardBlock} from './whiteboardBlocks';
import type {SpeechCue} from './digitalNarrator';

export function AttentionInsights({cues}:{cues:TeachingMark[]}){
 return <>{cues.filter(cue=>cue.kind!=='key_point'&&cue.explanation).map(cue=><details key={cue.id} className={`attention-insight ${cue.kind}`}><summary>{cue.kind==='pitfall'?'可能易错':'理解提示'}</summary><div><RichText text={cue.explanation}/></div><small>教学预测，不代表你已经犯错或不会。</small></details>)}</>;
}

export default function AttentionText({units,revealed,marks=[],spokenRange=null}:{units:BoardBlock[];revealed:number;marks?:TeachingMark[];spokenRange?:SpeechCue|null}){
 const root=useRef<HTMLDivElement>(null);
 const [surfaceHost,setSurfaceHost]=useState<Element|null>(null);
 const active=spokenRange?.last_unit??Math.min(units.length-1,revealed-1);
 const cues=units[active]?attentionCues(units[active],marks):[];
 const cueKey=cues.map(cue=>`${cue.id}:${cue.style}:${cue.start}:${cue.end}`).join('|');
 const hasInsights=cues.some(cue=>cue.kind!=='key_point'&&cue.explanation);
 useLayoutEffect(()=>{setSurfaceHost(root.current?.closest('.whiteboard-surface')||null);},[]);
 useLayoutEffect(()=>{surfaceHost?.dispatchEvent(new Event('attention-notes-change'));},[surfaceHost,hasInsights]);
 useLayoutEffect(()=>{
  let frame=requestAnimationFrame(()=>{frame=requestAnimationFrame(()=>{
   if(!surfaceHost?.classList.contains('whiteboard-overflow'))return;
   const row=root.current?.querySelector('.attention-row.current');if(!row)return;
   const box=surfaceHost.getBoundingClientRect(),rect=row.getBoundingClientRect();
   if(rect.top<box.top+10||rect.bottom>box.bottom-35)surfaceHost.scrollTop=Math.max(0,surfaceHost.scrollTop+rect.top-box.top-20);
  });});
  return()=>cancelAnimationFrame(frame);
 },[active,surfaceHost,cueKey]);
 useLayoutEffect(()=>{
  const writing=root.current,surface=writing?.closest('.whiteboard-surface'),ink=writing?.closest('.whiteboard-ink');
  if(!writing||!surface||!ink||!cues.length)return;
  const layer=document.createElement('div');layer.className='attention-overlay';layer.setAttribute('aria-hidden','true');surface.appendChild(layer);
  let disposed=false,frame=0;
  let drawings:ReturnType<typeof annotate>[]=[];
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
  const draw=(animate=false)=>{
   if(disposed)return;
   drawings.forEach(item=>item.remove());drawings=[];layer.replaceChildren();
   const origin=surface.getBoundingClientRect();
   for(const cue of cues){
    const marks=Array.from(writing.querySelectorAll<HTMLElement>('.attention-row.current mark')).filter(mark=>mark.dataset.plainIds?.split(' ').includes(cue.id));
    const raw=marks.flatMap(mark=>Array.from((mark.querySelector<HTMLElement>('.formula-block .katex-html')||mark).getClientRects())).filter(rect=>rect.width>1&&rect.height>1);
    const rectangles:{left:number;top:number;right:number;bottom:number}[]=[];
    for(const rect of raw){
     const row=rectangles.find(old=>Math.min(old.bottom,rect.bottom)-Math.max(old.top,rect.top)>Math.min(old.bottom-old.top,rect.height)*.5);
     if(row){row.left=Math.min(row.left,rect.left);row.right=Math.max(row.right,rect.right);row.top=Math.min(row.top,rect.top);row.bottom=Math.max(row.bottom,rect.bottom);}
     else rectangles.push({left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom});
    }
    for(const rect of rectangles){
    const anchor=document.createElement('span');anchor.className='attention-overlay-anchor';
    Object.assign(anchor.style,{left:`${rect.left-origin.left+surface.scrollLeft}px`,top:`${rect.top-origin.top+surface.scrollTop}px`,width:`${rect.right-rect.left}px`,height:`${rect.bottom-rect.top}px`});
    layer.appendChild(anchor);
    const drawing=annotate(anchor,{type:cue.style,color:cue.style==='highlight'?'#ffe698':'#cf4d46',strokeWidth:1.8,padding:cue.style==='circle'?5:2,iterations:1,
     animate:animate&&!reduce.matches,animationDuration:360});
    drawings.push(drawing);drawing.show();
    }
   }
  };
  const schedule=()=>{if(!disposed){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>draw(false));}};
  frame=requestAnimationFrame(()=>draw(true));
  const resize=new ResizeObserver(schedule);resize.observe(surface);resize.observe(writing);
  const transform=new MutationObserver(schedule);transform.observe(ink,{attributes:true,attributeFilter:['style']});
  window.addEventListener('resize',schedule);reduce.addEventListener('change',schedule);
  void document.fonts?.ready.then(schedule);
  return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();transform.disconnect();window.removeEventListener('resize',schedule);reduce.removeEventListener('change',schedule);drawings.forEach(item=>item.remove());layer.remove();};
 },[active,cueKey,units[active]?.text]);
 return <><div ref={root} className="whiteboard-writing attention-writing">
  {units.map((unit,i)=><div key={unit.start} className={`attention-row ${i>=revealed?'future':i===active?'current':'past'}${spokenRange&&i>=spokenRange.first_unit&&i<=spokenRange.last_unit?' is-reading':''}`} aria-hidden={i>=revealed} aria-current={i===active?'step':undefined}>
   <RichText text={unit.text} sourceOffset={unit.start} annotations={i===active?cues.map((cue,index)=>({id:cue.id,index,start:cue.start,end:cue.end})):[]}/>
  </div>)}
 </div>{surfaceHost&&hasInsights&&createPortal(<div className="attention-insights" aria-label="当前内容的教学提示"><AttentionInsights cues={cues}/></div>,surfaceHost)}</>;
}
