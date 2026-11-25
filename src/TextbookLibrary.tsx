import {useEffect,useState} from 'react';
import {ArrowLeft,ArrowUpRight,BookOpen,ExternalLink,LibraryBig,Search} from 'lucide-react';
import './textbook-library.css';

type LocalEdition={edition_id:string;label:string;format:string;page_count:number;bytes:number;read_url:string;download_url:string;source_url:string};
type Book={id:string;semester_id:string;title:string;grade:number;grade_label:string;term:number;volume:string;subject:string;publisher:string;series:string;edition:string;reader_url:string;source_url:string;full_text_available:boolean;toc_available:boolean;historical_references:{label:string;reader_url:string;source_url:string}[];local_editions?:LocalEdition[]};
type Catalog={books:Book[];total:number;local_book_count?:number;verified_at:string;source:{name:string;url:string};scope:string};
const gradeNames=['一年级','二年级','三年级','四年级','五年级','六年级'];

export default function TextbookLibrary({semesterId,onBack,backLabel}:{semesterId:string|null;onBack:()=>void;backLabel:string}){
 const initial=/^primary-math-g([1-6])-t([12])$/.exec(semesterId||'');
 const [grade,setGrade]=useState(initial?.[1]||''),[term,setTerm]=useState(initial?.[2]||''),[query,setQuery]=useState('');
 const [catalog,setCatalog]=useState<Catalog|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setError('');setCatalog(null);
  fetch('/api/materials',{signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error('教材资料暂时无法读取，请重试。');return response.json() as Promise<Catalog>;}).then(setCatalog).catch(e=>{if(!controller.signal.aborted)setError((e as Error).message);});
  return()=>controller.abort();
 },[retry]);
 const text=query.trim().toLocaleLowerCase();
 const books=(catalog?.books||[]).filter(book=>(!grade||book.grade===Number(grade))&&(!term||book.term===Number(term))&&(!text||[book.title,book.grade_label,book.volume,book.series,book.publisher].join(' ').toLocaleLowerCase().includes(text)));
 return <main className="textbook-library">
  <header className="textbook-header"><div><span className="textbook-logo"><LibraryBig size={23}/></span><strong>教材资料库</strong><small>小学数学 · 人教版</small></div><button onClick={onBack}><ArrowLeft size={16}/>{backLabel}</button></header>
  <section className="textbook-hero"><div><span className="textbook-eyebrow">TEXTBOOK LIBRARY</span><h1>课本有出处，<br/><em>学习有参照。</em></h1><p>一至六年级 · 上下册 · 官方来源</p></div><div className="textbook-hero-note"><BookOpen size={28}/><strong>{catalog?.local_book_count?`${catalog.local_book_count} 册已有本地教材`:'收藏可靠的课本'}</strong><p>本地存档可直接阅读和下载 PDF。<br/>历史教材与当前目录分开标记。</p></div></section>
  <section className="textbook-content" aria-label="教材检索">
   <div className="textbook-filters"><label className="textbook-search"><Search size={18}/><input aria-label="搜索教材名称" placeholder="搜索名称、年级或出版社" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>年级<select aria-label="筛选年级" value={grade} onChange={e=>setGrade(e.target.value)}><option value="">全部年级</option>{gradeNames.map((name,i)=><option value={i+1} key={name}>{name}</option>)}</select></label><label>册次<select aria-label="筛选册次" value={term} onChange={e=>setTerm(e.target.value)}><option value="">上下册</option><option value="1">上册</option><option value="2">下册</option></select></label><button className="textbook-reset" onClick={()=>{setGrade('');setTerm('');setQuery('');}}>查看全部</button></div>
   {error?<div className="textbook-empty" role="alert"><p>{error}</p><button onClick={()=>setRetry(value=>value+1)}>重新加载</button></div>:!catalog?<p className="textbook-empty" role="status">正在读取教材索引…</p>:<>
    <div className="textbook-results"><h2>教材索引 <span>{books.length} 册</span></h2><small>共 {catalog.total} 册 · 核验于 {catalog.verified_at}</small></div>
    <div className="textbook-grid">{books.map(book=><article className="textbook-card" key={book.id} data-material-id={book.id}>
     <div className={`textbook-cover textbook-cover-${book.term}`} aria-hidden="true"><small>{book.series} · 小学</small><BookOpen size={32} strokeWidth={1.2}/><strong>数学</strong><span>{book.grade_label} · {book.volume}</span></div>
     <div className="textbook-card-body"><div className="textbook-card-tags"><span>官方目录收录</span><span>{book.local_editions?.length?'有本地历史教材':'仅资料索引'}</span></div><h3>{book.grade_label}数学 · {book.volume}</h3><p className="textbook-official-title">{book.title}</p><dl><div><dt>出版社</dt><dd>{book.publisher}</dd></div><div><dt>当前版次</dt><dd>{book.edition}</dd></div><div><dt>系统内资料</dt><dd>{book.local_editions?.length?'历史教材已保存；文字待提取':'未下载教材文件'}</dd></div></dl>
      {book.local_editions?.map(edition=><section className="textbook-local" aria-label="本地教材存档" key={edition.edition_id}><strong>本地教材 · 历史参考</strong><p>{edition.label}<br/>{edition.page_count} 页 · {(edition.bytes/1024/1024).toFixed(1)} MB · {edition.format==='image_pdf'?'图片版 PDF':'PDF'}</p><div><a className="textbook-local-read" href={edition.read_url} target="_blank" rel="noopener noreferrer">本地阅读<ArrowUpRight size={14}/></a><a href={edition.download_url} download>下载 PDF<ArrowUpRight size={13}/></a></div><small>这是历史存档，可能与当前课本不同。<a href={edition.source_url} target="_blank" rel="noopener noreferrer">查看来源</a></small></section>)}
      <div className="textbook-card-links"><a className="textbook-read" href={book.reader_url} target="_blank" rel="noopener noreferrer">官方在线阅读<ArrowUpRight size={16}/></a><a href={book.source_url} target="_blank" rel="noopener noreferrer">官方教材平台<ExternalLink size={13}/></a></div>
      {book.historical_references.length>0&&<details className="textbook-history"><summary>历史参考来源</summary>{book.historical_references.map(ref=><div key={ref.reader_url}><a href={ref.reader_url} target="_blank" rel="noopener noreferrer">{ref.label}<ExternalLink size={12}/></a><a href={ref.source_url} target="_blank" rel="noopener noreferrer">查看专题来源</a></div>)}</details>}
     </div>
    </article>)}</div>
    {!books.length&&<div className="textbook-empty"><BookOpen size={28}/><h3>没有找到匹配的教材</h3><p>试试更换年级，或清空搜索条件。</p></div>}
    <footer className="textbook-source"><a href={catalog.source.url} target="_blank" rel="noopener noreferrer">目录来源：{catalog.source.name}<ExternalLink size={13}/></a><p>本地教材按来源版本独立保存，含官方历史专题与公开镜像存档。具体版次请以课本版权页为准。</p><p>当前搜索范围为教材名称等索引信息；PDF 尚未进行正文检索入库，AI 暂不能检索其正文。</p></footer>
   </>}
  </section>
 </main>;
}
