# 教学绘图工具接入

这是一层开源库适配器，不实现自己的坐标系、图形布局或数值绘图引擎。

| 工具 | 引擎 | 用途 |
| --- | --- | --- |
| draw_function | JSXGraph | 一元函数图像、坐标轴、缩放和拖动 |
| draw_riemann_sum | JSXGraph 的 riemannsum 对象 | 矩形数与左/右/中点取样控制、面积和 |
| draw_diagram | Mermaid | 流程图、时序图、静态思维导图 |
| draw_mindmap | Markmap | Markdown 交互思维导图，展开/折叠/缩放 |

依赖为 npm 的 jsxgraph、mermaid、mathjs。JSXGraph 采用 MIT 许可选项（项目同时提供 LGPL），Mermaid 为 MIT，mathjs 为 Apache-2.0。版本由 package-lock.json 固定；直接复用 JSXGraph 自带样式。数学表达式由 mathjs 解析计算。

## Agent 调用

授课 Agent 的 submit_lecturer_result 新增必填 visuals 数组，无图时为空；每轮最多3张图。模型根据当前对话和教学目标决定配图，也响应学生明确提出的画图请求。测评 Agent 不额外生成配图，避免增加当前题目的答案泄漏路径。

```json
{
  "tool": "draw_riemann_sum",
  "title": "矩形和逼近曲线下面积",
  "caption": "拖动矩形数量，并比较左右端点取样。",
  "expression": "x^2",
  "a": 0,
  "b": 1,
  "x_min": 0,
  "x_max": 1,
  "y_min": -0.1,
  "y_max": 1.3,
  "rectangles": 4,
  "sampling": "right"
}
```

draw_function 使用相同数学字段，不包含 rectangles/sampling。draw_diagram 只包含 tool/title/caption/diagram，例如 diagram 为 `flowchart LR\n A["细分"] --> B["求和"] --> C["取极限"]`。

黎曼和必须单独提供 a、b 作为实际积分端点；x_min/x_max 只控制显示视野，不参与面积计算。a、b 必须递增且位于显示范围内。draw_function 不接收 a、b。早期缺少 a、b 的图会提示重新生成，避免误把坐标留白当成积分区间。

后端 backend/drawing_tools.py 校验工具名、字段、长度、有限坐标范围、矩形数量和表达式允许字符/名称；流程图禁止配置覆盖、HTML、外链与 click。通过后加入 id、engine、status=validated，写入授课消息的 visuals。校验失败时保留文字讲解，显示绘图错误，不执行非法参数。蓝色交接记录显示授课 Agent → 教学绘图工具；它代表参数校验通过，不代表后端完成渲染。

## 前端

TeachingDrawing.tsx 延迟加载开源引擎；数学图调用 JSXGraph.initBoard、functiongraph、riemannsum、Value 和 freeBoard；React 控件只更新引擎参数，不自己计算黎曼和。mathjs 表达式树仅允许数值、x/pi/e、基础算术和列出的数学函数，不调用 eval 或执行模型 JS。非法定义域显示为缺点而不破坏整条对话。

Mermaid 以 strict 安全级别、关闭 HTML 标签布局渲染；生成 SVG 后通过 Blob URL 的 img 展示，不把 SVG 插入主页面执行。组件卸载会释放图板和对象 URL。渲染失败显示说明；参数和原文可继续查看。历史消息没有 visuals 时继续正常显示。

图形参数持久化到 SQLite，会话恢复后重绘。学生拖动的临时矩形数/取样方式仅保留在当前组件，不改变课堂进度或自动记为掌握。图像是否教学正确仍需人工或后续验证，不把绘图库数值近似视作符号证明。

## 验证

`python -m unittest discover -s tests -q`

`node tests/drawing_expression.cjs`

`npm run build`

真实联调需检查函数显示、黎曼和滑块/取样变化、Mermaid 图形及刷新恢复。当前仅接入上述通用能力，不包含 Manim 视频渲染或任意模型代码执行。

Markmap 的 markdown 字段、依赖与生命周期见 [MARKMAP.md](MARKMAP.md)。思维导图请求优先使用 Markmap；旧 Mermaid 图继续支持。
