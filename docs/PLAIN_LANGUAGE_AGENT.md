# 通俗讲解 Agent（右侧“说人话”）

## 目标与边界

授课正文提交后，额外调用一个独立角色，挑选本段真正重要或难理解的概念，以短句和小例子辅助阅读。它不负责课程规划、评分或推进进度，也不把讲过或解释过当作掌握证据。

当前界面采用“原文批注”：每条授课原文中被选中的句子高亮，并从该行右侧空白引出箭头，连接到独立的小解释卡。卡片随原文滚动，不再使用右侧汇总大面板或历史下拉框。优先选1至2个重点，最多3个；没有必要额外解释时允许0条，避免为了凑数制造难点。每卡显示概念、可能的难点、通俗解释；例子和引用按需展开。“定位这句话”精确定位高亮片段。

宽屏卡片位于对应授课右侧，按原文出现顺序对齐；发生碰撞时向下避让并为该授课保留高度。ResizeObserver、窗口 resize 和字体加载后重新测量连线；展开例子也会重排。窄屏将小卡片放在对应授课下方，用相同颜色和缩进指示关联。不同历史授课各自保留批注，切换会话不会沿用结果。

## 运行链路

1. 主 `run_chat` 在锁外完成原教学流程，按现有 job_id 检查后提交课堂。
2. 仅对本轮新增的、非交接、status=ai 的授课消息创建辅助任务，绑定 `source_message_id`。包括正常讲授、举例和直接向授课 Agent 提问。
3. 主课堂提交后，在同一后台工作函数中执行辅助调用；它不再持有课堂数据库锁。前端通过独立接口轮询，因此正文可以先显示并继续交互。
4. `plain_language.generate` 使用独立系统提示与 `explain_lecture_plainly` 工具；结果存入独立库。失败不回滚正文或课堂进度。

主教学流程仍最多3次模型调用；每条成功提交的新授课消息额外最多发起1次自动辅助调用。独立重试另计。不存在自发 Agent 循环。

## 交接输入与输出

输入只包含真实授课原文与ID、该消息的 objective（新消息保存此元数据）、学习阶段/年级/基础自述，以及必要的待答题 question/objective。不读取题目 rubric、不复制全部对话或任务历史。主题以原文为准，旧授课不会因为新目标而被解释成另一门课。学生信息是自述。

返回严格字段：

```json
{
  "takeaway": "一句话重点，最多60字",
  "concepts": [{
    "term": "概念名，最多30字",
    "quote": "从授课原文逐字摘录的连续片段，最多120字",
    "why_difficult": "简短说明这句话可能卡在哪里，最多50字",
    "explanation": "直白解释，最多90字",
    "example": "例子，最多80字，不适合时为空",
    "boundary": "类比边界，最多50字，不需要时为空"
  }]
}
```

模型先定位术语、隐藏前提、易混关系或跳过的推导，再逐条给出 quote → why_difficult → explanation。why_difficult 是可公开的简短教学说明，不是内部思维过程，也不表示学生确定不会。代码检查字段、0至3条、长度和原文引用，按 quote 在原文的位置排序。takeaway、term、why_difficult、explanation（以及没有例子时单独显示的 boundary）的合计文本不超过300字，超限报错并允许重试，不机械截断公式或条件。takeaway 继续保留在协议中，当前批注界面不展示汇总大框。

前端 `RichText` 通过原始 Markdown/LaTeX 字符偏移标记片段：普通文本可拆分，高亮跨加粗标记时递归传递原始偏移；公式和代码作为完整 token 包裹，不能拆坏 KaTeX 或插入模型 HTML。重复出现的同一引用默认定位第一次。箭头从原句所在行的消息边缘发出，避免横穿正文或公式。

模型被要求保留原意、条件与单位，不引入新的陌生术语；有待答测评时不代答，使用不同数值或情境举例。这些提示和引用检查不能保证解释的事实/数学正确性，也不是经过验证的学习效果评估。

## 存储与一致性

`backend/plain_language.py` 使用 `plain_language.sqlite3`，默认在课堂数据库同目录，可由 `AITEACHER_PLAIN_LANGUAGE_DB` 指定。每会话保留最近30条辅助记录。

每条记录含 id、source_message_id、source_title、job_id、created_at、format_version、status、result、error。当前 format_version=2，新增 why_difficult。会话+原文ID唯一，pending 和当前版本 completed 复用缓存。旧版本已完成结果继续高亮和展示解释，点击“补充难点分析”才调用模型升级，不批量补生成。失败或升级重试创建新id，旧请求晚到不能覆盖新id；不同原文结果单独保存。辅助写入不修改课堂 revision、学习计划、证据、报告或普通对话下载。

`PlainLanguageProvider` 按会话统一读取和轮询辅助记录，避免每个历史批注单独发请求；`AnnotatedMessage` 排版连线与卡片，`AnnotatedRichText` 根据精确引用构造高亮。颜色及编号关联同一条批注，悬停互相强调。

启动时未完成辅助记录标记为 failed/interrupted，可手动重试，不假装自动续跑。存储故障只记录安全标识，不回滚已提交的正文，不输出密钥或私有上下文。

调用经原 `tutor.call_tool`，成本独立入原用量账本，agent=plain_language。左侧用量可刷新查看“通俗讲解 Agent”。安排 Agent 调试不会将它误记为安排回复。辅助结果暂不作为下一轮调度反馈。

## API 与旧记录

- 鉴权 GET `/api/sessions/{sid}/plain-language`：返回 explanations 和 limit。
- 鉴权 POST 同地址，body 为 `{"message_id":"真实授课消息ID"}`：补生成旧讲授、升级旧协议或重试失败记录。仅允许当前会话真实、非交接、status=ai 的授课消息。已有 pending/当前版本 completed 时不重复调用。
- 旧会话正常恢复，每段已有授课旁的“为这段加通俗批注”可手动生成，不批量补生成全部历史。

## 验证

完整离线测试、前端构建见 README。`tests/test_plain_language.py` 覆盖引用和长度约束、输入最小化、去重、重试、防旧结果覆盖、重启恢复及不回滚主课堂；HTTP 测试覆盖会话鉴权与非法消息。

`node tests/rich_text.cjs` 额外覆盖跨加粗、跨行、公式完整性与恶意 HTML 转义。可选端到端：运行 `python tests/plain_language_fixture.py`，再 `node tests/plain_language_browser.cjs`。使用本地模拟模型、8012端口和 `.verification/` 独立数据库，不产生外部模型费用；Playwright 和 Edge 已安装时可用，`PLAYWRIGHT_MODULE_PATH` 可指定已有包。覆盖原句锚点与箭头坐标、卡片防重叠、展开/缩放重排、公式、正文先展示、旧结果晚到、恢复、重试、用量、手机布局和会话切换。
