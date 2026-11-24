# 教学安排 Agent 请求与回复调试

适用 `mode=chat`，只记录更新后发生的 `arrange_learning` 模型调用。左侧“安排 Agent 调试”默认展开，支持请求/回复切换、复制、选择最近调用、放大与 Esc 关闭。

## 显示内容

- 发送给模型：真实 HTTP JSON body 中的 system 提示词、user 问题及课堂上下文、工具 schema、模型与生成参数。DeepSeek 的 thinking 配置在发送前加入，也会显示。面板把消息中的 JSON 排版便于阅读，完整请求 JSON 可展开或复制。
- 模型原始回复：供应商返回的 JSON（在工具解析和教学结果校验之前记录）；`tool_calls[].function.arguments` 保留原文，方便定位非法 JSON、字段不符和输出截断。它可能只有工具调用，`content=null` 并不表示没有回答。
- 调用时间、job_id、状态与耗时；失败时显示安全的错误码和说明。网络或上游响应 JSON 解析失败时没有可展示的有效回复，不伪造响应、不记录供应商错误页/请求头。

连接密钥、令牌、私有评分标准和内部推理字段会隐藏；因此它是脱敏的实际请求/响应，不能用来查看隐藏推理。安排 Agent 不需要私有 rubric，发送前就从 pending_question 中移除，测评评分流程仍保留所需标准。

## 数据与权限

`backend/model_debug.py` 通过 ContextVar 将一次安排调用关联到会话及回合。`tutor.request_completion` 在发出请求前、收到 JSON 后记录，再由安排调用包装器补充校验状态。

调试数据独立保存在课堂数据库同目录的 `model_debug.sqlite3`；可用 `AITEACHER_MODEL_DEBUG_DB` 覆盖路径。每会话保留按开始时间排序的最近30次调用，过晚返回的旧调用不会成为最新。超长单段文本超过700000字符会明确截断。

鉴权 GET `/api/sessions/{sid}/debug/planner` 使用原会话 Bearer 凭据；未授权、错误会话或旧模式不可读取。调试内容不进入课堂 snapshot、普通记录下载、模型用量账本，也不重新注入下一轮模型上下文。

面板在课堂生成期间独立轮询，所以可先看到请求，再看到回复。调试写入不依赖课堂事务：后续授课失败、整轮回滚或旧任务被替代，已发生的安排调用仍可查询。记录写入异常不会阻断教学，只输出不包含内容的错误编号。调用完成仅代表该安排调用及格式校验完成，不代表后续课堂执行成功。

这是本地开发调试功能，记录包含提示词与学生学习上下文；与 data/ 其他本地数据一起管理。折叠面板只收起展示，不停止记录。历史调用没有请求/回复数据，无法补录。

## 验证

- `python -m unittest discover -s tests -q`：真实发送 body 对照、发送中的状态、原始工具 JSON、解析和网络失败、后续失败保留、会话鉴权、脱敏、保留上限。
- `npm run build`：前端类型检查和构建。
- 可选浏览器验证：安装好的 Playwright + Edge 环境下，先运行 `python tests/planner_debug_fixture.py`，再运行 `node tests/planner_debug_browser.cjs`。前者使用8012端口、`.verification/` 独立数据库和本地模拟模型，不能替换为真实课堂服务；不会发出外部模型请求。可用 `PLAYWRIGHT_MODULE_PATH` 指向已有 Playwright 包。测试覆盖实际适配器、请求先显示、失败原文、放大窗口、刷新恢复、切换会话和手机布局。
