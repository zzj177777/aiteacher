export type BoardDiagnostic={id:string;stage:string;code:string;message:string;details?:{field?:string;step?:number;actual_length?:number;limit?:number}};
export type BoardAttempt={id:string;created_at?:string;status:string;diagnostic?:BoardDiagnostic};
const stages:Record<string,string>={board_recovery:'板书自动修复',configuration:'模型配置',provider_request:'模型请求',response_parse:'模型响应解析',tool_parse:'工具参数解析',schema_validation:'板书内容校验',board_processing:'板书处理',historical_record:'历史记录'};
const fields:Record<string,string>={title:'标题',board:'短板书',focus:'当前重点',narration:'讲解词',question:'理解问题',rubric:'后台答案标准',source_quote:'原文依据',visual_ids:'配图编号',steps:'步骤列表',feedback:'作答反馈',verdict:'判答结论'};

export default function BoardFailure({diagnostic,attempts=[]}:{diagnostic?:BoardDiagnostic|null;attempts?:BoardAttempt[]}){
 if(!diagnostic)return null;
 const details=diagnostic.details;
 return <div className="board-failure-diagnostic">
  <p className="board-failure-stage">失败环节：<strong>{stages[diagnostic.stage]||'板书处理'}</strong>{details?.field&&<> · {details.step?`第 ${details.step} 步 · `:''}{fields[details.field]||'结果结构'}</>}</p>
  {diagnostic.code==='board_legacy_failure'&&<p>{diagnostic.message}</p>}
  <details><summary>查看诊断详情与重试记录</summary><dl><dt>错误码</dt><dd><code>{diagnostic.code}</code></dd><dt>诊断编号</dt><dd><code>{diagnostic.id}</code></dd>
   {details?.actual_length!==undefined&&<><dt>字符数 / 上限</dt><dd>{details.actual_length} / {details.limit}</dd></>}
  </dl>
  {attempts.length>0&&<ol aria-label="板书生成记录">{attempts.map(attempt=><li key={attempt.id}><span>{attempt.created_at?new Date(attempt.created_at).toLocaleTimeString():''} · {attempt.status==='completed'?'整理成功':attempt.status==='pending'?'整理中':'整理失败'}</span>{attempt.diagnostic&&<p>{attempt.diagnostic.message}<br/><code>{attempt.diagnostic.code}</code></p>}</li>)}</ol>}
  </details>
 </div>;
}
