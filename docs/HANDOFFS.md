# 通用课堂的信息交接

适用 mode=chat，代码 backend/chat_classroom.py。程序顺序调用同一模型的不同角色；交接日志是受控执行记录，不是模型私下自由讨论或隐藏思维链。

新增的授课→通俗讲解交接走独立辅助记录，绑定已提交的 source_message_id，右侧展示角色接力和结果；不加入主调度的 handoffs，不把简化解释作为掌握反馈。正文先提交，辅助失败不回滚主交接。详细输入、输出和恢复机制见 [PLAIN_LANGUAGE_AGENT.md](PLAIN_LANGUAGE_AGENT.md)。

## 1. 派发

学生消息进入安排 Agent，arrange_learning 返回 action、objective、reason 等。后端先校验字段/枚举，再创建任务：

- id / protocol=1 / job_id：交接身份和本回合关联。
- plan_id / node_id：绑定学习计划和节点，避免新目标误用旧反馈。
- sender / recipient / objective / reason：谁交给谁、做什么、公开依据。
- expected_result / constraints：预期返回字段、不能把讲过当掌握、不公开评分标准。
- consumed_feedback_ids：本次安排可参考的反馈ID集合；表示已提供给决策上下文，不表示模型逐条采用了建议。

任务加入context.handoffs后，专项Agent接收同一课堂上下文和objective，能看到本次派发及最近相关反馈。学生明确指定专项角色时沿用受控派发入口，不额外调用安排模型。

## 2. 回传

授课返回message、covered、next_suggestion、visuals。message给学生看，绘图参数单独校验；covered和next_suggestion进入授课→安排的反馈记录。它表示“讲过什么、建议检查什么”，不表示学生已经理解。

测评先返回题目与私有rubric；rubric只存pending_question，不进入公开交接。学生作答后返回verdict、observation、next_suggestion，生成有ID的evidence，记录node_id及assisted。测评→安排交接引用本次evidence_ids；not_answer不新增证据、不引用旧证据。授课反馈也不会错误引用上一题证据。

公开feedback仅白名单保留covered、next_suggestion、verdict、observation以及绘图的tool/engine/caption；不复制整份模型结果，尤其不包含rubric。授课正文在原消息中显示。

## 3. 消费与下一步

context.handoffs提供当前计划最近8条派发/反馈，排除绘图日志，反馈只取教学字段。安排提示明确要求：优先结合结构化反馈、学生最新意图和证据决定teach/diagnose/assess/ask/plan，不机械服从next_suggestion。新派发任务记录对应反馈ID，便于回看信息传递路径。

例：授课反馈“已讲倍加不变，建议解释题检查”→等待学生→下一轮安排收到该反馈及学生回答→安排测评或回补。测评partial且观察“漏记换行符号”→同一回合安排收到反馈与证据→派发换行符号补讲。授课完成后不会自主无限调度；每回合主流程最多3次模型调用，新授课另有1次独立通俗讲解调用。

## 4. 边界与兼容

替换学习计划后不将旧plan_id任务带入新计划。历史任务无plan_id/node_id时不猜测绑定，只保留在历史显示。消息日志中的一般历史仍可能包含旧课内容，不将其当作本计划的结构化证据。

任务与课堂状态一起原子保存；整轮后续失败则交接和进度不部分落库，错误诊断及独立调用用量仍可追查。当前status=completed表示对应处理完成，不是长期掌握；没有增加模型调用次数或新Agent。

安排模型请求与原始回复另存独立调试记录，即使整轮失败、交接未提交，仍可在左侧“安排 Agent 调试”查看。与本节的事务交接记录含义不同，调试不会作为反馈回灌给模型。见 [PLANNER_DEBUG.md](PLANNER_DEBUG.md)。
