# 通用聊天教学：Agent 与流程

当前默认网页入口是纯聊天实验室，课程、教学任务和题目由模型根据对话生成，不再限制为行列式，也不读取固定知识点列表。原行列式模式和已有记录保留在后端，未迁移或删除。

## 模块

- `backend/chat_classroom.py`：通用会话、结构化 Agent 协议、角色调度、任务与反馈、测评证据。
- `backend/app.py`：原有鉴权、SQLite、幂等事件和版本冲突控制；增加 run_chat 后台任务及重启恢复。
- `backend/tutor.py`：复用 DeepSeek 原生工具调用，各角色分别发起独立模型请求。
- `src/ChatApp.tsx`、`src/chat.css`：简单聊天入口、会话恢复、角色标识、任务日志、记录下载。原页面源码保留在 `src/LegacyClassroom.tsx`，便于后续参考。

## Agent 协作

学生消息 → 安排 Agent 的 arrange_learning → ask / plan / teach / diagnose / assess。

ask 和 plan 返回学生等待回应。teach 创建任务交给授课 Agent，返回 message、covered、next_suggestion，再交接给安排 Agent，等待学生反馈。diagnose 和 assess 交给测评 Agent，生成单题、目标和仅后端保存的参考标准。

下一条自动路由的学生消息按待答题进行评判；测评 Agent 返回 correct / partial / incorrect / uncertain / not_answer 及观察、建议。有效作答记入 evidence（source=model_judgment），然后安排 Agent 根据反馈决定回补、推进或询问。not_answer 不记作错误。学生也可明确选择安排或授课 Agent 打断，暂停待答题，保留历史对话而不判分。

每个交接保存 sender、recipient、objective、reason、status，以及可公开的 feedback。reason 是短安排依据，不是模型内部推理。计划、讲授、出题与评判均是模型结果；尚无通用符号计算或事实核验，不据单题结果认定掌握。

## 会话协议

### 初始化卡片

默认新学习入口使用 `src/LearningIntake.tsx` 与 `src/intake.css`：学习主题、目标（可多选）、阶段为三项核心信息；年级、基础自述和本次时间选填。选择跟上课堂时展开教材与章节，选择备考时展开考试范围与日期。隐藏的分支字段不提交；后端也按目标清理。草稿只在当前标签页 sessionStorage 暂存，成功提交后清除；失败保留。已有课堂默认直接恢复；“新学习会话”打开卡片，提交前不创建新课堂，可返回原课堂，也可跳过卡片直接聊天。

提交仍使用鉴权、版本控制和幂等事件接口：`chat_intake` 的 payload 字段为 `topic`、`goals`、`stage`、`grade`、`background`、`time_budget`、`textbook`、`chapter`、`exam_scope`、`exam_date`。除 `topic`、`goals`、`stage` 外，其余字段均可省略或为空。只允许尚无学生消息且无计划的新会话提交；后端验证长度、选项、年级与阶段对应和日期。

后端将其保存到 `profile.intake`，附 `source=student_self_report`、`collected_at`；同时生成可见的学生摘要并创建 `intent=intake` 的安排任务。结构化信息随 profile 进入后续各 Agent 上下文，超过24条聊天窗口仍保留，不产生测评证据，不推断前置知识已经掌握。首次动作由程序限定为 ask/plan，等待学生确认后才允许专项讲授或测评；缺信息时只追问必要问题。网络或模型失败不会丢失已保存的初始化信息。兼容没有 intake 字段的旧会话与直接聊天入口。

验证：`test_intake.py` 覆盖数据边界及规划上下文；`test_api.py` 覆盖真实 HTTP 鉴权、幂等和持久化。可选浏览器回归 `node tests/intake_browser.cjs` 需要本机已安装 Playwright 与 Edge：`PLAYWRIGHT_MODULE_PATH` 可指定现有 Playwright 包路径，`INTAKE_TEST_URL` 默认 `http://127.0.0.1:8012`。应使用独立临时数据库、关闭模型配置的服务，避免测试数据写入实际课堂或触发模型计费；截图保存在 `.verification/`。

创建：POST `/api/sessions`，`{"mode":"chat"}`。

事件仍走 `/api/sessions/{id}/events`，携带 expected_revision、idempotency_key、type、payload。新事件：

- chat_message：text 为1至4000字；recipient 为 auto / planner / lecturer / assessment。
- chat_end：取消未完成生成，生成并保存基于对话与证据的记录。
- chat_example：结合最近对话和当前节点交给授课 Agent 举具体、生动的例子；不推进节点。待答题保留并标记 assisted，讲授上下文不包含该题 rubric。
- chat_continue：学生确认理解；已讲节点记录 completion_source=student_acknowledgement 并推进一格，尚未开讲则开始当前节点；有待答测评时拒绝推进。最后节点确认后说明大纲完成，但不自动宣称测评通过或结束会话。

GET 会话返回 working、active_agent、profile、plan、messages、tasks、pending_question（不包含 rubric）、evidence、report。前端用独立的本机存储键保存新聊天会话恢复入口，不覆盖原课堂入口。

plan 新增稳定 id 和 nodes（id、title、status、delivered）；状态为 pending / current / completed。旧会话首次读取时持久化补齐节点，因没有可靠的历史节点映射，从第一节点开始记录进度。模型通过 plan_update=keep/replace 表达是否重排，普通问答默认保留大纲；continue 期间禁止重排。大纲进度与测评证据分开记录。

前端左侧 LearningRoute 展示纵向节点图，侧栏随页面滚动固定并可独立滚动；窄屏改为上下布局。点击节点仅查看内容，不跳课；已确认进度来自学生确认，不表示经过独立验证。RichText 将 **强调** 和行内代码渲染为 React 元素，不执行模型文本中的 HTML。

RichText 使用本地 KaTeX 排版：支持 `\(...\)` / `$...$` 行内公式和 `\[...\]` / `$$...$$` 独立公式，可显示积分、分式、矩阵和求和；独立公式支持横向滚动。普通程序代码不解析公式；为兼容历史输出，完整公式被反引号包住时仍渲染，latex/tex/math 围栏按公式渲染。仅在公式内部兼容成倍转义，保留矩阵换行。只有 KaTeX 生成的 HTML 被插入，trust=false；无效公式回退为可读源码。通用 Agent 输出提示要求面向学生的数学内容采用规范 LaTeX，不猜测历史纯文本中的数学边界。

## 选中解释

`src/SelectionExplainer.tsx` 监听课堂消息内的文本选择，显示浮动“解释选中内容”按钮，点击后在右侧非模态小窗展示简要解释。支持重试、关闭和 Esc；切换会话或重新解释时取消旧请求并忽略过期结果。跨多条消息的选择不显示按钮，单次最多2000字符。

POST `/api/sessions/{sid}/explain` 使用原会话鉴权，接收 message_id 与 text。后端查找真实原文消息，提供原文、目标、当前节点和最多两条附近对话作为解释上下文；不提供题目私有评分标准。模型简要说明词句在当前语境中的含义，不代答整题。调用在数据库锁外进行，不写入对话、进度、任务、作答证据或版本号。失败返回明确错误，不伪造解释。

## 执行控制

独立的通俗讲解 Agent：主授课消息提交后，先指出具体原句及其可能的理解障碍，再给简短解释。原句高亮并用箭头连接右侧分散小卡片，历史批注跟随各自原文。最多3条，可无额外批注；共享会话轮询、独立持久化和重试，失败不回滚正文，不修改课堂进度或证据。接口、format_version=2 与旧结果升级见 [PLAIN_LANGUAGE_AGENT.md](PLAIN_LANGUAGE_AGENT.md)。

左侧新增“安排 Agent 调试”：展示安排模型的脱敏实际请求、原始工具回复与错误状态，生成期间独立轮询。实现为 `backend/model_debug.py`、`src/PlannerDebugPanel.tsx`，鉴权接口 `GET /api/sessions/{sid}/debug/planner`。独立记录最近30次，不随整轮失败回滚、不暴露私有评分标准或内部推理、不进入模型下一轮上下文。详细数据与验证说明见 [PLANNER_DEBUG.md](PLANNER_DEBUG.md)。

工具参数必须匹配规定字段、类型、枚举和长度。每个学生回合的主教学流程最多三次模型调用（测评评判 → 安排 → 专项执行）；新授课成功提交后额外一次通俗讲解调用，独立重试另计，没有无限 Agent 循环。等待学生的消息承担流程边界，程序只保留 pending / completed / failed 等运行状态，不预设各课程教学顺序。

后台在锁外生成，在锁内核对当前 job id 后原子提交。新学生消息会替换旧任务；旧任务即使晚返回也不能覆盖新安排。调用或校验失败时保留原回合、明确提示重试，不伪造通用讲稿或测评结果。重启后未完成任务标为中断。当前后台执行不流式展示中间输出；一回合多个 Agent 完成后一起显示。

## 验证

完整离线回归：先在当前 PowerShell 设置 `$env:AI_API_KEY=''; $env:AI_API_URL=''; $env:AI_MODEL=''`，再 `python -m unittest discover -s tests -q`。不修改 .env。前端运行 `npm run build`。

新增测试覆盖任意课题、计划等待、角色交接、隐藏答案标准、测评反馈、提问不误判、新目标中断、非法工具参数、过期任务与失败恢复；HTTP 验证创建、持久化、幂等和报告。进度测试覆盖大纲保持、逐节点推进、首次开始、末节点确认、测评期间阻止推进及举例保留题目。`node tests/rich_text.cjs` 验证强调、行内代码和 HTML 转义。

后续重点是对话教学质量评估、跨回合压缩记忆、题目与评判核验、可取消的模型请求，以及更清晰的工具执行进度。当前上下文仅保留最近24条消息和12条证据供模型使用，完整历史仍存库，不等于长期认知模型。

## 交接与成本（当前增量）

每个新交接绑定 protocol=1、job_id、plan_id、node_id、expected_result、constraints；完成反馈字段按白名单保留。context.handoffs 提供当前计划最近8条任务/反馈（不含drawing），新派发任务的 consumed_feedback_ids 记录本轮供安排器参考的反馈集合，不表示模型逐条接受。旧交接缺少计划元数据时不推测关联，保留在历史中。

详细协议与时间线见 [HANDOFFS.md](HANDOFFS.md)。每次调用的计量与课堂事务分离；鉴权 GET /api/sessions/{sid}/usage 读取当前会话汇总和最近30次调用，侧栏展示。说明、计价配置和未知用量边界见 [COST_TRACKING.md](COST_TRACKING.md)。
