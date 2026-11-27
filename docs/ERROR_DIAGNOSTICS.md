# 聊天课堂错误诊断

主聊天教学任务的每次失败均在 job.error、对应消息的 error 和 chat_agent_result 事件中保存诊断；后端日志输出 chat_failure JSON，界面直接显示失败 Agent、环节、原因、错误码及诊断编号。无需前端升级。

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

若工具参数里的正文换行被再次转义成字面量 `\n` 或 `\r\n`，RichText 在分离公式和代码后，仅将正文中独立的换行转义显示为真实换行；保留 `\nabla` 等较长命令和代码中的转义写法。转换保留原始消息的字符位置，批注仍按原文定位；数据库和左侧原始请求/响应调试内容不改写，历史消息刷新后同样适用。

回归命令：node tests/rich_text.cjs；npm run build；python -m unittest discover -s tests。

## 数字人板书辅助任务

板书是独立辅助调用，不写主教学 job.error；详细协议见 DIGITAL_CLASSROOM。失败当前记录的 diagnostic 和 digital_board_runs 历史按诊断编号保存，界面展示阶段、字段、步骤与限制。不会再只返回“逐步板书暂未生成成功”。

| 错误码 | 含义 |
| --- | --- |
| board_field_type / board_field_empty | 字段类型错误或为空 |
| board_text_too_long | 文本超长，提供实际字符数与上限 |
| board_missing_fields / board_extra_fields | 缺少必填字段或多出字段 |
| board_wrong_tool / board_object_type / board_steps_type / board_step_count | 工具、结果对象、步骤类型或数量错误 |
| board_focus_mismatch | 当前重点无法在对应短板书中找到 |
| board_source_quote_mismatch | 原文依据无法在授课讲稿中找到 |
| board_visual_type / board_visual_count / board_visual_unknown | 配图编号类型、数量或引用错误 |
| board_check_structure / board_check_verdict | 判答结构或枚举错误 |
| board_interrupted | 服务重启打断尚未完成的辅助操作 |
| board_legacy_failure | 旧记录未保存具体原因，重新生成后才有详细诊断 |

provider_request、response_parse、tool_parse 沿用模型适配器的具体错误码；未知异常仅保存类型。重试不会自动触发付费模型调用；由用户点击“重新整理板书”发起。新结果会保留此前失败元数据，当前最多通过诊断接口查询最近 10 条；完整账本仍在本地库中。

原文依据 source_quote 在版本 3 起取消 260 字符上限，长引用不再触发 board_text_too_long；空引用和无法匹配原文仍报错。版本 4 进一步移除所有板书生成文本的字段字符上限；该错误码仅保留兼容旧诊断，主线、补讲和教学标注不再因字段字符数超长而失败。历史记录中的 300/260 报错按原样保留，供追溯旧规则。


版本 5 自动恢复：schema_validation / tool_parse / response_parse / board_recovery 可进入最多两次输出修复。board_repair_structure、board_repair_fields 表示局部替换格式不合法；board_repair_formula_changed 表示修复新增/遗漏/改写了原公式或代码，替换被拒绝。board_recovery_budget 表示没有合法结果且预算耗尽。篇幅超过 300 的 board_length_target 只记为重新编排问题，不是阻断课程的错误。recovery 元数据保留每次尝试摘要；网络与配置故障不进行同样参数的盲重试。
