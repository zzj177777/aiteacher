> 范围说明：2026-10-20 的旧版行列式需求草案，包含当时的拟议方案（例如 SymPy），不是当前通用聊天系统需求或最终实现。 当前系统见 [系统说明](IMPLEMENTATION.md)，默认开发入口见 [通用 Agent 协议](CHAT_AGENTS_DEVELOPMENT.md)。文内测试数量为历史快照。

# AI Teacher MVP 需求与实现方案

状态：开发前草案。2026-10-20。
目标项目目录：D:\aiteacher（检查时尚不存在；本文暂存于当前可写工作区）。

## 1. 产品目标与边界

帮助大学生通过行变换将三阶行列式化为上三角形，并正确求值。学生需要独立完成新题、解释倍加不变与换行变号，并处理首个主元为零的题。首次通过称为本次达标，不宣称长期掌握。

包含：文字互动、公式、结构化逐步操作、随时插问、局部诊断与补充、独立测验、课后笔记、断线恢复。不包含：语音、拍照手写、全课程知识图谱、支付、复杂账户、多 Agent 自由辩论。

教学强调倍加与换行。允许学生缩放一行，系统必须正确记录倍数；界面可将其放在更多操作中。不教授完整行列式理论，但讲解必须正确区分矩阵行变换与行列式值变化。

## 2. 课堂流程

阶段：diagnosis -> guided_practice -> independent_assessment -> report。
补基础与澄清是当前阶段的子任务，不丢失原题及恢复位置。

诊断：三角形求值、倍加规则、换行规则。引导练习：逐步选择行操作、填写变换结果、计算行列式。测验：至少一题普通消元、一题需要换行的题，以及简短规则解释。测验过程中允许问操作方法；学科提示需明确退出本次独立尝试并记为 assisted，后续换题复测。

普通聊天提问不推进矩阵状态。答案透露、实质性提示均记录；普通术语澄清按内容判断是否构成帮助，不只根据按钮类别判断。

错误分为：输入无效、算术错误、消元选择无效、规则错误、证据不足。先反馈或追问再决定回补，不能仅根据一次错误认定能力缺陷。

## 3. 数学约定

采用精确整数与有理数，输入只允许整数、分数及有限小数（按十进制文本精确转换）；不接受符号表达式或任意代码。后端使用 SymPy Rational。

设原行列式值为 D0，当前矩阵为 M，维护系数 c，使 D0 = c * det(M)，初值 c=1。
倍加 Ri <- Ri + k Rj（i != j）：c 不变。
换行：c <- -c。
缩放 Ri <- k Ri（k != 0）：c <- c/k。
化为上三角形后：D0 = c * M11 * M22 * M33。
合法的不同消元路径均应接受；合法但没有推进三角化的操作给出建议，不判为数学错误。
零主元允许换行；若当前列下面均为零则跳过该列。全零行或其他奇异情况允许结果为零，但仅答零不自动满足本节方法要求。

学生先提交行操作与自己计算的完整结果（前端可只开放受影响行编辑），后端比较预期结果。错误尝试写入事件，但不修改当前矩阵；正确操作才推进版本。

## 4. 前端

建议 React + TypeScript + Vite，公式使用 KaTeX；最终依赖版本在实施时确认。
一个课堂主页面与一个报告视图，首页仅用于开始/恢复。
课堂组件：当前目标/阶段、三阶矩阵、行操作编辑器、结果行输入、推导历史、行列式关系系数、老师对话、提示入口、最终求值输入。
独立测验中保留学生自己的推导历史，隐藏系统的下一步建议和自动生成结果。
必须由后端快照恢复，不自行判定正确性或达标。前端预校验仅帮助输入。
显示请求中、错误、重试、模型不可用等状态。MVP 同一会话按序提交事件；客户端生成 idempotency_key 防重复。发起提问时允许停止尚未展示的老师回复；废弃输出不得覆盖新状态。

## 5. 后端

建议 Python + FastAPI + SymPy + SQLite（单实例原型）。上线多实例或有并发写入需求时迁移 PostgreSQL。
模块：session_service、lesson_controller、math_validator、assessment_service、tutor_service、report_service、content_repository、model_gateway。

程序负责：状态迁移、数学验证、评分规则、提示标记、持久化、并发与权限检查。
模型负责：解释、渐进提示、文字回答评估、提出诊断建议、报告表述。模型建议使用结构化输出并经服务校验；不得直接改数据库或执行学生输入代码。
教学与测评使用隔离提示词及最小上下文，可共用模型；本版不训练模型、不引入 Agent 框架、不进行多轮全员协商。
模型失败时数学提交仍能保存并给出规则化反馈，文字评估标为待评，不默认通过。

## 6. 数据

Session：id、resume_token_hash、phase、revision、current_problem_instance_id、current_matrix、determinant_factor、return_context、status。
Event：id、session_id、sequence、idempotency_key、type、payload、accepted、assessment、created_at。
Problem：id、version、role、matrix、objective_ids、rubric、hint_ladder、misconception_tags、reference（仅服务端）。
Attempt：problem_instance_id、assistance_level、steps、final_answer、criterion_results、status。
Evidence：concept_id、observation、event_ids、independence、uncertainty。
Report：session_id、revision、summary、notes、mistakes、criteria_results、next_practice。
保存模型/提示词/题目版本与工具验证结果以便重放。无需收集真实姓名。匿名恢复令牌也应进行服务端访问校验，不能仅凭可猜 session_id 访问。

## 7. 接口契约

POST /api/sessions：创建匿名课堂，返回 session_id、恢复凭据及公开快照。
GET /api/sessions/{id}：鉴权后获取公开快照与历史。
POST /api/sessions/{id}/events：提交事件；请求包括 expected_revision、idempotency_key、type、payload。类型含 submit_diagnostic_answer、submit_row_step、submit_final_answer、ask_question、request_hint、submit_explanation、continue。
GET /api/sessions/{id}/report：返回结构化报告，未完成时返回明确状态。

提交响应：event_id、revision、snapshot、feedback、teacher_message_status。数学和状态先事务提交，模型长任务随后处理；可通过 GET 会话获取完成消息。首版不要求流式；需要更佳体验时增加 SSE，且不得通过重试重放写操作。
版本冲突返回 409 并要求重新加载；相同幂等键返回原结果。前端只获得公开题面与学生可见反馈，不暴露参考解、隐藏测验或模型密钥。

## 8. 内容与测评标准

准备约 8-12 道人工审核题，区分诊断、示例、练习、独立测验及替代复测。覆盖普通整数消元、分数、换行、奇异矩阵；对零主元和零行列式至少提供正确的程序行为。
达标逐项记录：合法消元、计算正确、行列式关系正确、三角形求值正确、规则解释通过、独立程度。缺任何关键证据不自动判通过。模型无法确认的解释请求澄清或待评。

## 9. 验收与实施顺序

一：数学引擎与内容。验证倍加、换行、缩放、分数、零主元、奇异矩阵、不同合法路径、非法操作与不变量。
二：无模型的课堂闭环。完成提交、反馈、阶段迁移、报告、刷新恢复、重复提交与版本冲突处理。
三：接入模型解释、插问、局部诊断与提示；验证提示后不再算独立通过、插问后原题可恢复、失败降级可用。
四：用人工审核案例检查测评与讲解，学生试用后修正。测试不使用实时模型输出作精确字符串断言。

产品验收：两名具有不同错误的学生获得不同反馈与回补；完成独立新题与解释后才能达标；报告忠于事件；密钥不出现在浏览器；恢复令牌隔离会话；模型不可用不破坏数学状态。

## 10. 待实施时确认

模型供应商、凭据和部署地区；本地演示还是外网部署。未确认前采用模型适配层与本地单实例设计，不阻塞数学引擎、题库和页面开发。
