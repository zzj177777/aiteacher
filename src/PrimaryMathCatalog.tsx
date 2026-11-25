import {ArrowLeft,ArrowRight,BookOpen,GraduationCap,Layers3,ListTree,Sparkles} from 'lucide-react';
import './primary-math.css';

const grades=['一年级','二年级','三年级','四年级','五年级','六年级'];
export const primaryMathSemesters=grades.flatMap((grade,index)=>([1,2] as const).map(term=>({
 id:`primary-math-g${index+1}-t${term}`,grade:index+1,gradeLabel:grade,term,volume:term===1?'上册':'下册',publisher:'人教版',subject:'数学',
})));

export function PrimaryMathEntry({onOpen}:{onOpen:()=>void}){
 return <button className="primary-entry" aria-label="进入小学数学板块" onClick={onOpen}>
  <span className="primary-entry-icon"><BookOpen size={28} strokeWidth={1.5}/></span>
  <span className="primary-entry-text"><small>课本同步 · 人教版</small><strong>小学数学</strong><span>一至六年级，上下册共 12 个学期入口</span></span>
  <span className="primary-entry-action">选年级，找课本<ArrowRight size={18}/></span>
 </button>;
}

export default function PrimaryMathCatalog({semesterId,onSelect,onBack,onHome,onMaterials}:{semesterId:string|null;onSelect:(id:string)=>void;onBack:()=>void;onHome:()=>void;onMaterials:()=>void}){
 const index=primaryMathSemesters.findIndex(item=>item.id===semesterId),semester=primaryMathSemesters[index];
 function select(id:string){onSelect(id);window.scrollTo(0,0);}
 return <main className="primary-catalog">
  <header className="primary-header"><button className="primary-brand" onClick={onHome} aria-label="返回课程中心"><span><GraduationCap size={23}/></span><strong>AI 私教</strong><small>小学学习板块</small></button><button className="primary-back" onClick={semester?onBack:onHome}><ArrowLeft size={15}/>{semester?'全部年级':'课程中心'}</button></header>
  {semester?<>
   <nav className="primary-breadcrumb" aria-label="课本导航"><button onClick={onBack}>小学数学</button><span>/</span><span>{semester.gradeLabel}{semester.volume}</span></nav>
   <section className={`primary-semester-hero primary-grade-tone-${(semester.grade-1)%3}`}>
    <div><span className="primary-eyebrow"><BookOpen size={14}/>{semester.publisher} · 小学数学</span><h1>{semester.gradeLabel}<span> · {semester.volume}</span></h1><p>跟着这一本课本，找到想补的那一课。</p><div className="primary-semester-tags"><span>数学</span><span>{semester.gradeLabel}</span><span>{semester.term===1?'第一学期':'第二学期'}</span></div></div>
    <div className="primary-large-book" aria-hidden="true"><small>小学数学</small><strong>数学</strong><span>{semester.grade}</span><p>{semester.gradeLabel} · {semester.volume}</p><i>{semester.publisher}</i></div>
   </section>
   <button className="materials-entry" onClick={onMaterials}><BookOpen size={20}/><span><strong>查看本学期教材资料</strong><small>本地阅读与下载 · 历史教材独立标记</small></span><ArrowRight size={18}/></button>
   <section className="primary-chapters" aria-label="教材章节入口"><div className="primary-section-heading"><div><h2>按课本章节找薄弱点</h2><p>这里将按教材目录，逐章进入对应的学习内容。</p></div><span>人教版</span></div>
    <div className="primary-chapter-empty"><span><ListTree size={30} strokeWidth={1.4}/></span><h3>章节目录待接入</h3><p>已为{semester.gradeLabel}{semester.volume}准备好入口。<br/>下一步核对课本章节，让你直接找到想补的内容。</p><button onClick={onBack}>换一本课本<ArrowRight size={15}/></button></div>
   </section>
   <nav className="primary-book-navigation" aria-label="切换课本">{index>0?<button aria-label={`上一册：${primaryMathSemesters[index-1].gradeLabel}${primaryMathSemesters[index-1].volume}`} onClick={()=>select(primaryMathSemesters[index-1].id)}><ArrowLeft size={16}/><span><small>上一册</small>{primaryMathSemesters[index-1].gradeLabel}{primaryMathSemesters[index-1].volume}</span></button>:<span/>}{index<primaryMathSemesters.length-1&&<button aria-label={`下一册：${primaryMathSemesters[index+1].gradeLabel}${primaryMathSemesters[index+1].volume}`} onClick={()=>select(primaryMathSemesters[index+1].id)}><span><small>下一册</small>{primaryMathSemesters[index+1].gradeLabel}{primaryMathSemesters[index+1].volume}</span><ArrowRight size={16}/></button>}</nav>
  </>:<>
   <section className="primary-hero"><div><span className="primary-eyebrow"><Sparkles size={14}/>课本在身边，学习有方向</span><h1>小学数学，<br/><em>从想补的那一课开始。</em></h1><p>先选年级，再选上下册。<br/>让每一次补习，都有清楚的起点。</p><div className="primary-hero-tags"><span>人教版</span><span>1—6 年级</span><span>12 册课本入口</span></div></div><div className="primary-hero-art" aria-hidden="true"><span className="primary-symbol symbol-plus">＋</span><span className="primary-symbol symbol-times">×</span><div className="primary-art-book"><small>一点点理解，一步步长大</small><BookOpen size={46} strokeWidth={1.2}/><strong>数 学</strong><span>每天，学明白一点</span></div><span className="primary-art-label">1 · 2 · 3 · 4 · 5 · 6</span></div></section>
   <section className="primary-grades" aria-label="小学数学年级学期"><div className="primary-section-heading"><div><span className="primary-eyebrow"><Layers3 size={14}/>按年级找课本</span><h2>你想补哪一学期？</h2></div><span>6 个年级 · 12 个学期</span></div>
    <nav className="primary-grade-shortcuts" aria-label="快速定位年级">{grades.map((grade,index)=><button key={grade} onClick={()=>document.getElementById(`primary-grade-${index+1}`)?.scrollIntoView({behavior:'smooth',block:'center'})}>{grade}</button>)}</nav>
    <div className="primary-grade-grid">{grades.map((grade,gradeIndex)=><article className={`primary-grade-card primary-grade-tone-${gradeIndex%3}`} id={`primary-grade-${gradeIndex+1}`} key={grade}><div className="primary-grade-heading"><span>{String(gradeIndex+1).padStart(2,'0')}</span><h3>{grade}</h3><small>人教版 · 数学</small></div><div className="primary-volume-grid">{primaryMathSemesters.filter(item=>item.grade===gradeIndex+1).map(item=><button key={item.id} className="primary-semester-card" data-semester-id={item.id} aria-label={`${item.gradeLabel}${item.volume}`} onClick={()=>select(item.id)}><span className="primary-mini-book" aria-hidden="true"><BookOpen size={23} strokeWidth={1.3}/><i>{item.term===1?'上':'下'}</i></span><strong>{item.volume}</strong><span>第{item.term===1?'一':'二'}学期<ArrowRight size={13}/></span></button>)}</div></article>)}</div>
   </section>
  </>}
  <footer className="primary-footer"><BookOpen size={14}/><span>已收录官方教材索引，课本章节目录将在核对教材后接入。</span><button className="primary-back" onClick={onMaterials}>教材资料库<ArrowRight size={14}/></button></footer>
 </main>;
}
