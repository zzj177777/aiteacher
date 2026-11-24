import React,{lazy,Suspense,useEffect,useId,useRef,useState} from 'react';
import '../node_modules/jsxgraph/distrib/jsxgraph.css';

const TeachingMindmap=lazy(()=>import('./TeachingMindmap'));

export type DrawingSpec={id:string;tool:string;title:string;caption:string;engine:string;expression?:string;x_min?:number;x_max?:number;y_min?:number;y_max?:number;a?:number;b?:number;rectangles?:number;sampling?:string;diagram?:string;markdown?:string};

export default function TeachingDrawing({spec}:{spec:DrawingSpec}){
 const unique='teaching-'+useId().replace(/[^a-zA-Z0-9-]/g,'');
 const host=useRef<HTMLDivElement>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(true);
 const [count,setCount]=useState(spec.rectangles??8);const [sampling,setSampling]=useState(spec.sampling??'right');
 const [sum,setSum]=useState<number|null>(null);const [image,setImage]=useState('');
 useEffect(()=>{
  let stopped=false;let dispose:(()=>void)|undefined;setLoading(true);setError('');setSum(null);setImage('');
  (async()=>{try{
   if(spec.tool==='draw_mindmap'){
    if(!stopped)setLoading(false);return;
   }else if(spec.tool==='draw_diagram'){
    const {default:mermaid}=await import('mermaid');
    mermaid.initialize({startOnLoad:false,securityLevel:'strict',suppressErrorRendering:true,flowchart:{htmlLabels:false},theme:'neutral'});
    const {svg}=await mermaid.render(unique+'-'+Date.now(),spec.diagram??'');
    if(stopped)return;
    const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));dispose=()=>URL.revokeObjectURL(url);setImage(url);
   }else{
    const [{default:JXG},{buildFunction}]=await Promise.all([import('jsxgraph'),import('./drawingExpression')]);
    if(stopped||!host.current)return;
    const fn=buildFunction(spec.expression??'x');
    const xmin=spec.x_min??-5,xmax=spec.x_max??5,ymin=spec.y_min??-2,ymax=spec.y_max??5;
    const pad=(xmax-xmin)*.07;
    const board=JXG.JSXGraph.initBoard(host.current.id,{boundingbox:[xmin-pad,ymax,xmax+pad,ymin],axis:true,showCopyright:true,showNavigation:true,keepaspectratio:false,resize:{enabled:true,throttle:100}});
    dispose=()=>JXG.JSXGraph.freeBoard(board);
    board.create('functiongraph',[fn,xmin,xmax],{strokeColor:'#5c56a6',strokeWidth:2.5});
    if(spec.tool==='draw_riemann_sum'){
     if(typeof spec.a!=='number'||typeof spec.b!=='number')throw new Error('缺少积分区间，请重新绘图');
     const bars=board.create('riemannsum',[fn,count,sampling,spec.a,spec.b],{fillColor:'#8cbca1',fillOpacity:.45,strokeColor:'#699680',strokeWidth:1});
     const value=bars.Value();setSum(Number.isFinite(value)?value:null);
    }
   }
   if(!stopped)setLoading(false);
  }catch{dispose?.();dispose=undefined;if(!stopped){setError('这张图暂时未能渲染，文字讲解仍可阅读。可请老师简化表达式或重新绘图。');setLoading(false);}}})();
  return()=>{stopped=true;dispose?.();};
 },[spec.id,count,sampling,unique]);
 return <figure className="teaching-drawing" aria-label={spec.title}><figcaption><strong>{spec.title}</strong><span>{spec.engine} · 开源绘图</span></figcaption>{spec.expression&&<code className="drawing-expression">f(x) = {spec.expression}</code>}{spec.tool==='draw_riemann_sum'&&<div className="drawing-controls"><label>矩形数 {count}<input aria-label="矩形数量" type="range" min="2" max="200" value={count} onChange={e=>setCount(Number(e.target.value))}/></label><label>取样<select aria-label="矩形取样方式" value={sampling} onChange={e=>setSampling(e.target.value)}><option value="left">左端点</option><option value="right">右端点</option><option value="middle">中点</option></select></label><output aria-live="polite">面积和：{sum===null?'—':Number(sum.toPrecision(7))}</output></div>}{loading&&<p role="status" className="drawing-status">正在加载绘图工具…</p>}{error&&<p className="drawing-error" role="alert">{error}</p>}{spec.tool==='draw_mindmap'?<Suspense fallback={<p role="status">正在加载思维导图…</p>}><TeachingMindmap markdown={spec.markdown??''} title={spec.title}/></Suspense>:spec.tool==='draw_diagram'?image&&<div className="diagram-image"><img src={image} alt={spec.title}/></div>:<div ref={host} id={unique} className="jsxgraph-host" style={{display:error?'none':'block'}}/>}<p className="drawing-caption">{spec.caption}</p><details><summary>查看绘图工具参数</summary><pre>{JSON.stringify({tool:spec.tool,...Object.fromEntries(Object.entries(spec).filter(([key])=>!['id','status','engine','tool'].includes(key)))},null,2)}</pre></details></figure>;
}
