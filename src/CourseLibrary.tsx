import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ArrowRight,BookOpen,Check,Clock3,FolderOpen,GraduationCap,Layers3,Plus,X} from 'lucide-react';
import ChatApp,{type Credential,type CourseContext,type SchoolContext} from './ChatApp';
import './course-library.css';
import CourseRoadmap,{type CourseRoadmapData,type RoadmapSection} from './CourseRoadmap';
import PrimaryMathCatalog,{primaryMathSemesters} from './PrimaryMathCatalog';
import TextbookLibrary from './TextbookLibrary';
import SchoolCatalog,{SchoolCourseEntry} from './SchoolCatalog';
import {restoreSchoolPath,schoolStages,type SchoolPath,type StageId} from './schoolCatalogData';

type Lesson={id:string;course_id:string|null;section_id?:string|null;school_context?:SchoolContext|null;title:string;created_at:string;last_activity:string;completed:boolean;working:boolean;has_started:boolean;confirmed_nodes:number;total_nodes:number;current_node:string};
type Course=CourseContext&{created_at:string;updated_at:string;session_count:number;ended_count:number;section_count?:number;confirmed_sections?:number;last_activity:string;latest_session:Lesson|null};
type Library={courses:Course[];unassigned_sessions:Lesson[]};
type Access={library_id:string;token:string};
type Classroom={key:string;credential?:Credential;course:CourseContext|null;school?:SchoolContext;returnSchool?:SchoolPath};
type Navigation={view:'library'|'course'|'classroom'|'new'|'primary'|'primary-semester'|'materials'|'school';course_id?:string;session_id?:string;semester_id?:string;return_view?:'library'|'primary'|'school';stage_id?:StageId;subject_id?:string;grade_id?:string;term?:1|2};
const libraryKey='aiteacher.learning.library.v1',navigationKey='aiteacher.learning.navigation.v1',sessionsKey='aiteacher.chat.sessions.v1';

async function request(path:string,token?:string,body?:unknown,method=body===undefined?'GET':'POST'){
 const response=await fetch(path,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'暂时无法完成操作，请重试。');
 return data;
}

let initializing:Promise<{access:Access;rejected:number}>|null=null;
function initialize(){
 if(!initializing)initializing=(async()=>{
  const saved=JSON.parse(localStorage.getItem(libraryKey)||'null');
  let access:Access;
  if(saved&&typeof saved.library_id==='string'&&typeof saved.token==='string')access=saved;
  else{access=await request('/api/learning-library',undefined,{});localStorage.setItem(libraryKey,JSON.stringify(access));}
  let old:unknown=[];try{old=JSON.parse(localStorage.getItem(sessionsKey)||'[]');}catch{/* Preserve malformed legacy storage without blocking the library. */}
  const sessions=Array.isArray(old)?old.filter((item):item is Credential=>item&&typeof item.session_id==='string'&&typeof item.token==='string').map(item=>({session_id:item.session_id,token:item.token,title:typeof item.title==='string'?item.title.slice(0,200):''})):[];
  let rejected=0;
  for(let at=0;at<sessions.length;at+=200){const result=await request('/api/learning-library/import',access.token,{sessions:sessions.slice(at,at+200)});rejected+=result.rejected.length;}
  return {access,rejected};
 })().catch(error=>{initializing=null;throw error;});
 return initializing;
}

function date(value:string){return new Date(value).toLocaleDateString('zh-CN',{month:'long',day:'numeric'});}
function remember(value:Navigation){try{localStorage.setItem(navigationKey,JSON.stringify(value));}catch{/* Navigation is optional; access credentials were already persisted. */}}

function CourseDialog({course,onClose,onSave}:{course:Course|null;onClose:()=>void;onSave:(title:string,description:string)=>Promise<void>}){
 const dialog=useRef<HTMLDialogElement>(null),[title,setTitle]=useState(course?.title||''),[description,setDescription]=useState(course?.description||''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 async function submit(event:FormEvent){event.preventDefault();if(busy)return;if(!title.trim()){setError('给这门课程起个名字吧。');return;}setBusy(true);setError('');try{await onSave(title.trim(),description.trim());}catch(e){setError((e as Error).message);setBusy(false);}}
 return <dialog ref={dialog} className="course-dialog" aria-labelledby="course-dialog-title" onCancel={event=>{event.preventDefault();if(!busy)onClose();}}>
  <form onSubmit={submit}><div className="course-dialog-heading"><span className="course-dialog-icon"><BookOpen size={24}/></span><button type="button" className="course-icon-button" aria-label="关闭课程表单" disabled={busy} onClick={onClose}><X size={20}/></button></div>
   <span className="course-eyebrow">留一个位置，慢慢学</span><h2 id="course-dialog-title">{course?'编辑课程':'新建一门长期课程'}</h2><p>把每次学的小知识，放进同一个学习空间。</p>
   <label>课程名称<input autoFocus maxLength={80} value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：初二数学" disabled={busy}/></label>
   <label>课程说明 <small>选填</small><textarea maxLength={400} rows={3} value={description} onChange={e=>setDescription(e.target.value)} placeholder="例如：跟上学校进度，逐步补齐基础。" disabled={busy}/></label>
   {error&&<p role="alert" className="course-error">{error}</p>}<button className="course-primary" disabled={busy} type="submit">{busy?'正在保存…':course?'保存修改':'创建课程'}<ArrowRight size={17}/></button>
  </form>
 </dialog>;
}

export default function CourseLibrary(){
 const [access,setAccess]=useState<Access|null>(null),[data,setData]=useState<Library|null>(null),[selected,setSelected]=useState<string|null>(null),[detail,setDetail]=useState<{course:Course;sessions:Lesson[];curriculum:CourseRoadmapData}|null>(null);
 const [openingSection,setOpeningSection]=useState('');
 const [primaryOpen,setPrimaryOpen]=useState(false),[primarySemester,setPrimarySemester]=useState<string|null>(null);
 const [materials,setMaterials]=useState<{semesterId:string|null;fromPrimary:boolean}|null>(null);
 const [schoolStage,setSchoolStage]=useState<StageId>('primary'),[schoolPath,setSchoolPath]=useState<SchoolPath|null>(null);
 const [schoolStarting,setSchoolStarting]=useState(false),[schoolStartError,setSchoolStartError]=useState('');
 const schoolStartLock=useRef(false);
 const [classroom,setClassroom]=useState<Classroom|null>(null),[dialog,setDialog]=useState<{course:Course|null}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0),[moving,setMoving]=useState(''),[rejected,setRejected]=useState(0);
 const navigationLoaded=useRef(false);
 const acceptRoadmap=useCallback((cid:string,roadmap:CourseRoadmapData)=>setDetail(old=>!old||old.course.id!==cid||old.curriculum===roadmap?old:{...old,curriculum:roadmap,course:{...old.course,section_count:roadmap.sections.length,confirmed_sections:roadmap.confirmed_sections}}),[]);
 useEffect(()=>{let alive=true;setLoading(true);setError('');(async()=>{
  try{
   const result=await initialize(),items=await request('/api/learning-library',result.access.token) as Library;
   if(!alive)return;setAccess(result.access);setRejected(result.rejected);setData(items);
   if(!navigationLoaded.current){navigationLoaded.current=true;let nav:Navigation|null=null;try{nav=JSON.parse(localStorage.getItem(navigationKey)||'null');}catch{/* Use the library home. */}
    const course=items.courses.find(item=>item.id===nav?.course_id)||null;
    if(schoolStages.some(item=>item.id===nav?.stage_id))setSchoolStage(nav!.stage_id!);
    if(course)setSelected(course.id);
    if(nav?.view==='classroom'&&typeof nav.session_id==='string')setClassroom({key:nav.session_id,credential:{session_id:nav.session_id,token:result.access.token,title:'学习小课'},course,returnSchool:nav.return_view==='school'?restoreSchoolPath(nav)||undefined:undefined});
    else if(nav?.view==='new')setClassroom({key:crypto.randomUUID(),course});
    else if(nav?.view==='primary'||nav?.view==='primary-semester'){setPrimaryOpen(true);setPrimarySemester(primaryMathSemesters.some(item=>item.id===nav?.semester_id)?nav!.semester_id!:null);}
    else if(nav?.view==='materials'){const semesterId=primaryMathSemesters.some(item=>item.id===nav?.semester_id)?nav!.semester_id!:null;setPrimarySemester(semesterId);setPrimaryOpen(nav.return_view==='primary');setMaterials({semesterId,fromPrimary:nav.return_view==='primary'});}
    else if(nav?.view==='school')setSchoolPath(restoreSchoolPath(nav));
   }
  }catch(e){if(alive)setError((e as Error).message);}finally{if(alive)setLoading(false);}
 })();return()=>{alive=false;};},[refresh]);
 useEffect(()=>{if(!access||!selected){setDetail(null);return;}let alive=true;setDetail(null);request(`/api/courses/${selected}`,access.token).then(result=>{if(alive)setDetail(result);}).catch(e=>{if(alive)setError((e as Error).message);});return()=>{alive=false;};},[access?.token,selected,refresh]);

 function openCourse(course:Course){setSelected(course.id);setError('');remember({view:'course',course_id:course.id});window.scrollTo(0,0);}
 function home(){setSchoolPath(null);setMaterials(null);setPrimaryOpen(false);setPrimarySemester(null);setClassroom(null);setSelected(null);setError('');remember({view:'library',stage_id:schoolStage});setRefresh(value=>value+1);window.scrollTo(0,0);}
 function chooseSchoolStage(stage:StageId){setSchoolStage(stage);remember({view:'library',stage_id:stage});}
 function openSchool(path:SchoolPath){setSchoolStartError('');setSchoolStage(path.stage);setSchoolPath(path);remember({view:'school',stage_id:path.stage,subject_id:path.subject,grade_id:path.grade,term:path.term});window.scrollTo(0,0);}
 function rememberClassroom(sid:string,courseId?:string,returnSchool?:SchoolPath){remember({view:'classroom',session_id:sid,course_id:courseId,...(returnSchool?{return_view:'school' as const,stage_id:returnSchool.stage,subject_id:returnSchool.subject}:{} )});}
 async function startSchoolLesson(){if(!access||!schoolPath||schoolStartLock.current)return;schoolStartLock.current=true;setSchoolStarting(true);setSchoolStartError('');const returnSchool={stage:schoolPath.stage,subject:schoolPath.subject};try{const result=await request('/api/sessions',access.token,{mode:'chat',school_context:{stage_id:returnSchool.stage,subject_id:returnSchool.subject}});setClassroom({key:result.session_id,credential:{session_id:result.session_id,token:access.token,title:'自由小课'},course:null,school:result.snapshot.school_context,returnSchool});rememberClassroom(result.session_id,undefined,returnSchool);window.scrollTo(0,0);}catch(e){setSchoolStartError((e as Error).message);}finally{schoolStartLock.current=false;setSchoolStarting(false);}}
 function openPrimary(id?:string){setPrimaryOpen(true);setPrimarySemester(id||null);remember(id?{view:'primary-semester',semester_id:id}:{view:'primary'});window.scrollTo(0,0);}
 function openMaterials(semesterId:string|null=null,fromPrimary=false){setMaterials({semesterId,fromPrimary});remember({view:'materials',semester_id:semesterId||undefined,return_view:fromPrimary?'primary':'library'});window.scrollTo(0,0);}
 function closeMaterials(){const previous=materials;setMaterials(null);if(previous?.fromPrimary)openPrimary(previous.semesterId||undefined);else home();}
 function openLesson(lesson:Lesson,course:CourseContext|null,returnSchool?:SchoolPath){if(!access)return;setClassroom({key:lesson.id,credential:{session_id:lesson.id,token:access.token,title:lesson.title},course,school:lesson.school_context||undefined,returnSchool});rememberClassroom(lesson.id,course?.id,returnSchool);window.scrollTo(0,0);}
 function newLesson(course:CourseContext|null){setClassroom({key:crypto.randomUUID(),course});remember({view:'new',course_id:course?.id});window.scrollTo(0,0);}
 function leaveClassroom(){const returnSchool=classroom?.returnSchool;setClassroom(null);setError('');if(returnSchool){setSelected(null);openSchool(returnSchool);}else remember(selected?{view:'course',course_id:selected}:{view:'library'});setRefresh(value=>value+1);window.scrollTo(0,0);}
 async function saveCourse(title:string,description:string){if(!access)return;const saved=await request(dialog?.course?`/api/courses/${dialog.course.id}`:'/api/courses',access.token,{title,description},dialog?.course?'PATCH':'POST');setDialog(null);setSelected(saved.id);remember({view:'course',course_id:saved.id});setRefresh(value=>value+1);}
 async function moveLesson(id:string,cid:string){if(!access||moving)return;setMoving(id);setError('');try{await request(`/api/learning-library/sessions/${id}`,access.token,{course_id:cid||null},'PATCH');setRefresh(value=>value+1);}catch(e){setError((e as Error).message);}finally{setMoving('');}}
 async function openSection(section:RoadmapSection){if(!access||!detail||openingSection)return;setOpeningSection(section.id);setError('');try{const result=await request(`/api/courses/${detail.course.id}/sections/${section.id}/open`,access.token,{});setClassroom({key:result.session_id,credential:{session_id:result.session_id,token:access.token,title:section.title},course:detail.course});remember({view:'classroom',session_id:result.session_id,course_id:detail.course.id});window.scrollTo(0,0);}catch(e){setError((e as Error).message);}finally{setOpeningSection('');}}

 if(classroom&&access)return <ChatApp key={classroom.key} initialSession={classroom.credential} course={classroom.course} school={classroom.school} libraryToken={access.token} onLibrary={leaveClassroom} libraryLabel={classroom.returnSchool?'返回科目':'课程管理'} onSessionCreated={credential=>rememberClassroom(credential.session_id,classroom.course?.id,classroom.returnSchool)}/>;
 if(materials)return <TextbookLibrary semesterId={materials.semesterId} onBack={closeMaterials} backLabel={materials.fromPrimary?(materials.semesterId?'返回课本入口':'返回年级列表'):'返回课程中心'}/>;
 if(primaryOpen)return <PrimaryMathCatalog semesterId={primarySemester} onSelect={id=>openPrimary(id)} onBack={()=>openPrimary()} onHome={home} onMaterials={()=>openMaterials(primarySemester,true)}/>;
 if(schoolPath)return <SchoolCatalog path={schoolPath} onNavigate={openSchool} onHome={home} onStart={()=>void startSchoolLesson()} starting={schoolStarting||!access} startError={schoolStartError} lessons={(data?.unassigned_sessions||[]).filter(lesson=>lesson.school_context?.stage_id===schoolPath.stage&&lesson.school_context.subject_id===schoolPath.subject)} onResume={id=>{const lesson=data?.unassigned_sessions.find(item=>item.id===id);if(lesson)openLesson(lesson,null,{stage:schoolPath.stage,subject:schoolPath.subject});}}/>;
 const count=(data?.unassigned_sessions.length||0)+(data?.courses.reduce((sum,item)=>sum+item.session_count,0)||0);
 const current=detail?.course;
 function lessons(items:Lesson[],course:CourseContext|null){return <div className="lesson-card-grid">{items.map(lesson=><article className="lesson-card" key={lesson.id} data-session-id={lesson.id}>
  <button className="lesson-open" onClick={()=>openLesson(lesson,course)}><div className="lesson-card-top"><span className={`lesson-status${lesson.completed?' ended':''}`}>{lesson.working?'正在生成':lesson.completed?'已结束':lesson.has_started?'学习中':'待开始'}</span><span>{date(lesson.last_activity)}</span></div><h3>{lesson.title}</h3><p>{lesson.current_node?`上次学到：${lesson.current_node}`:lesson.completed?'对话与学习记录已保存，随时可以回看。':lesson.has_started?'学习记录已保存，从上次的对话继续。':'已经准备好，随时开始第一段对话。'}</p>{lesson.total_nodes>0&&<div className="lesson-progress"><span style={{width:`${lesson.confirmed_nodes/lesson.total_nodes*100}%`}}/></div>}<div className="lesson-card-bottom"><small>{lesson.total_nodes?`${lesson.confirmed_nodes} / ${lesson.total_nodes} 节点已确认理解`:'还没有生成学习计划'}</small><span>{lesson.completed?'查看记录':'继续学习'}<ArrowRight size={16}/></span></div></button>
  <label className="lesson-move"><FolderOpen size={14}/> 归入课程<select aria-label={`归类：${lesson.title}`} value={lesson.course_id||''} disabled={!!moving} onChange={e=>void moveLesson(lesson.id,e.target.value)}><option value="">未分类小课</option>{data?.courses.map(item=><option value={item.id} key={item.id}>{item.title}</option>)}</select>{moving===lesson.id&&<small>保存中…</small>}</label>
 </article>)}</div>;}
 return <main className="course-library">
  <header className="library-header"><button className="library-brand" onClick={home}><span><GraduationCap size={23}/></span><strong>AI 私教</strong><small>我的学习空间</small></button><div className="library-header-actions"><a className="digital-classroom-entry" href="/digital-classroom" target="_blank" rel="noopener noreferrer">✦ 数字人课堂 ↗</a>{selected&&<button className="course-secondary" onClick={home}><ArrowLeft size={15}/>全部课程</button>}{!selected&&<button className="school-materials-button" onClick={()=>openMaterials()}><BookOpen size={15}/>资料库</button>}<button className="course-primary" disabled={!access} onClick={()=>setDialog({course:null})}><Plus size={16}/>新建课程</button></div></header>
  {error&&<div className="course-error" role="alert">{error}<button onClick={()=>setRefresh(value=>value+1)}>重试</button></div>}
  {rejected>0&&<p className="library-notice">有 {rejected} 条旧会话的恢复凭据暂不可用，其余记录已整理；原浏览器记录已保留。</p>}
  {loading&&!data?<div className="library-loading" role="status">正在打开你的学习空间…</div>:selected?current?<>
   <section className="course-detail-hero"><div><span className="course-eyebrow"><BookOpen size={15}/>长期课程</span><h1>{current.title}</h1><p>{current.description||'从一个知识点开始，把一次次学习连起来。'}</p><div className="course-detail-meta"><span><Layers3 size={15}/>{current.section_count?`${current.section_count} 节规划`:`${current.session_count} 个小课`}</span><span><Check size={15}/>{current.section_count?`${current.confirmed_sections||0} 节已确认`:`${current.ended_count} 个已结束`}</span><button onClick={()=>setDialog({course:current})}>编辑课程信息</button></div></div><button className="course-primary" onClick={()=>newLesson(current)}><Plus size={17}/>在这门课程里学点新的</button></section>
   {access&&detail.curriculum&&<CourseRoadmap key={current.id} course={current} token={access.token} initial={detail.curriculum} onOpen={section=>void openSection(section)} opening={openingSection} onChange={acceptRoadmap}/>}
   <section className="library-section"><div className="library-section-heading"><div><h2>{detail.curriculum?.plan?'补充小课与历史记录':'这门课程的小课'}</h2><p>独立添加的小课保留在这里，不会替代上面的课程路线。</p></div><span>{detail.sessions.filter(item=>!item.section_id).length} 个</span></div>{detail.sessions.some(item=>!item.section_id)?lessons(detail.sessions.filter(item=>!item.section_id),current):detail.curriculum?.plan?<div className="library-empty compact"><p>按上方路线学习，也可以添加补充小课。</p></div>:<div className="library-empty"><span><BookOpen size={28}/></span><h3>第一堂小课，从这里开始</h3><p>比如，在「{current.title}」里学一次函数。<br/>学完后，下次还能回到这里继续。</p><button className="course-primary" onClick={()=>newLesson(current)}>开始第一个小课<ArrowRight size={16}/></button></div>}</section>
  </>:<div className="library-loading" role="status">正在读取课程…</div>:<>
   <SchoolCourseEntry stageId={schoolStage} onStage={chooseSchoolStage} onOpen={openSchool}/>
   <div className="school-personal-prompt"><div><strong>也可以，按自己的目标慢慢学。</strong><p>创建一门长期课程，把每次的小进步留在一起。</p></div><button className="course-primary" disabled={!access} onClick={()=>setDialog({course:null})}>创建我的课程<ArrowRight size={17}/></button></div>
   <section className="library-section"><div className="library-section-heading"><div><h2>我的课程 <small>{data?.courses.length||0}</small></h2><p>按科目、学期或长期目标，整理你的学习。</p></div><span>{count} 个小课已保存</span></div><div className="course-card-grid">{data?.courses.map((course,index)=><article className={`course-card course-tone-${index%3}`} key={course.id}><button className="course-card-main" onClick={()=>openCourse(course)}><div className="course-card-top"><span className="course-card-icon"><BookOpen size={23}/></span><span>{course.section_count?`${course.confirmed_sections||0} / ${course.section_count} 节已确认`:`${course.session_count} 个小课`}</span></div><h3>{course.title}</h3><p>{course.description||'给持续学习留一个位置。'}</p><div className="course-card-footer"><span>{course.latest_session?`最近：${course.latest_session.title}`:'还没有小课，开启第一步吧'}</span><ArrowRight size={18}/></div></button>{course.latest_session&&<button className="course-resume" onClick={()=>openLesson(course.latest_session!,course)}><Clock3 size={14}/>{course.latest_session.completed?'回看上次学习':'继续上次学习'}<span>{date(course.latest_session.last_activity)}</span></button>}</article>)}<button className="course-add-card" disabled={!access} onClick={()=>setDialog({course:null})}><span><Plus size={26}/></span><strong>新建一门课程</strong><small>例如：初二数学、线性代数、英语阅读</small></button></div></section>
   <section className="library-section"><div className="library-section-heading"><div><h2>未分类的小课 <small>{data?.unassigned_sessions.length||0}</small></h2><p>以前的学习记录在这里，也可以把它们归入课程。</p></div><button className="course-secondary" disabled={!access} onClick={()=>newLesson(null)}><Plus size={15}/>直接开始小课</button></div>{data?.unassigned_sessions.length?lessons(data.unassigned_sessions,null):<div className="library-empty compact"><p>还没有未分类的小课。你也可以先开始学习，再慢慢整理。</p></div>}</section>
  </>}
  <footer className="library-footer"><FolderOpen size={14}/><span>记录保存在本机服务，恢复入口保存在当前浏览器。节点进度表示确认理解，不等同于长期掌握。</span></footer>
  {dialog&&<CourseDialog course={dialog.course} onClose={()=>setDialog(null)} onSave={saveCourse}/>}
 </main>;
}
