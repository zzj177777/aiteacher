import {useEffect,useRef,useState,type MutableRefObject} from 'react';
import type {Live2DModel,Cubism4InternalModel} from 'pixi-live2d-display/cubism4';

export type DigitalCharacter={id:string;name:string;mode:'live2d'|'portrait';available:boolean;description:string;model_url?:string;portrait_url?:string;mouth_parameter?:string;note?:string;credit:string;source_url:string};
export const defaultCharacter:DigitalCharacter={id:'mao',name:'Mao',mode:'live2d',available:true,description:'魔法少女 · 动态形象',model_url:'/digital-assets/characters/mao/mao_pro.model3.json',mouth_parameter:'ParamA',credit:'Sample model © Live2D Inc.',source_url:'https://www.live2d.com/en/learn/sample/'};

let coreLoading:Promise<void>|undefined;
function loadCore(){
 if((window as unknown as {Live2DCubismCore?:unknown}).Live2DCubismCore)return Promise.resolve();
 if(!coreLoading)coreLoading=new Promise<void>((resolve,reject)=>{
  const script=document.createElement('script');script.src='/digital-assets/core.js';
  script.onload=()=>resolve();script.onerror=()=>{script.remove();coreLoading=undefined;reject(new Error('角色运行库未能加载'));};
  document.head.appendChild(script);
 });
 return coreLoading;
}

export default function DigitalAvatar({mouth,speaking,character=defaultCharacter}:{mouth:MutableRefObject<number>;speaking:boolean;character?:DigitalCharacter}){
 const host=useRef<HTMLDivElement>(null);const [error,setError]=useState('');const [ready,setReady]=useState(false);const [attempt,setAttempt]=useState(0);
 useEffect(()=>{
  let alive=true;let dispose:undefined|(()=>void);setError('');setReady(false);
  if(character.mode==='portrait')return()=>{alive=false;};
  (async()=>{try{
   await loadCore();
   const [PIXI,{Live2DModel}]=await Promise.all([import('pixi.js'),import('pixi-live2d-display/cubism4')]);
   if(!alive||!host.current)return;
   Live2DModel.registerTicker(PIXI.Ticker);
   const container=host.current;
   const app=new PIXI.Application({width:container.clientWidth,height:container.clientHeight,backgroundAlpha:0,antialias:true,autoDensity:true,resolution:Math.min(devicePixelRatio,2)});
   container.appendChild(app.view as HTMLCanvasElement);
   let model:Live2DModel<Cubism4InternalModel>|undefined;let observer:ResizeObserver|undefined;
   dispose=()=>{observer?.disconnect();app.destroy(true,{children:true,texture:true,baseTexture:true});};
   if(!character.model_url)throw new Error('角色缺少运行模型');
   model=await Live2DModel.from(character.model_url,{autoInteract:true}) as Live2DModel<Cubism4InternalModel>;
   if(!alive){model.destroy();return;}
   app.stage.addChild(model);model.anchor.set(.5,1);
   const width=model.width,height=model.height;
   const fit=()=>{
    const w=container.clientWidth,h=container.clientHeight;
    app.renderer.resize(w,h);model!.scale.set(Math.min(w/width,h/height)*.96);model!.position.set(w*.5,h*.99);
   };
   model.internalModel.on('beforeModelUpdate',()=>{model!.internalModel.coreModel.setParameterValueById(character.mouth_parameter||(character.id==='mao'?'ParamA':'ParamMouthOpenY'),mouth.current);});
   observer=new ResizeObserver(fit);observer.observe(container);fit();setReady(true);
  }catch(e){dispose?.();dispose=undefined;if(alive)setError((e as Error).message||'角色未能加载');}})();
  return()=>{alive=false;dispose?.();};
 },[attempt,mouth,character.id,character.model_url,character.mode,character.mouth_parameter]);
 return <div className={`digital-avatar ${speaking?'is-speaking':''} ${character.mode==='portrait'?'portrait-mode':''}`}>
  <div className="digital-avatar-stars"/>{character.mode==='portrait'?<img key={`${character.id}-${attempt}`} className="digital-avatar-portrait" src={character.portrait_url} alt="Hiyori 趴桌造型（静态形象）" onLoad={()=>setReady(true)} onError={()=>setError('图片未能加载')}/>:<div ref={host} className="digital-avatar-canvas" aria-label={`${character.name} 动漫老师`} data-ready={ready}/>}
  {!ready&&!error&&<p className="digital-avatar-notice" role="status">老师正在来到教室…</p>}
  {error&&<div className="digital-avatar-notice" role="alert"><strong>角色暂时没有加载成功</strong><p>你仍然可以看板书、听讲解。</p><button onClick={()=>setAttempt(v=>v+1)}>重新加载角色</button></div>}
  <div className="digital-teacher-name"><span className={speaking?'speaking-dot':''}/><div><strong>{character.name}</strong><small>{speaking?'正在为你讲解':character.mode==='portrait'?'静态形象 · 语音授课':'你的动漫学习伙伴'}</small></div><span className="digital-live-badge">{character.mode==='portrait'?'静态形象':'LIVE 2D'}</span></div>
 </div>;
}
