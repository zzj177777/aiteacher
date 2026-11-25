# AI 私教 · 通用聊天教学原型

当前默认入口：课程管理页。大课程先规划有序小节卡片，进入每节后再规划本节教学节点，通过卡片恢复学习；以前独立添加的小课保留为补充记录。大课规划、教学安排、授课、测评角色共用模型适配器，通过结构化任务和反馈配合；不是多个独立部署的服务。

## 当前能力与边界

- 动态学习计划、节点进度、插问、举例、测评、会话恢复与记录下载。
- 进度主要来自学生确认；讲过、说懂了、模型判对均不等于长期掌握。
- 通用出题和评分由模型生成，尚无通用事实或数学核验，也无跨会话长期认知模型。
- 数字人课堂提供逐步短板书、当前重点高亮、每步一道理解题；完整讲稿折叠保留，原文字课堂独立。
- 公式由 KaTeX 渲染；JSXGraph、Mermaid、Markmap 提供教学绘图。
- 结构化交接进入下一次模型上下文；模型调用用量与估算费用独立记录。
- 当前为本地单实例原型；进程内后台任务，不流式输出，无生产账户/支付/持久队列。

## 开发文档入口

| 文档 | 适用范围 |
| --- | --- |
| [当前系统与模式](docs/IMPLEMENTATION.md) | 当前架构、真实边界、新旧模式区别 |
| [长期课程管理](docs/COURSE_MANAGEMENT.md) | 课程/小课归档、旧记录导入、恢复鉴权与当前边界 |
| [大课程分层规划](docs/COURSE_CURRICULUM.md) | 大课路线、小节卡片、节内节点、规划任务及版本保护 |
| [学段与学科入口](docs/SCHOOL_CATALOG_UI.md) | 小学语数英，初高中九科；科目自由小课 + 年级学期占位页 |
| [学科自由小课](docs/SCHOOL_FREE_LEARNING.md) | 带入学段科目、聊天定目标、推荐选项、短课规划与历史恢复 |
| [历史小学数学入口](docs/PRIMARY_MATH_ENTRY.md) | 兼容旧书签；当前主入口已改为全学段学科导航 |
| [教材资料库](docs/TEXTBOOK_LIBRARY.md) | 12 册官方书目与本地历史教材 PDF，支持阅读、下载；正文检索与章节目录待接入 |
| [通用 Agent 协议](docs/CHAT_AGENTS_DEVELOPMENT.md) | 默认聊天课堂，主要开发入口 |
| [数字人课堂](docs/DIGITAL_CLASSROOM.md) | 并行页面、角色、逐步板书与理解检查、语音和打断 |
| [信息交接](docs/HANDOFFS.md) | 任务派发、反馈、下一轮消费、隐私与历史兼容 |
| [调用用量与成本](docs/COST_TRACKING.md) | 记录、单价配置、查询与限制 |
| [模型接入](docs/DEEPSEEK.md) | 供应商适配与上下文 |
| [错误诊断](docs/ERROR_DIAGNOSTICS.md) | 失败分类、公式约定 |
| [安排 Agent 调试](docs/PLANNER_DEBUG.md) | 左侧查看实际请求、原始工具回复、调用失败与脱敏 |
| [通俗讲解 Agent](docs/PLAIN_LANGUAGE_AGENT.md) | 原句高亮→箭头→分散短批注，难点说明与独立辅助任务 |
| [教学绘图](docs/DRAWING_TOOLS.md)、[Markmap](docs/MARKMAP.md) | 已接入开源绘图能力 |

REQUIREMENTS、LECTURER_AGENT_DEVELOPMENT、PLANNER_AGENT_DEVELOPMENT、SEGMENTED_TEACHING 描述旧版行列式模式或历史设计，不应直接套用于通用聊天。见各文档开头范围说明。

## 启动

需要 Python 3.10+、Node.js 20.19+ 或 22.11+。

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本安装依赖并构建。打开 http://127.0.0.1:8000 。手动开发：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
# 另开终端
npm run dev
```

复制 .env.example 为 .env 后填写模型接口、密钥、模型；只在服务端读取，改配置后重启。费用单价另行配置，不自动采用供应商公开价格。不要将 .env 提交或放入 VITE_* 变量。

## 数据与验证

课堂在 data/classroom.sqlite3，用量在 data/model_usage.sqlite3。浏览器保存匿名恢复凭据；数据库、.env 不提交。旧的模型调用没有用量记录，不能追溯补算。

```powershell
$env:AI_API_KEY=''; $env:AI_API_URL=''; $env:AI_MODEL=''
python -m unittest discover -s tests
node tests/rich_text.cjs
node tests/drawing_expression.cjs
npm run build
```

以上环境变量仅关闭当前测试进程的模型配置，不修改 .env。自动测试验证实现行为，不代表已经证明学生学习效果。旧版功能沿革见 [历史归档](docs/LEGACY_README.md)。
