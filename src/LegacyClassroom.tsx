import React, { useEffect, useRef, useState } from 'react';
import katex from 'katex';
import { ArrowRight, BookOpen, Check, ChevronDown, CircleHelp, Clock3, Download, GraduationCap, Lightbulb, LoaderCircle, MessageCircle, Plus, RotateCcw, Send, ShieldCheck, Sparkles, X } from 'lucide-react';
import 'katex/dist/katex.min.css';
import './style.css';
import './teaching.css';
import './planning.css';

type Matrix = string[][];
type Step = { label: string; matrix: Matrix; factor: string };
type Attempt = { problem_id: string; title: string; answer: string; steps: Step[]; factor: string; independent: boolean; hints: number };
type TeachingSummary = {id:string; title:string; status:string; completed_points:string[]; checks:{segment_title:string; answer:string; correct:boolean}[]; open_questions:{id:string; text:string}[]; resolved_count:number};
type Report = { passed: boolean; attempts: Attempt[]; evidence: { concept: string; observation: string; problem_id: string }[]; mistakes: { kind: string; text: string }[]; diagnostic_score: number; notes: string[]; next: string; explanation: { correct: boolean; note: string; note_evaluated: boolean } | null; teaching_sessions?:TeachingSummary[] };
type TeachingCheck = { id: string; kind: string; prompt: string; choices?: string[] };
type TeachingTask = { id: string; title: string; topic: string; objective: string; outline: string[]; focus: string[]; constraints: string[]; status: string; reason: string; return_phase: string; segments: {title: string; passed: boolean}[]; segment: {index: number; total: number; title: string; objective: string; status: string; check: TeachingCheck | null}; session: {completed_points: string[]; checks: {segment_index: number; segment_title: string; prompt: string; answer: string; correct: boolean; attempt: number}[]; latest_check_result: {correct: boolean; answer: string} | null; open_questions: {id: string; text: string; segment_index: number; status: string}[]; resolved_questions: {id: string; text: string}[]; resume_point: {phase: string; problem_id: string | null; step_count: number}} };
type ChatEntry = { id: string; role: string; text: string; status?: string; agent?: string; kind?: string; to_agent?: string; task_id?: string };
type PlannerState = {enabled:boolean; status:string; capability_note:string; course_confirmed:boolean; profile:{goal:string; prior_knowledge:string; time_minutes:number|null; preference:string}; plan:{id:string; goal:string; course_id:string; executable:boolean; status:string; time_minutes:number; steps:{kind:string; objective:string}[]}|null; question:{text:string; options:string[]}|null; history:{id:string; trigger:string; tool:string; source:string; status:string; result_phase:string; arguments:{message:string; reason:string; [key:string]:unknown}; fallback_reason?:string}[]};
type Snapshot = { phase: string; revision: number; planner?:PlannerState|null; diagnostic_index: number; diagnostic?: { question: string; choices: string[] }; matrix: Matrix | null; factor: string; problem?: { id: string; title: string; original: Matrix; role: string }; messages: ChatEntry[]; teaching_task?: TeachingTask | null; paused_teaching_tasks?: {id:string; title:string; segment_index:number; segment_total:number}[]; steps: Step[]; helped: boolean; problem_done?: boolean; passed: string[]; completed: boolean; report: Report | null };
type Credential = { session_id: string; token: string };
type Envelope = { snapshot: Snapshot; teaching_mode: string; result?: Record<string, unknown> };

function MathText({ tex, display = false }: { tex: string; display?: boolean }) {
  return <span className={display ? 'math display' : 'math'} dangerouslySetInnerHTML={{ __html: katex.renderToString(tex, { throwOnError: false, displayMode: display, trust: false }) }} />;
}
function determinantTex(m: Matrix) { return `\\begin{vmatrix}${m.map(row => row.join(' & ')).join(' \\\\ ')}\\end{vmatrix}`; }
const phaseLabels: Record<string, string> = { planning:'教学安排 Agent 正在主持', diagnosis: '找到你的起点', lecture: '授课 Agent 正在讲授', guided_practice: '跟着思路练习', independent_assessment: '自己完成新题', rule_check: '理解背后的规则', rule_remedy: '再梳理一下规则', report: '留下学习的证据' };
const storageKey = 'aiteacher.session.v1';
const rules = [
  { name: '倍加不变', tex: 'R_i \\leftarrow R_i + kR_j', text: '把另一行的倍数加到一行，行列式的值不变。' },
  { name: '换行变号', tex: 'R_i \\leftrightarrow R_j', text: '每交换两行，行列式变号一次。' },
  { name: '对角线相乘', tex: 'D = c \\cdot a_{11}a_{22}a_{33}', text: '化为上三角形后，别忘了修正系数 c。' },
];

const identities: Record<string, { name: string; mark: string; source: string }> = {
  planner: {name:'教学安排 Agent',mark:'排',source:'DeepSeek'},
  scheduler: { name: '课堂调度器', mark: '调', source: '状态机' },
  lecturer: { name: '授课 Agent', mark: '授', source: '规则讲稿' },
  assessment: { name: '测评模块', mark: '评', source: '程序规则' },
  student: { name: '你', mark: '我', source: '' },
  legacy: { name: '历史课堂消息', mark: '序', source: '旧版记录' },
};
function ChatMessage({ item }: { item: ChatEntry }) {
  const agent = item.agent ?? (item.role === 'student' ? 'student' : 'legacy');
  const identity = identities[agent] ?? identities.legacy;
  const source = agent === 'lecturer' || agent === 'planner' ? item.status === 'ai' ? 'DeepSeek' : item.status === 'pending' ? '正在生成' : item.status === 'fallback' ? '规则回退' : item.status === 'receipt' ? '工具执行记录' : '规则内容' : identity.source;
  if (item.kind === 'handoff') return <div className={`handoff-card agent-${agent}`}><div className="handoff-title"><span className="agent-mini">{identity.mark}</span><strong>{identity.name}</strong><ArrowRight size={12} /><strong>{identities[item.to_agent ?? '']?.name ?? '课堂'}</strong><span className="agent-source">{source}</span></div><p>{item.text}</p>{item.task_id && <small>任务 {item.task_id.slice(0, 8)}</small>}</div>;
  return <div className={`chat-row agent-${agent} ${agent === 'student' ? 'student' : ''}`}>{agent !== 'student' && <div className="chat-icon">{identity.mark}</div>}<div className="chat-bubble">{agent !== 'student' && <div className="speaker-label"><strong>{identity.name}</strong><span>{source}</span>{item.kind === 'lecture' && <em>知识讲授</em>}</div>}<p>{item.text}</p>{item.status === 'pending' && <span className="message-status"><LoaderCircle size={12} className="spin" /> {agent === 'planner' ? '正在选择下一步工具，执行前由系统校验' : item.kind === 'lecture' ? '正在准备本次讲授，先显示规则讲稿' : '正在生成回答，先显示规则回复'}</span>}{item.status === 'fallback' && <span className="message-status">模型安排暂不可用 · 已使用规则回退</span>}</div></div>;
}

function PlanningPanel({planner,busy,send}:{planner:PlannerState; busy:boolean; send:(type:string,payload?:Record<string,unknown>)=>Promise<boolean>}) {
  const [input,setInput]=useState('');
  const pending=planner.status==='pending';
  const names:Record<string,string>={diagnostic:'课前诊断',teaching:'知识讲授',practice:'引导练习',assessment:'独立测评'};
  async function submit() { if(input.trim() && await send('planner_message',{text:input})) setInput(''); }
  return <div className="planning-panel"><div className="task-tag">教学安排 Agent · 目标与下一步</div><h2>先了解你，再安排学习。</h2><p className="planner-scope">{planner.capability_note}</p>{pending && <div className="planner-working"><LoaderCircle size={16} className="spin" /> 正在结合目标、学生选择与学习证据安排下一步…</div>}
    {planner.question && <div className="planner-question"><h3>{planner.question.text}</h3><div>{planner.question.options.map(option=><button className="secondary" key={option} disabled={busy||pending} onClick={()=>send('planner_message',{text:option,select_supported_course:option==='体验三阶行列式课堂'})}>{option}<ArrowRight size={14}/></button>)}</div></div>}
    {planner.plan && <div className="learning-plan"><div className="plan-top"><span>{planner.plan.status==='confirmed'?'已确认计划':'待确认计划'}</span><span>{planner.plan.time_minutes} 分钟 · {planner.plan.executable?'可执行课堂':'仅计划草案'}</span></div><h3>{planner.plan.goal}</h3><div className="learner-profile"><p><strong>基础自述</strong>{planner.profile.prior_knowledge}</p><p><strong>教学偏好</strong>{planner.profile.preference}</p><small>这些信息来自对话整理，不等同于已验证的掌握证据。</small></div><ol>{planner.plan.steps.map((step,i)=><li key={i}><span>{String(i+1).padStart(2,'0')}</span><div><strong>{names[step.kind]}</strong><p>{step.objective}</p></div></li>)}</ol>{planner.plan.status==='proposed' && <button className="primary" disabled={busy||pending||!planner.plan.executable} onClick={()=>send('confirm_learning_plan',{plan_id:planner.plan!.id})}>{planner.plan.executable?'确认计划，开始三阶行列式课堂':'该领域暂不支持执行'}<ArrowRight size={15}/></button>}{!planner.plan.executable&&<p className="unsupported-note">可以继续讨论和修改草案；当前尚未接入该领域的授课、题目验证和测评，不能直接启动。</p>}</div>}
    <form className="planning-input" onSubmit={e=>{e.preventDefault();submit();}}><label htmlFor="learning-request">告诉我目标、基础，或想调整的地方</label><textarea id="learning-request" aria-label="学习需求" value={input} onChange={e=>setInput(e.target.value)} maxLength={1500} rows={3} placeholder="例如：我想学三阶行列式，知道一些规则，但总是弄错换行后的符号。"/><button className="primary" disabled={busy||!input.trim()}>{pending?'更新这次需求':'交给教学安排 Agent'}<Send size={14}/></button></form>
    {(!planner.plan?.executable || planner.status==='awaiting_student')&&<button className="supported-course-button" disabled={busy||pending} onClick={()=>send('planner_message',{text:'我选择体验三阶行列式课堂，请安排一份学习计划。',select_supported_course:true})}>先体验可执行的三阶行列式课堂 <ArrowRight size={14}/></button>}
    {planner.history.length>0&&<details className="planning-history"><summary>查看调度与工具执行记录 <ChevronDown size={14}/></summary>{planner.history.slice().reverse().map(d=><div key={d.id}><strong>{d.tool}</strong><span>{d.source==='ai'?'DeepSeek 决策':'规则回退'} · 已执行</span><p>{d.arguments.reason}</p><small>结果：{phaseLabels[d.result_phase]??d.result_phase}</small><details><summary>结构化工具参数</summary><pre>{JSON.stringify({tool:d.tool,arguments:d.arguments},null,2)}</pre></details></div>)}</details>}
  </div>;
}

function LecturePanel({ task, busy, send }: {task: TeachingTask; busy: boolean; send: (type: string, payload?: Record<string, unknown>) => Promise<boolean>}) {
  const [answer, setAnswer] = useState('');
  const [choice, setChoice] = useState(-1);
  const segment = task.segment;
  const session = task.session;
  const check = segment.check;
  useEffect(() => { setAnswer(''); setChoice(-1); }, [check?.id, task.id]);
  const stageLabels: Record<string,string> = {generating:'正在准备本段', awaiting_check:'等待理解检查', passed:'本段检查通过', completed:'本轮随堂检查完成', needs_review:'当前要点待复习'};
  return <div className="lecture-overview segmented-lecture"><div className="task-tag">授课 Agent · 分段讲授</div><div className="segment-progress"><span>第 {segment.index+1} / {segment.total} 段</span><strong>{stageLabels[segment.status] ?? segment.status}</strong></div><h2>{segment.title}</h2><p className="lecture-objective">{segment.objective}</p><div className="segment-rail">{task.segments.map((s,i) => <span key={s.title} className={`${s.passed ? 'passed' : ''} ${i === segment.index ? 'active' : ''}`}><span>{s.passed ? <Check size={12} /> : i+1}</span>{s.title}</span>)}</div>
    <p className="muted">右侧对话每次只讲当前要点。先完成下面的随堂检查，再决定继续还是补讲。</p>
    {session.latest_check_result && <div className={`check-feedback ${session.latest_check_result.correct ? 'correct' : 'incorrect'}`}>{session.latest_check_result.correct ? '这次回答正确，可以继续。' : '这次回答尚未通过，先看补讲，再尝试不同的问题。'}<small>只记录随堂理解证据，不等同于独立掌握。</small></div>}
    {check && <form className="understanding-check" onSubmit={e => { e.preventDefault(); send('submit_teaching_check', {task_id:task.id, check_id:check.id, answer:check.kind === 'choice' ? choice : answer}); }}><div className="section-heading"><h3>理解检查</h3><span className="task-tag">{session.latest_check_result && !session.latest_check_result.correct ? '换一道题再确认' : '先用一个小问题确认'}</span></div><p className="check-prompt">{check.prompt}</p>{check.kind === 'choice' ? <fieldset disabled={busy || segment.status !== 'awaiting_check'}>{check.choices?.map((text,i) => <label key={i} className={choice === i ? 'selected' : ''}><input type="radio" name={`teaching-${check.id}`} checked={choice === i} onChange={() => setChoice(i)} />{text}</label>)}</fieldset> : <label className="numeric-check-label">你的答案<input aria-label="理解检查答案" value={answer} onChange={e => setAnswer(e.target.value)} maxLength={30} placeholder="整数、分数或小数" disabled={busy || segment.status !== 'awaiting_check'} /></label>}<button className="primary" disabled={busy || segment.status !== 'awaiting_check' || (check.kind === 'choice' ? choice < 0 : !answer.trim())}>{segment.status === 'generating' ? <><LoaderCircle className="spin" size={15} /> 正在准备本段</> : <>提交理解检查 <ArrowRight size={15} /></>}</button></form>}
    {segment.status === 'passed' && <button className="primary" disabled={busy} onClick={() => send('next_teaching_segment')}>继续下一个要点 <ArrowRight size={16} /></button>}
    {segment.status === 'completed' && <div className="segment-complete"><p>各段随堂检查已完成。接下来通过独立练习验证，不直接认定掌握。</p><button className="primary" disabled={busy} onClick={() => send('finish_lecture')}>交回调度器，进入练习 <ArrowRight size={16} /></button></div>}
    {segment.status === 'needs_review' && <div className="check-feedback incorrect">这一段的检查仍未通过，保留待复习记录。你可以继续提问，或暂存后回到练习，不会自动跳过此要点。</div>}
    {session.open_questions.length > 0 && <div className="open-questions"><h3>待解决的疑问 · {session.open_questions.length}</h3>{session.open_questions.map(q => <div key={q.id}><span>第{q.segment_index+1}段：{q.text}</span><small>{q.status === 'awaiting_answer' ? '等待回答' : q.status === 'needs_followup' ? '需要继续追问' : '已回答，等待你确认理解'}</small><button className="hint-link" disabled={busy || q.status === 'awaiting_answer'} onClick={() => send('resolve_teaching_question', {question_id:q.id})}>这个疑问已解决 <Check size={13} /></button></div>)}</div>}
    <details className="session-record"><summary>授课会话记录 <ChevronDown size={13} /></summary><p>原课堂位置：{phaseLabels[session.resume_point.phase] ?? session.resume_point.phase} · 第{session.resume_point.step_count}步之后</p><p>已完成要点：{session.completed_points.join('、') || '暂无'}</p><p>已确认解决的疑问：{session.resolved_questions.length}个</p>{session.checks.map((c,i) => <p key={i}>第{c.segment_index+1}段 · 第{c.attempt}次：{c.answer} · {c.correct ? '通过' : '待补充'}</p>)}</details>
    <details className="task-boundaries"><summary>查看任务目标与边界 <ChevronDown size={13} /></summary><p>{task.objective}</p>{task.constraints.map(c => <p key={c}>{c}</p>)}</details><div className="lecture-pause"><button className="secondary" disabled={busy} onClick={() => send('pause_lecture')}>暂存讲授，回到原课堂</button><span>保留当前要点、检查结果与疑问，可稍后恢复。</span></div><div className="lecture-task-id">任务 {task.id.slice(0,8)}</div></div>;
}

export default function LegacyClassroom() {
  const [credential, setCredential] = useState<Credential | null>(null);
  const [state, setState] = useState<Snapshot | null>(null);
  const [mode, setMode] = useState('local');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [kind, setKind] = useState('add');
  const [target, setTarget] = useState(1);
  const [source, setSource] = useState(0);
  const [multiple, setMultiple] = useState('-2');
  const [result, setResult] = useState<Matrix>([['', '', ''], ['', '', ''], ['', '', '']]);
  const [answer, setAnswer] = useState('');
  const [question, setQuestion] = useState('');
  const [needsHelp, setNeedsHelp] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [checks, setChecks] = useState([-1, -1]);
  const [note, setNote] = useState('');
  const [showCollaboration, setShowCollaboration] = useState(true);
  const [teachingTopic, setTeachingTopic] = useState('triangular_method');
  const [recipient,setRecipient]=useState('lecturer');
  const messagesEnd = useRef<HTMLDivElement>(null);
  const lock = useRef(false);
  const currentRevision = useRef(-1);

  function accept(data: Envelope) {
    if (data.snapshot.revision < currentRevision.current) return;
    currentRevision.current = data.snapshot.revision;
    setState(data.snapshot); setMode(data.teaching_mode);
  }
  async function request(path: string, cred: Credential | null, options: RequestInit = {}) {
    const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(cred ? { Authorization: `Bearer ${cred.token}` } : {}) } });
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : '提交格式有误，请检查输入。'), { status: response.status });
    return data;
  }
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved) {
          const cred = JSON.parse(saved) as Credential;
          const data = await request(`/api/sessions/${cred.session_id}`, cred);
          if (alive) { setCredential(cred); accept(data); }
        }
      } catch (e) { if (alive) setError(`恢复课堂失败：${(e as Error).message} 可以重试刷新，或开始新课堂。`); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    setResult(state?.matrix?.map(row => [...row]) ?? [['', '', ''], ['', '', ''], ['', '', '']]);
    setAnswer('');
  }, [JSON.stringify(state?.matrix), state?.problem?.id, kind, target, source]);
  useEffect(() => {
    const container = messagesEnd.current?.parentElement;
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
  }, [state?.messages.length, state?.messages.at(-1)?.status]);
  useEffect(() => {
    if (!credential || !state?.messages.some(m => m.status === 'pending')) return;
    const timer = setInterval(async () => {
      if (lock.current) return;
      try { accept(await request(`/api/sessions/${credential.session_id}`, credential)); } catch { /* manual next action remains available */ }
    }, 1200);
    return () => clearInterval(timer);
  }, [credential, state?.messages]);

  async function start() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const data = await request('/api/sessions', null, { method: 'POST',body:JSON.stringify({mode:'planner'}) });
      const cred = { session_id: data.session_id, token: data.token };
      localStorage.setItem(storageKey, JSON.stringify(cred));
      currentRevision.current = -1; setCredential(cred); accept(data);
      setRestartOpen(false); setNeedsHelp(false); setChecks([-1, -1]); setNote('');
    } catch (e) { setError((e as Error).message); }
    finally { lock.current = false; setBusy(false); }
  }
  async function send(type: string, payload: Record<string, unknown> = {}) {
    if (!credential || !state || lock.current) return false;
    lock.current = true; setBusy(true); setError('');
    try {
      const data = await request(`/api/sessions/${credential.session_id}/events`, credential, { method: 'POST', body: JSON.stringify({ expected_revision: state.revision, idempotency_key: crypto.randomUUID(), type, payload }) });
      accept(data); setNeedsHelp(Boolean(data.result?.needs_assistance_confirmation));
      return true;
    } catch (e) {
      setError((e as Error).message);
      if ((e as { status?: number }).status === 409) {
        try { accept(await request(`/api/sessions/${credential.session_id}`, credential)); } catch { /* show original error */ }
      }
      return false;
    } finally { lock.current = false; setBusy(false); }
  }
  async function ask(acceptAssistance = false, text = question) {
    if (!text.trim()) return;
    if (await send(recipient==='planner' || state?.phase==='planning' ? 'planner_message' : 'ask_question', { text, accept_assistance: acceptAssistance })) setQuestion('');
  }
  function downloadReport() {
    if (!state?.report) return;
    const r = state.report;
    const text = `# 序 · 三阶行列式学习笔记\n\n${r.passed ? '本次达标（未验证长期保持）' : '尚未收集到全部达标证据'}\n\n## 学习记录\n${r.attempts.map(a => `\n### ${a.title}\n${a.independent ? '独立完成' : '辅导完成'}，答案：${a.answer}\n${a.steps.map(s => `${s.label}；c=${s.factor}\n${s.matrix.map(row => row.join('  ')).join('\n')}`).join('\n\n')}`).join('\n')}\n\n## 关键规则\n${r.notes.map(n => '- ' + n).join('\n')}\n\n## 错误与修正\n${r.mistakes.map(m => '- ' + m.text).join('\n') || '没有记录到错误。'}\n\n## 我的说明（未自动评分）\n${r.explanation?.note || '未填写'}\n\n## 下一步\n${r.next}\n`;
    const teachingNotes = '\n\n## 分段讲授记录（随堂检查，不等于独立掌握）\n' + (r.teaching_sessions ?? []).map(t => `\n### ${t.title}\n已完成要点：${t.completed_points.join('、') || '暂无'}\n${t.checks.map(c => `- ${c.segment_title}：${c.answer}，${c.correct ? '通过' : '待补充'}`).join('\n')}\n待解决疑问：${t.open_questions.map(q => q.text).join('；') || '暂无'}\n`).join('\n');
    const url = URL.createObjectURL(new Blob([text, teachingNotes], { type: 'text/markdown;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = '三阶行列式学习笔记.md'; anchor.click(); URL.revokeObjectURL(url);
  }
  const phase = state?.phase ?? 'welcome';
  const isExam = phase === 'independent_assessment';
  const isProblem = phase === 'guided_practice' || isExam;
  const triangular = state?.matrix && [state.matrix[1][0], state.matrix[2][0], state.matrix[2][1]].every(v => v === '0');
  const phaseIndex = phase === 'planning'||phase === 'diagnosis' ? 0 : phase === 'guided_practice' || phase === 'lecture' ? 1 : phase === 'report' ? 3 : 2;
  const lastStudentQuestion = state?.messages.filter(m => m.role === 'student').at(-1)?.text ?? '';

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" aria-label="序，AI 线代私教"><span className="brand-mark">序<span>·</span></span><span className="brand-caption">让理解，一步一步发生</span></a>
      <div className="sidebar-label">你的学习空间</div>
      <div className="nav-item selected"><BookOpen size={18} /> 线性代数 <span className="nav-dot" /></div>
      <div className="course-outline"><span className="outline-line" /><span className="outline-dot" /> 三阶行列式</div>
      <div className="sidebar-bottom"><div className="mini-avatar"><GraduationCap size={19} /></div><div><strong>专注一次小进步</strong><span>匿名学习 · 本机保存恢复入口</span></div></div>
    </aside>

    <main className="main-shell">
      <header className="topbar"><div className="breadcrumb">线性代数 <span>/</span> 行列式 <span>/</span> <strong>化三角形法</strong></div><div className="top-actions"><span className="mode-pill"><span />{mode === 'ai' ? 'AI 问答已连接' : '规则教学模式'}</span><button className="icon-button" title="查看本节规则" aria-label="查看本节规则" onClick={() => setRulesOpen(!rulesOpen)}><CircleHelp size={19} /></button></div></header>

      {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="关闭错误"><X size={16} /></button></div>}

      {!state ? <div className="welcome">
        <div className="eyebrow"><span /> 一节小课，一个真正学会的方法</div>
        <h1>把复杂的计算，<br />变成清晰的<span>三步。</span></h1>
        <p className="welcome-description">从三阶行列式开始，学会用行变换化成上三角形。<br />你来动手，我陪你理清每一步。</p>
        <div className="welcome-meta"><span><Clock3 size={16} /> 约 20 分钟</span><span><ShieldCheck size={16} /> 分步验证 · 独立测验</span></div>
        <button className="primary start-button" disabled={busy || loading} onClick={start}>{busy || loading ? <LoaderCircle className="spin" size={19} /> : <>让 AI 安排学习 <ArrowRight size={18} /></>}</button>
        <div className="welcome-art"><div className="art-label">从这里出发</div><MathText tex={'\\begin{vmatrix}a&b&c\\\\d&e&f\\\\g&h&i\\end{vmatrix} \\quad \\longrightarrow \\quad \\begin{vmatrix}a&b&c\\\\0&p&q\\\\0&0&r\\end{vmatrix}'} display /><div className="art-foot"><span>消去下方的元素</span><span>让结构告诉你答案</span></div></div>
        <div className="welcome-footer">不需要一次全会。每一个错误，都是下一步教学的起点。</div>
      </div> : <>
        <section className="lesson-heading"><div><div className="eyebrow">微课堂 01 <span className="tiny-divider" /> 行列式的计算</div><h1>三阶行列式，化繁为简。</h1><p>用行变换化为上三角形，再求出原行列式的值。</p></div><div className="heading-actions">{phase !== 'report' && phase !== 'planning' && <button className="secondary arrangement-shortcut" disabled={busy} onClick={() => send('planner_message', {text:'请根据当前学习记录重新安排下一步'})}>调整教学安排</button>}<button className="subtle-button" onClick={() => setRestartOpen(true)}><RotateCcw size={15} /> 新一轮学习</button></div></section>
        <div className="progress-track">{['目标与诊断', '引导练习', '独立验证', '学习报告'].map((name, i) => <div key={name} className={`progress-step ${i === phaseIndex ? 'current' : ''} ${i < phaseIndex ? 'done' : ''}`}><span className="step-number">{i < phaseIndex ? <Check size={13} /> : `0${i+1}`}</span><span>{name}</span>{i < 3 && <span className="step-line" />}</div>)}</div>

        {phase === 'report' && state.report ? <section className="report-layout"><div className="report-card"><div className="report-icon"><GraduationCap size={30} /></div><div className="eyebrow">每一步都有迹可循</div><h2>{state.report.passed ? '这一次，你独立做到了。' : '把这次进步，留给下一次。'}</h2><p>{state.report.passed ? '普通消元、换行题与规则辨析均已通过。长期保持还需要之后的新题验证。' : '本次学习已保存，尚未收集到全部独立达标证据。'}</p><div className="report-stats"><div><strong>{state.report.attempts.length}</strong><span>完成题目</span></div><div><strong>{state.report.attempts.filter(a => a.independent).length}</strong><span>独立完成</span></div><div><strong>{state.report.mistakes.length}</strong><span>错误观察</span></div></div><h3>本节学习轨迹</h3>{state.report.attempts.length ? state.report.attempts.map((a, i) => <details className="attempt" key={i}><summary><span>{a.title}</span><span className={`badge ${a.independent ? 'green' : ''}`}>{a.independent ? '独立完成' : '辅导完成'}<ChevronDown size={14} /></span></summary><p>最终答案：{a.answer} · {a.steps.length} 次合法行操作</p>{a.steps.map((s, j) => <div key={j} className="report-step"><code>{s.label}</code><MathText tex={`${s.factor} \\times ${determinantTex(s.matrix)}`} display /></div>)}</details>) : <p className="muted">本次尚未完成整道题。</p>}<h3>错误与修正</h3>{state.report.mistakes.length ? state.report.mistakes.map((m, i) => <div className="mistake-note" key={i}><Lightbulb size={16} /><span>{m.text}</span></div>) : <p className="muted">本次没有记录到错误。</p>}{state.report.explanation?.note && <><h3>我的解释 <small>已保存，未自动评分</small></h3><p className="personal-note">{state.report.explanation.note}</p></>}<div className="report-actions"><button className="primary" onClick={downloadReport}><Download size={16} /> 下载学习笔记</button><button className="secondary" disabled={busy} onClick={start}>再学一轮 <ArrowRight size={16} /></button></div></div><aside className="report-notes"><div className="panel-kicker"><BookOpen size={17} /> 带走这几条规则</div>{state.report.notes.map((n, i) => <p key={i}><span>0{i+1}</span>{n}</p>)}<div className="next-note"><Clock3 size={17} /><p>{state.report.next}</p></div></aside></section> : <div className="classroom-grid">
          <section className="work-panel"><div className="panel-top"><span><span className="live-dot" /> {phaseLabels[phase]}</span><span className="small-muted">{phase === 'diagnosis' ? `${state.diagnostic_index+1} / 3` : isExam ? state.helped ? '辅导尝试' : '独立作答' : '一起完成'}</span></div>

            {phase === 'planning' && state.planner && <PlanningPanel planner={state.planner} busy={busy} send={send} />}

            {phase === 'diagnosis' && state.diagnostic && <div className="diagnostic-body"><div className="task-tag">小诊断 · 不计入独立达标</div><h2>{state.diagnostic.question}</h2><p className="muted">选出你认为正确的答案，我们据此调整讲解。</p><div className="choice-list">{state.diagnostic.choices.map((choice, i) => <button disabled={busy} key={`${state.diagnostic_index}-${i}`} onClick={() => send('submit_diagnostic_answer', { choice: i })}><span>{String.fromCharCode(65+i)}</span>{choice}<ArrowRight size={16} /></button>)}</div><div className="gentle-note"><Sparkles size={17} /> 不确定也没关系，先从你的理解出发。</div></div>}

            {phase === 'lecture' && state.teaching_task?.segment && <LecturePanel task={state.teaching_task} busy={busy} send={send} />}

            {isProblem && state.matrix && <>
              <div className="problem-heading"><div className="task-tag">{isExam ? '把方法用在新题上' : '从一个具体的例子开始'}</div><h2>{state.problem?.title}</h2><p>目标：消去主对角线下的三个元素。</p></div>
              <div className="matrix-stage"><span className="matrix-caption">原行列式 D</span><MathText tex={`${state.factor === '1' ? '' : `${state.factor} \\times `}${determinantTex(state.matrix)}`} display /><div className="factor-note"><ShieldCheck size={14} /> 始终保持 <MathText tex={`D = ${state.factor} \\times \\det(M)`} /></div></div>
              {state.steps.length > 0 && <details className="history"><summary>已完成 {state.steps.length} 步 <ChevronDown size={14} /></summary>{state.steps.map((step, i) => <div key={i}><span>{String(i+1).padStart(2, '0')}</span><code>{step.label}</code><small>c = {step.factor}</small></div>)}</details>}
              {!state.problem_done ? <div className="operation-area"><div className="section-heading"><h3>下一步，怎样变换？</h3><button className="hint-link" disabled={busy} onClick={() => send('request_hint')}><Lightbulb size={15} /> {isExam && !state.helped ? '获取学科帮助' : '给我一点提示'}</button></div>{isExam && !state.helped && <p className="exam-note">获取提示或学科问答后，本题会记为辅导完成，之后换题复测。</p>}<div className="operation-controls"><label>操作<select aria-label="操作类型" value={kind} onChange={e => setKind(e.target.value)}><option value="add">倍加 · 不改变值</option><option value="swap">换行 · 变号</option><option value="scale">缩放 · 调整倍数</option></select></label><label>目标行<select aria-label="目标行" value={target} onChange={e => setTarget(Number(e.target.value))}>{[0,1,2].map(i => <option key={i} value={i}>R{i+1}</option>)}</select></label>{kind !== 'scale' && <label>来源行<select aria-label="来源行" value={source} onChange={e => setSource(Number(e.target.value))}>{[0,1,2].map(i => <option key={i} value={i}>R{i+1}</option>)}</select></label>}{kind !== 'swap' && <label>倍数 k<input aria-label="倍数" value={multiple} onChange={e => setMultiple(e.target.value)} maxLength={30} placeholder="如 -2 或 1/2" /></label>}</div><div className="operation-preview"><MathText tex={kind === 'add' ? `R_{${target+1}} \\leftarrow R_{${target+1}} + kR_{${source+1}}` : kind === 'swap' ? `R_{${target+1}} \\leftrightarrow R_{${source+1}}` : `R_{${target+1}} \\leftarrow kR_{${target+1}}`} /></div><label className="result-label">填写变换后的结果 <span>仅编辑受影响的行 · 支持分数，如 1/2</span></label><div className="matrix-input-wrap"><div className="matrix-input">{result.map((row, i) => row.map((v, j) => { const editable = kind === 'swap' ? i === target || i === source : i === target; return <input key={`${i}-${j}`} aria-label={`第${i+1}行第${j+1}列`} disabled={!editable || busy} value={v} maxLength={30} onChange={e => setResult(old => old.map((r, ri) => r.map((x, ci) => ri === i && ci === j ? e.target.value : x)))} />; }))}</div><button className="primary" disabled={busy} onClick={() => send('submit_row_step', { operation: { kind, target, source, multiple }, result })}>{busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />} 验证这一步</button></div><div className={`final-answer ${triangular ? 'ready' : ''}`}><div><strong>{triangular ? '已化成上三角形' : '准备好后，提交原行列式的值'}</strong><span>{triangular ? '对角线相乘，再处理修正系数 c。' : '先完成三角化，再计算最终结果。'}</span></div><form onSubmit={e => { e.preventDefault(); send('submit_final_answer', { answer }); }}><span>D =</span><input aria-label="原行列式的值" placeholder="结果" value={answer} onChange={e => setAnswer(e.target.value)} maxLength={30} /><button className="icon-submit" disabled={busy || !answer.trim()} aria-label="提交最终答案"><ArrowRight size={18} /></button></form></div></div> : <div className="success-block"><span><Check size={19} /></span><div><strong>这一题，完成了。</strong><p>{state.helped || !isExam ? '接下来用新题验证能否独立完成。' : '独立完成的证据已保存。'}</p></div><button className="primary" disabled={busy} onClick={() => send('continue')}>继续 <ArrowRight size={16} /></button></div>}
            </>}

            {phase === 'rule_check' && <div className="rule-check"><div className="task-tag">最后一步 · 规则辨析</div><h2>不仅算对，也知道为什么。</h2><p className="muted">请选择理由，再用自己的话留下一句笔记。</p>{[{ title: 'R₂ ← R₂ + 3R₁ 后，原值与新值有什么关系？', options: ['原值是新值的 1/3', '原值等于新值，因为倍加不改变行列式', '原值是新值的 −1 倍'] }, { title: '先交换两行，再把一行乘以 2，如何恢复原值？', options: ['原值 = 2 × 新值', '原值 = −2 × 新值', '原值 = −1/2 × 新值'] }].map((q, qi) => <fieldset key={qi}><legend>{qi+1}. {q.title}</legend>{q.options.map((o, i) => <label key={i}><input type="radio" name={`check-${qi}`} checked={checks[qi] === i} onChange={() => setChecks(old => old.map((v, j) => j === qi ? i : v))} />{o}</label>)}</fieldset>)}<label className="note-label">用自己的话解释一下 <span>可选 · 保存为笔记，首版不自动评分</span><textarea value={note} onChange={e => setNote(e.target.value)} maxLength={1500} placeholder="例如：为什么倍加与把一行乘以一个数，不是同一种操作？" /></label><button className="primary" disabled={busy || checks.includes(-1)} onClick={() => send('submit_explanation', { answers: checks, note })}>完成辨析，查看报告 <ArrowRight size={16} /></button></div>}
            {phase === 'rule_remedy' && <div className="diagnostic-body"><div className="task-tag">规则回补</div><h2>先把关系理清，再继续。</h2><p className="muted">两道计算题的独立表现已保存，规则辨析还需要复习。这次不重复刚刚公布答案的题目作为达标证据。</p>{rules.map(r => <div className="remedy-card" key={r.name}><strong>{r.name}</strong><MathText tex={r.tex} /><p>{r.text}</p></div>)}<button className="primary" disabled={busy} onClick={() => send('finish')}>保存本次报告 <ArrowRight size={16} /></button></div>}
            {['guided_practice','independent_assessment','rule_check','rule_remedy'].includes(phase) && <div className="teaching-request"><label>想让授课 Agent 再讲讲？<select aria-label="授课知识点" value={teachingTopic} onChange={e => setTeachingTopic(e.target.value)}><option value="triangular_method">化上三角形的整体方法</option><option value="addition">倍加与缩放的区别</option><option value="swap">换行与符号修正</option><option value="triangle">上三角形求值</option></select></label><button className="secondary" disabled={busy} onClick={() => send('request_teaching', {topic:teachingTopic})}><BookOpen size={15} /> 请授课 Agent 讲解</button>{isExam && <small>本题将记录为辅导尝试，之后需要新题复测。</small>}</div>}
            {phase !== 'lecture' && state.paused_teaching_tasks && state.paused_teaching_tasks.length > 0 && <div className="paused-lectures"><h3>暂存的授课会话</h3>{state.paused_teaching_tasks.map(t => <button className="secondary" key={t.id} disabled={busy} onClick={() => send('resume_lecture', {task_id:t.id})}>恢复「{t.title}」· 第{t.segment_index+1}/{t.segment_total}段 <ArrowRight size={14} /></button>)}</div>}
          </section>

          <aside className="teacher-panel"><div className="teacher-heading"><div className="teacher-avatar"><Sparkles size={21} /></div><div><strong>课堂对话与协作</strong><span>{phase === 'planning' ? '教学安排 Agent 出场中' : phase === 'lecture' ? '授课 Agent 出场中' : '按学习证据安排下一步'}</span></div><span className="live-dot" /></div><div className="agent-roster"><span className="agent-planner">排 · 教学安排</span><span className="agent-scheduler">调 · 调度器</span><span className="agent-lecturer">授 · 授课</span><span className="agent-assessment">评 · 测评</span></div><label className="collaboration-toggle"><input type="checkbox" checked={showCollaboration} onChange={e => setShowCollaboration(e.target.checked)} /> 显示任务下达与交接记录<span>{mode === 'ai' ? '授课由 DeepSeek 生成' : '当前使用规则讲稿'}</span></label><div className="chat-messages" aria-live="polite">{state.messages.filter(m => showCollaboration || m.kind !== 'handoff').map(m => <ChatMessage item={m} key={m.id} />)}<div ref={messagesEnd} /></div><div className="chat-compose"><label className="recipient-selector">对话对象<select aria-label="对话对象" value={phase==='planning' ? 'planner' : recipient} disabled={phase==='planning'} onChange={e => setRecipient(e.target.value)}><option value="lecturer">授课 Agent · 知识提问</option><option value="planner">教学安排 Agent · 调整学习</option></select></label>{needsHelp && <div className="help-confirm">学科问答会结束本题的独立尝试。<button disabled={busy} onClick={() => ask(true, lastStudentQuestion)}>转为辅导并回答</button></div>}<form onSubmit={e => { e.preventDefault(); ask(); }}><textarea aria-label="向老师提问" rows={2} placeholder={phase==='planning' || recipient==='planner' ? '说说学习目标、基础或调整需求…' : '随时打断，向授课 Agent 提问…'} value={question} onChange={e => setQuestion(e.target.value)} maxLength={1500} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(); } }} /><button disabled={busy || !question.trim()} aria-label="发送问题"><Send size={17} /></button></form><span><MessageCircle size={12} /> Enter 发送 · Shift + Enter 换行</span></div></aside>
        </div>}
        {phase === 'report' && state.report?.teaching_sessions && state.report.teaching_sessions.length > 0 && <section className="report-teaching"><h3>分段讲授记录 <small>随堂检查，不等于独立掌握</small></h3>{state.report.teaching_sessions.map(t => <details className="attempt" key={t.id}><summary>{t.title}<span>{t.completed_points.length} 个要点 · {t.checks.length} 次检查</span></summary><p>已完成要点：{t.completed_points.join('、') || '暂无'}</p>{t.checks.map((c,i) => <p key={i}>{c.segment_title}：{c.answer} · {c.correct ? '通过' : '待补充'}</p>)}<p>已确认解决 {t.resolved_count} 个疑问</p>{t.open_questions.map(q => <p key={q.id}>待解决：{q.text}</p>)}</details>)}</section>}
        <footer className="class-footer"><span><ShieldCheck size={13} /> 每一步计算都经过精确验证，学习记录自动保存。</span>{phase !== 'report' && <button disabled={busy} onClick={() => send('finish')}>结束并保存报告 <ArrowRight size={13} /></button>}</footer>
      </>}
    </main>
    {rulesOpen && <div className="modal-backdrop" onClick={() => setRulesOpen(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="本节规则" onClick={e => e.stopPropagation()}><button className="modal-close icon-button" onClick={() => setRulesOpen(false)} aria-label="关闭规则"><X size={20} /></button><div className="eyebrow">随手翻一翻</div><h2>三条规则，一个方法。</h2>{rules.map(r => <div className="remedy-card" key={r.name}><strong>{r.name}</strong><MathText tex={r.tex} /><p>{r.text}</p></div>)}<p className="muted">补充：一行乘 k，会使行列式乘 k；恢复原值时 c 除以 k，且 k ≠ 0。</p>{isExam && !state?.helped && <p className="exam-note">这些通用规则在所有阶段均可查看；具体解题提示会单独记录。</p>}</section></div>}
    {restartOpen && <div className="modal-backdrop" onClick={() => setRestartOpen(false)}><section className="modal small-modal" role="dialog" aria-modal="true" aria-label="开始新课堂" onClick={e => e.stopPropagation()}><h2>开始新一轮学习？</h2><p>当前记录仍保存在本机服务中。建议先下载报告；新的恢复入口会替换当前入口。</p><div className="report-actions"><button className="secondary" onClick={() => setRestartOpen(false)}>继续当前课堂</button><button className="primary" disabled={busy} onClick={start}><Plus size={16} /> 新课堂</button></div></section></div>}
  </div>;
}

