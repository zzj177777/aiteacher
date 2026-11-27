export default function BoardHelp({quote,question,busy,error,onQuote,onQuestion,onClose,onSubmit}:{quote:string;question:string;busy:boolean;error:string;onQuote:(value:string)=>void;onQuestion:(value:string)=>void;onClose:()=>void;onSubmit:()=>void}){
 return <aside className="board-help-panel" aria-label="说明哪里没懂"><header><strong>哪里没懂？我们单独补一下。</strong><button disabled={busy} onClick={onClose}>收起，先选原文 ×</button></header><p>可以在上方白板选中词句，也可以直接写下困惑；两项填一项就能补讲。</p>
  {quote&&<blockquote><span>你指出的地方</span><div>{quote}</div><button disabled={busy} onClick={()=>onQuote('')}>清除选中文字</button></blockquote>}
  <label>你的困惑<textarea aria-label="说明具体困惑" rows={2} maxLength={1500} value={question} disabled={busy} onChange={e=>onQuestion(e.target.value)} placeholder="比如：这个条件为什么必须成立？是哪一步推出来的？"/></label>
  {error&&<p role="alert" className="board-help-error">{error}</p>}
  <footer><span>主线位置会保留，补讲结束再回来。</span><button disabled={busy||(!quote.trim()&&!question.trim())} onClick={onSubmit}>{busy?'正在安排补讲…':'开一块白板讲清楚'}</button></footer>
 </aside>;
}
