# 聊天课堂错误诊断

每次失败均在 job.error、对应消息的 error 和 chat_agent_result 事件中保存诊断；后端日志输出 chat_failure JSON，界面直接显示失败 Agent、环节、原因、错误码及诊断编号。无需前端升级。

- configuration：模型配置不完整。
- provider_request：HTTP 状态（401/402/429 等）、网络连接失败或45秒超时。
- response_parse：响应 JSON/结构错误、finish_reason=length 输出截断、空回答。
- tool_parse：工具调用数量、参数类型、参数 JSON 解析问题（仅保留行列号）。
- schema_validation：工具名称、必填字段、文本、枚举、步骤或绘图数组不符合约定；details 中记录固定字段名/工具名。
- workflow：未分类的内部异常，只记录异常类型，不记录异常文本。

失败时整轮教学状态回滚，保留学生消息、原学习进度和测评记录。不会自动重试计费请求；可重新发送上一条消息。绘图参数不合规仍按原逻辑保留文字讲解。

不记录 API 密钥、请求/响应正文、异常原文或学生回答。诊断随课堂记录保存在 SQLite 中。旧失败没有错误详情，无法追溯恢复。

## 公式显示约定

Agent 工具参数只做一次 JSON 转义；正文公式用 $ 或 $$ 分隔，禁止套代码标记。前端兼容历史消息中被反引号包住的完整公式和 latex/tex/math 代码块。只在公式内检查全体反斜杠均成倍转义的情况并去掉多余层，保留矩阵原有换行。普通程序代码、路径和文字不会被全局替换。无法解析的公式仍保留原文供排查，KaTeX trust=false。

回归命令：node tests/rich_text.cjs；npm run build；python -m unittest discover -s tests。
