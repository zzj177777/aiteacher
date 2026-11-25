# 长期课程与小课管理

当前网页入口为 `CourseLibrary`。课程承载大课路线与学习归档：大课程先划分小节卡片，每节绑定 chat session，再规划节内教学节点。独立添加或导入的小课作为补充记录保留。完整协议见 [COURSE_CURRICULUM.md](COURSE_CURRICULUM.md)。

```text
学习空间（当前浏览器持有恢复凭据）
├─ 初二数学
│  ├─ 一次函数（独立聊天、计划、进度、测评、报告）
│  └─ 二元一次方程（另一个独立 session）
└─ 未分类小课（可随时归入课程）
```

## 页面行为

- 课程管理首页展示长期课程卡片、最近一次小课入口，以及未分类的历史小课。
- 支持创建/修改课程名称和说明，在课程内新建小课，恢复已有小课，跨课程归类或移回未分类。
- 进入小课沿用初始化卡片、安排/授课/测评和通俗批注。返回课程管理不会结束后台教学任务。
- 刷新页面恢复当前课程或小课；小课的 revision、对话、待答题、计划、证据和结束状态不因归档发生变化。
- 已结束的小课进入后查看保存的记录；继续学习新内容可在同一长期课程下新建小课。
- 课程卡片显示小课数量、结束数量和最近活动；小课节点条显示“已确认理解”。结束、讲过或自述理解不代表长期掌握。

## 存储与鉴权

在原 `classroom.sqlite3` 中增加目录和路线相关表，启动时通过 `CREATE TABLE IF NOT EXISTS` 迁移，不重建旧表：

| 表 | 用途 |
| --- | --- |
| learning_libraries | 学习空间 id、恢复令牌 SHA256、创建时间 |
| courses | 所属空间、名称、说明、创建/修改时间 |
| course_sessions | session_id 唯一、所属空间、可空课程 id、初始标题、归档时间 |
| course_curricula / curriculum_sections | 大课程规划状态、版本、任务、方案及小节固定会话绑定，详见大课程规划协议 |

浏览器 `aiteacher.learning.library.v1` 保存空间 id 和原始令牌；`aiteacher.learning.navigation.v1` 仅保存当前页面、课程/session id，不存令牌。原 `aiteacher.chat.sessions.v1` 继续保留旧 session 凭据。

空间令牌只能访问本空间的课程及关联小课。原 session 令牌继续只授权原小课，不能访问课程目录。目录列表不返回令牌、完整对话、题目答案标准或模型调试正文。匿名恢复凭据应视作密码，不发送给模型。

首次打开管理页，凭本浏览器已有 session 令牌批量导入 chat 会话到“未分类”。导入逐项校验，幂等，失效项不会阻止其他记录导入，也不会删除原浏览器数据。同一 session 只属于一个空间，不能靠再次导入转移到其他空间。

当前仍是本地匿名原型：不是账户登录或跨设备同步系统。仅有数据库文件不能恢复浏览器已经丢失的原始令牌；清理浏览器存储会丢失恢复入口。

## API

除创建空间外，目录接口均用 `Authorization: Bearer <library_token>`。

| 方法/路径 | 行为 |
| --- | --- |
| POST /api/learning-library | 创建匿名空间，返回 id/令牌 |
| GET /api/learning-library | 本空间课程摘要及未分类小课 |
| POST /api/learning-library/import | 最多200条旧 session 凭据，返回已导入/拒绝 id；不返回令牌 |
| POST /api/courses | 创建课程，title 1–80字、description 0–400字 |
| GET /api/courses/{cid} | 课程及按最近学习时间排序的小课卡片 |
| PATCH /api/courses/{cid} | 修改名称/说明 |
| PATCH /api/learning-library/sessions/{sid} | course_id 指定目标课程，null 移回未分类 |
| POST /api/sessions | 原接口新增可选 course_id/title；携带空间令牌时自动归档 |

GET /api/sessions/{sid} 和既有事件/用量/解释/调试接口继续经过 `read_session`；它接受原 session 令牌，或持有该小课所属空间的有效令牌。分组和重命名不写教学事件，不提升 revision。

## 与 Agent 的关系

读取 session 时由服务端关联实时课程信息，避免移动/重命名后仍使用旧课程名称。`chat_classroom.context.course` 仅包含课程名称和说明，不包含恢复令牌。安排 Agent 将它作为大课程背景，仍围绕本次小课的具体目标安排教学，不自动展开整个学期。

目前不自动汇总跨小课的认知画像，不把兄弟小课的证据传入当前模型上下文，也不据年级或课程名称推断已掌握。这层实现长期组织与恢复，教学记忆的跨课整合需另行设计。

## 课程范围约束

`backend/course_scope.py` 以课程名称为范围依据，说明不能把“初中数学”扩大成英语等无关学科。检查小课创建标题、初始化主题、任意聊天角色的新请求、旧课移入课程，以及有记录课程的改名；AI 返回的实际大纲和专项讲解/出题也在发布前检查。补数学基础或适当学习更高年级内容允许，年级不是硬上限。

明显的同科主题、课堂确认和数学作答使用本地快速判断，明显无关学科直接返回422。交叉学科例子、术语或无法从字面判断的主题由模型调用 `check_course_scope` 返回 allow/redirect/clarify。它是语义分类，不是知识图谱；学科词只帮助快速分流，自定义课程仍能走模型判断。语义判断仍有误判可能，不宣称完全消除跨科漂移。

模型检查在数据库锁外执行；返回后再次检查 revision、课程归属/信息，避免等待期间课程改变后仍提交旧判断。输入被拦截时不保存教学事件、不消耗待答题或取消原任务；AI 输出被拦截时沿用教学事务回滚，记录 `course_scope_violation`，保留此前计划/证据。无法完成语义检查时返回503，不静默放行。查看已有历史记录不做删除或自动搬移。

有计费模型检查时按 `course_guard` 记录用量，侧栏显示“课程范围检查”。创建时被拒绝的请求可能尚无可恢复课堂，计量仍独立留存于用量数据库；归类检查记在被移动的小课，改名检查记在现有首个相关小课。

`tests/test_course_scope.py`、课程 HTTP 测试和 `tests/course_scope_browser.cjs` 覆盖拦截、相关术语例外、错误处理、原状态保留、AI 偏题和归类/改名约束；浏览器测试使用同一个8014本地假模型。

## 验证

`tests/test_courses.py` 覆盖真实 HTTP、历史凭据导入、跨空间隔离、移动后上下文更新、原会话状态保留、重启持久化和边界校验。

浏览器端使用隔离数据库和本地假模型，不产生外部模型费用：

```powershell
python tests/course_library_fixture.py
# 另开终端；需要已安装 Playwright 和 Edge
$env:PLAYWRIGHT_MODULE_PATH='<已有 Playwright 模块的路径>'
node tests/course_library_browser.cjs
```

测试端口8014；数据库和截图都在被忽略的 `.verification/`。运行前先 `npm run build`。浏览器测试覆盖新建课程、旧会话归类、课程背景交给 Agent、小课继续/刷新恢复、修改课程、已结束记录、跨课移动以及桌面/手机布局。
