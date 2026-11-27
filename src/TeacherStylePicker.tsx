import {useEffect,useRef,useState,type FormEvent} from 'react';
import {createPortal} from 'react-dom';
import {ensureTeacherStyleToken,teacherStyleHeaders,teacherStyleStorageKey} from './teacherStyleStorage';
import './teacher-style.css';

export type TeacherStyle={id:string;name:string;description:string;version:number;prompt_hash:string};
type Style=TeacherStyle&{prompt:string;source?:string};

export default function TeacherStylePicker({value,disabled,onChange}:{value?:TeacherStyle;disabled:boolean;onChange:(id:string)=>void}){
 const [styles,setStyles]=useState<Style[]>([]),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [open,setOpen]=useState(false),[saving,setSaving]=useState(false),[saveError,setSaveError]=useState('');
 const [name,setName]=useState(''),[approach,setApproach]=useState(''),[examples,setExamples]=useState('');
 const dialog=useRef<HTMLDialogElement>(null),nameInput=useRef<HTMLInputElement>(null),saveLock=useRef(false),catalogEpoch=useRef(0),eventKey=useRef('');
 useEffect(()=>{
  let alive=true;let abort:AbortController|undefined;
  async function load(){
   abort?.abort();const controller=new AbortController();abort=controller;const epoch=++catalogEpoch.current;
   try{const response=await fetch('/api/teacher-styles',{headers:teacherStyleHeaders(),signal:controller.signal});if(!response.ok)throw new Error();const data=await response.json();if(alive&&epoch===catalogEpoch.current){setStyles(data.styles);setError('');}}
   catch{if(alive&&!controller.signal.aborted&&epoch===catalogEpoch.current)setError('教学风格暂未加载，请刷新后重试。');}
  }
  const storage=(event:StorageEvent)=>{if(event.key===teacherStyleStorageKey)void load();};
  void load();window.addEventListener('focus',load);window.addEventListener('storage',storage);
  return()=>{alive=false;abort?.abort();window.removeEventListener('focus',load);window.removeEventListener('storage',storage);};
 },[]);
 useEffect(()=>{const modal=dialog.current;if(open&&!modal?.open){modal?.showModal();nameInput.current?.focus();}else if(!open&&modal?.open)modal.close();},[open]);
 const selected=styles.find(s=>s.id===(value?.id||'framework'));
 const missingCurrent=value&&!styles.some(s=>s.id===value.id);
 function edit(set:(text:string)=>void,text:string){set(text);eventKey.current='';setSaveError('');}
 async function save(event:FormEvent){
  event.preventDefault();if(saveLock.current||disabled)return;saveLock.current=true;setSaving(true);setSaveError('');
  try{
   ensureTeacherStyleToken();eventKey.current||=crypto.randomUUID();
   const response=await fetch('/api/teacher-styles',{method:'POST',headers:{'Content-Type':'application/json',...teacherStyleHeaders()},body:JSON.stringify({name:name.trim(),approach:approach.trim(),examples:examples.trim(),idempotency_key:eventKey.current})});
   const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'保存未完成，请检查填写内容后重试。');
   const style=data.style as Style;++catalogEpoch.current;setStyles(current=>[...current.filter(s=>s.id!==style.id),style]);setOpen(false);setName('');setApproach('');setExamples('');eventKey.current='';setNotice('已保存到我的老师，可在列表中重复使用。');onChange(style.id);
  }catch(e){setSaveError((e as Error).message);}finally{saveLock.current=false;setSaving(false);}
 }
 return <section className="teacher-style-picker" aria-label="老师教学风格"><label>教学风格<select aria-label="选择老师教学风格" value={value?.id||'framework'} disabled={disabled||!styles.length} onChange={e=>{setNotice('');onChange(e.target.value);}}>{styles.map(style=><option key={style.id} value={style.id}>{style.name}{style.source==='custom'?' · 自定义':''}</option>)}{missingCurrent&&<option value={value.id}>{value.name} · 本课已保存</option>}{!styles.length&&!missingCurrent&&<option value="framework">正在加载老师…</option>}</select></label>{selected&&<><p>{selected.description}</p><small>从下一次讲解或新补讲生效，当前板书保留。{disabled?' 当前暂不能切换。':''}</small><details><summary>查看这位老师的提示词 · v{selected.version}</summary><div><p>以下是追加到授课系统提示中的教学策略与示范。通用教学要求、课程范围和工具约束共同生效。</p><pre>{selected.prompt}</pre></div></details></>}{missingCurrent&&<small>本课保留了这位老师的配置，可继续教学。使用创建时的浏览器凭据可恢复完整风格列表。</small>}<button type="button" className="teacher-style-create" disabled={disabled} onClick={()=>{setSaveError('');setNotice('');setOpen(true);}}>＋ 创建我的老师</button>{notice&&<small role="status">{notice}</small>}{error&&<small role="alert">{error}</small>}
  {open&&createPortal(<dialog ref={dialog} className="teacher-style-dialog" aria-labelledby="custom-teacher-title" onClose={()=>setOpen(false)} onCancel={event=>{if(saving)event.preventDefault();}}><form onSubmit={save}><header><div><span>你的教法，你来定义</span><h2 id="custom-teacher-title">创建我的老师</h2></div><button type="button" aria-label="关闭创建老师弹窗" disabled={saving} onClick={()=>setOpen(false)}>×</button></header><p className="teacher-style-intro">写下你希望老师怎么讲，再给一个具体的教学示例。</p><label>老师名称<input ref={nameInput} required maxLength={80} value={name} disabled={saving} onChange={e=>edit(setName,e.target.value)} placeholder="例如：先抓重点的老师"/></label><label>教学思路<textarea required rows={4} maxLength={6000} value={approach} disabled={saving} onChange={e=>edit(setApproach,e.target.value)} placeholder="希望怎样开始、怎样解释？学生没懂时，老师应该怎么调整？"/></label><label>教学示例<textarea required rows={5} maxLength={10000} value={examples} disabled={saving} onChange={e=>edit(setExamples,e.target.value)} placeholder={'例如：\n学生：为什么移项要变号？\n老师：先看 x+3=8。为了让左边只剩 x，两边同时减去3……\n学生：我还是没懂。\n老师：我们换一个更小的例子……'}/></label><small className="teacher-style-storage-note">保存到本机服务，由当前浏览器保留恢复凭据；文字课堂与数字人课堂共用。</small>{saveError&&<p className="teacher-style-save-error" role="alert">{saveError}</p>}<footer><button type="button" disabled={saving} onClick={()=>setOpen(false)}>取消</button><button type="submit" className="teacher-style-save" disabled={disabled||saving||!name.trim()||!approach.trim()||!examples.trim()}>{saving?'正在保存…':'保存并使用'}</button></footer></form></dialog>,document.body)}
 </section>;
}
