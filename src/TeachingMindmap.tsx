import React,{useEffect,useRef,useState} from 'react';
import type {Markmap} from 'markmap-view';

export default function TeachingMindmap({markdown,title}:{markdown:string;title:string}){
 const svg=useRef<SVGSVGElement>(null);const map=useRef<Markmap|null>(null);
 const [status,setStatus]=useState('正在加载思维导图…');
 useEffect(()=>{
  let cancelled=false;let observer:ResizeObserver|undefined;let instance:Markmap|undefined;
  (async()=>{try{
   const [{Transformer},{Markmap},{default:purifier}]=await Promise.all([import('markmap-lib/no-plugins'),import('markmap-view'),import('dompurify')]);
   if(cancelled||!svg.current)return;
   const transformer=new Transformer();
   transformer.md.set({html:false,linkify:false});
   const {root}=transformer.transform(markdown);
   const clean=(node:typeof root)=>{
    node.content=purifier.sanitize(node.content,{ALLOWED_TAGS:['strong','em','code','span','br','s','del'],ALLOWED_ATTR:[]});
    node.children?.forEach(clean);
   };clean(root);
   instance=Markmap.create(svg.current,{duration:0,maxWidth:230,initialExpandLevel:2},root);
   map.current=instance;
   await instance.fit();
   if(cancelled)return;
   observer=new ResizeObserver(()=>{void instance?.fit();});observer.observe(svg.current);
   setStatus('');
  }catch{if(!cancelled)setStatus('思维导图暂时无法显示，可以展开下方文字大纲。');}})();
  return()=>{cancelled=true;observer?.disconnect();instance?.destroy();map.current=null;};
 },[markdown]);
 return <div className="teaching-mindmap">
  <div className="drawing-controls"><button type="button" onClick={()=>void map.current?.fit()}>适应窗口</button><span>滚轮缩放 · 拖动平移 · 点击节点圆点展开或折叠</span></div>
  {status&&<p role="status">{status}</p>}
  <svg ref={svg} role="img" aria-label={title} style={{width:'100%',height:420,display:'block',background:'#fff',touchAction:'none'}}/>
  <details><summary>查看文字大纲</summary><pre style={{whiteSpace:'pre-wrap'}}>{markdown}</pre></details>
 </div>;
}
