# Markmap 教学思维导图

开源依赖：markmap-lib 0.18.12（Markdown 转换）和 markmap-view（SVG 交互渲染），MIT 许可；DOMPurify 清理节点 HTML。

## Agent 接口

在授课 Agent 的 visuals 数组中返回：

    {"tool":"draw_mindmap","title":"二次函数知识框架","caption":"先看概念，再看图像与应用。","markdown":"# 二次函数\n## 概念\n- 定义\n- 三种表达形式\n## 图像\n- 对称轴\n- 顶点\n## 应用\n- 最值\n- 实际问题"}

与其他绘图工具共享每轮最多3张图限制。markdown 最大6000字符、100行，须以一级标题开始。模型建议最多60节点、5层。拒绝HTML、链接、图片、代码围栏和配置。后端只保存结构化参数，原有聊天记录恢复机制会持久化导图。

## 前端

TeachingDrawing 按 draw_mindmap 加载 TeachingMindmap；组件懒加载 Markmap，使用无插件 Transformer，不加载外部脚本、CSS或CDN资源。节点内容经DOMPurify白名单清理。

滚轮缩放、拖动平移、点击节点圆点展开/折叠；默认展开前两层，提供适应窗口按钮、自动随容器调整视野和文字大纲。折叠/缩放为当前页面的交互状态，刷新后恢复默认视野，导图内容保持不变。公式暂按普通节点文字显示；主聊天公式仍由KaTeX渲染。

组件卸载时销毁Markmap和ResizeObserver。渲染失败时保留文字大纲及教学正文。

验证：python -m unittest discover -s tests；npm run build。浏览器新会话可请求“请用Markmap总结二次函数知识框架”。
