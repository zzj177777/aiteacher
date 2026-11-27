import {useLayoutEffect,useRef,useState,type ReactNode} from 'react';

/** Fixed viewport; fit short content, scroll long content at a readable scale. */
export default function WhiteboardSurface({children,pageKey}:{children:ReactNode;pageKey:string}){
 const host=useRef<HTMLDivElement>(null),content=useRef<HTMLDivElement>(null);
 const [layout,setLayout]=useState({width:600,scale:1,overflow:false});
 useLayoutEffect(()=>{
  const frame=host.current,ink=content.current;if(!frame||!ink)return;
  let animation=0,disposed=false;
  const measure=()=>{
   if(disposed)return;
   cancelAnimationFrame(animation);animation=requestAnimationFrame(()=>{
    const width=Math.max(1,frame.clientWidth-40),height=Math.max(1,frame.clientHeight-(frame.querySelector('.attention-insights')?70:40));
    const logicalWidth=Math.max(320,Math.min(width,850));
    const widthScale=Math.min(1,width/Math.max(logicalWidth,ink.scrollWidth));
    const fitScale=Math.min(widthScale,height/Math.max(1,ink.scrollHeight));
    const scale=Math.max(Math.min(.8,widthScale),fitScale),overflow=fitScale+.002<scale;
    setLayout(old=>Math.abs(old.width-logicalWidth)>.5||Math.abs(old.scale-scale)>.002||old.overflow!==overflow?{width:logicalWidth,scale,overflow}:old);
   });
  };
  const observer=new ResizeObserver(measure);observer.observe(frame);observer.observe(ink);measure();
  // SVG/images and web fonts may settle after the first layout.
  ink.addEventListener('load',measure,true);void document.fonts?.ready.then(measure);
  frame.addEventListener('attention-notes-change',measure);
  return()=>{disposed=true;observer.disconnect();ink.removeEventListener('load',measure,true);frame.removeEventListener('attention-notes-change',measure);cancelAnimationFrame(animation);};
 },[pageKey]);
 return <div className={`whiteboard-surface${layout.overflow?' whiteboard-overflow':''}`} ref={host} data-page={pageKey}><div className="whiteboard-ink" ref={content} data-scale={layout.scale} style={{width:layout.width,transform:`scale(${layout.scale})`}}>{children}</div></div>;
}
