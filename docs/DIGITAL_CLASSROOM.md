# 数字人课堂（并行实验入口）

入口 `/digital-classroom`；原来的 `/`、文字课堂、课程管理和教学事件语义保持不变。课程中心和文字课堂页头提供新标签页入口。

## 职责

`DigitalClassroom.tsx` 是独立展示层，仍使用 `/api/sessions` 和已有 `chat_*` 事件。安排、授课、测评、结构化计划、任务交接与测评证据均由现有后端产生；Open-LLM-VTuber 的闲聊 Agent 不参与教学。数字人展示层的板书编排只整理授课正文；出题和判答统一调用独立测评 Agent（assessment_agent.py）。白板测评结果写入共享学习证据与调度交接，供教学安排 Agent 使用。

`DigitalAvatar.tsx` 通过开源 PixiJS 6 + pixi-live2d-display 0.4 显示已部署的 Mao 角色。Cubism Core、模型及纹理由同源的限定素材接口提供，不依赖 12393 的演示服务是否启动。Mao 和 Cubism Core 是上游演示素材，授权与 MIT 渲染插件分别管理；商用前需核对各自许可。

`digitalNarrator.ts` 串行播放安排、测评的已提交正文，以及当前板书步骤的讲解和问题；完整授课正文仍可从折叠原文手动重听。交接、学生原话、失败及生成中消息不播报。音频分段生成，Web Audio 分析振幅驱动口型，声音结束不推进课程、不写掌握结论。用户确认后才发送原有的继续事件。数学公式原样保留在板书中。语音层通过同一 KaTeX 引擎输出 MathML，再按结构生成中文读法：字母、隐式乘法、比较、平方/立方、上下标、分数、根号和矩阵等常见表达式可朗读。英文字母以独立英文字符交给语音引擎读字母名称，不再替换为中文谐音；原数学符号为大写时保留“大写”提示。分数按“分母分之分子”读，并保留复合项的括号。复杂或未支持的结构明确提示暂不支持朗读，请结合板书查看，不把不认识的命令当正确读法。

## 数据与取消

- 浏览器凭据独立存于 `aiteacher.digital.sessions.v1`，当前入口存于 `aiteacher.digital.active.v1`。文字模式的本地导航和会话列表不被改写。
- 后端仍是原有持久化 session，首版为独立小课，尚未添加从长期大课小节直接进入数字人模式的导航。
- 刷新或恢复时不自动朗读旧消息或当前旧板书；可点“重听这步”。新授课的首步和用户点击进入的后续小步按语音开关播放，可关闭自动语音。
- 发消息、暂停、新课、恢复其他课程以及卸载组件都会取消请求并清空播放队列。播放代次隔离晚返回的旧音频，防止串课。
- 暂停语音只暂停呈现；发新消息打断生成仍由原有 job 版本机制处理。

## 可选运行依赖

后端模块 `digital_human.py` 注册适配接口，文字流程不会调用语音程序。

`DIGITAL_HUMAN_HOME` 指向官方 Open-LLM-VTuber 完整包；默认是当前项目的相邻 `Open-LLM-VTuber` 文件夹。当前电脑配置值为 `D:\vibe coding\Open-LLM-VTuber`。

`DIGITAL_HUMAN_PYTHON` 可选，默认使用该包 `.venv` 内的 Python。隔离环境需要可用的 `edge-tts`，本机已验证 7.3.1。主教学后端不新增语音模型依赖，不读取或复制 VTuber 的 DeepSeek 密钥。公式解析需要 Node.js 和项目现有的 katex npm 依赖；`DIGITAL_HUMAN_NODE` 可指定 Node 可执行文件，默认从 PATH 查找。`mathml_for_speech.cjs` 只执行受限 KaTeX 解析；`math_speech.py` 负责中文读法。

## 接口与错误边界

- `GET /api/digital-human/status`：检查角色文件、语音服务是否已配置，并返回默认音色 ID；不返回本地路径或凭据。
- `GET /digital-assets/core.js`、`GET /digital-assets/models/{path}`：限定角色目录、扩展名和真实路径，禁止任意文件读取。
- `POST /api/sessions/{sid}/digital-speech`：沿用会话 Bearer 鉴权，请求包括 `message_id`、`chunk` 和可选的 `voice_id`，不接受任意外部文字。服务端从已授权会话查找可播报消息。
- 成功返回 MP3 和 `X-Speech-Chunks`。晓晓通过隔离 Python 的 Edge TTS 合成，将正文发送至微软；豆包音色按版本选择 TTS 3.0 北京接口或 TTS 2.0 接口，将正文发送至火山引擎。公式转换在服务端执行，原课堂正文不变；公式批量解析最多 8 秒，生成读法按原始消息缓存，重听不需要每段重复解析。
- 生成在数据库锁外进行；Edge 超时 40 秒，豆包连接/读取超时 45 秒且在帧间检查总耗时，最多两个并发，16 MiB 进程内音频缓存按供应商、模型、音色、文本隔离。未增加持久化音频库。页面取消后，已开始的子进程可能运行至本次生成结束或超时，但其结果不会继续播放。
- 缺环境、服务失败、繁忙、播放权限等错误只影响声音；板书、学习状态及教学反馈仍保留。重听可重试。
- 语音服务没有接入课程 LLM token 用量计费。豆包为收费 API，按供应商控制台账单核算，当前页面尚不估算语音成本。

## 验证

`python -m unittest discover -s tests -q`：包含数字人鉴权、拒绝未提交/交接/学生消息、素材路径限制、配音失败不改变课程、超时、分段与公式保留测试。

`node tests/digital_narrator.cjs`：验证多段串行、生成中取消、播放中打断、旧会话晚返回以及失败重试。

`node tests/rich_text.cjs`、`node tests/drawing_expression.cjs`、`npm run build`：保留公式、绘图与文字模式回归检查。

公式朗读新增测试：`python -m unittest discover -s tests -p test_math_speech.py -v`，覆盖一次函数、独立字母、复合括号幂、分数顺序、嵌套求根公式、矩阵行、双重转义和解析失败。

初版输入为文字，输出为动漫老师、语音和板书，尚未接入课堂语音输入。不是把独立 VTuber 聊天页面嵌进来；教学权仍在私教系统内。


## 角色选择（2026-11-26）

左侧“老师形象”提供 Mao、初音未来和 Hiyori 趴桌造型。选择存于 `aiteacher.digital.character.v1`，是浏览器展示偏好，不改变课堂 session、计划、Agent 提示词或学生证据。没有选择记录时优先显示已安装的初音，素材缺失时回退 Mao。

`GET /api/digital-human/characters` 返回角色白名单、可用状态、展示模式、相对资源地址和素材说明。动态角色走 `/digital-assets/characters/{character_id}/{path}`；现有 Mao 资源地址仍保留兼容。角色目录和文件扩展名按白名单限制。静态图片只由固定地址 `/digital-assets/portraits/hiyori-movie.jpg` 提供，不支持任意文件路径。

- 初音：官方样例页面列出 Cubism 3.3 runtime。官网文件下载在本机返回 403，当前 runtime 采用开源仓库 `tcmiku/tools_live2D` 保留的同名官方示例，固定提交 `51a1cfb8f74a29907b9c8f68618be45bf012f39d`；只取运行素材与原 ReadMe，不运行该仓库代码。下载逐文件核对 Git blob SHA，源信息与 SHA256 保存在独立素材目录 `live2d-models/miku/SOURCE.json`。初音口型参数使用模型实际声明的 `PARAM_MOUTH_OPEN_Y`，不同于 Mao 的 `ParamMouthOpenY`。
- Hiyori 趴桌：官方是 Form Animation 教学工程，列出 `.cmo3`、`.can3` 和背景图，没有供 SDK 使用的 runtime。当前仅用用户本次提供的 JPG 作静态形象，界面明确标注“静态形象”和“不支持口型”；可以听授课语音，但不会伪装成动态图。没有换成普通站姿 Hiyori。
- 角色外观与配音独立：可选晓晓或已配置的豆包音色，教学风格仍沿用原 Agent。

素材目录在独立 Open-LLM-VTuber 下，不复制进代码仓库或前端 dist。该功能只在本地技术体验范围验证；初音角色不适用 Live2D 原创角色的一般商业使用许可，商业发布前需单独确认 Crypton/Piapro 的角色使用条件。页面保留来源和版权说明。

官方资料：
- https://www.live2d.com/en/learn/sample/hatsune-miku/
- https://www.live2d.com/en/learn/sample/momose-hiyori-video/
- https://www.live2d.com/en/learn/sample/model-terms/
- https://piapro.jp/license/pcl/summary

## 逐步互动板书（2026-11-26）

授课不再默认铺开整段消息。`StepBoard.tsx` 展示当前一小步，以当前阅读句为位置指示，知识标记由独立教学标注 Agent 安排，原对话、完整讲稿和任务交接折叠保留。每步包含短板书、口语讲解和原文依据；整个授课片段在结尾做一次小结检查。板书工具不再生成题目与评分标准；小节末尾由白板适配器请求测评 Agent 独立出题；公式仍由现有 KaTeX 渲染，图仍复用原文已有的 TeachingDrawing，未生成新的可执行代码。

数据流：已提交的 lecturer 消息 → `backend/digital_board.py` 的 `design_step_board` 工具调用 → 字段和长度/原文引用/图 ID 校验 → 持久化 → 前端逐步展示。通常 2–4 小步，步骤数量上限 6；生成的标题、板书和讲解不设字段字符上限。题目、反馈和私有答案标准由测评 Agent 独立生成并校验。不是按字数分页。结构校验不能证明内容正确，当前仍依赖模型编排和判答。

播放只请求当前小步的 narration，不读备用题。最后一段声音结束后停下，不自动翻白板或进入下一步；取消或播放失败不会触发完成回调。每块讲解白板可点“听懂了，继续”或“没懂”；前者手动翻到下一图页或下一白板，最后一块才进入本小节题目。答错可重试，明确跳过标记“稍后再练”，保留补答入口，不记为答对。求助走下述独立补讲支线。

板书小步和课程计划节点是两层进度。小步答对不写长期掌握，也不自动发送 `chat_continue`。本小节检查答对或明确跳过后，学生点击“继续课程”，才沿用原继续事件。文本聊天中的明确指令仍由原调度逻辑处理，因此这些界面约束不是后端课程权限系统。

### 持久化与接口

同一课堂 SQLite 新增 `digital_boards`、`digital_board_answers` 表。板书按 `(session_id, source_id)` 缓存，记录源文本哈希、结构版本和生成状态；答题记录带幂等键，保留尝试。源文在原 session 中不改写。恢复时读取已完成的最新答题反馈；阅读位置另存浏览器 `aiteacher.digital.board.view.<sid>.<sourceid>`，不再被旧版逐页题目的未答状态拦截；旧题及反馈仍保留。浏览器清理后位置可能回到首步，服务端答题记录仍在。

- `GET /api/sessions/{sid}/boards/source/{message_id}`：读取缓存板书和反馈。
- `POST /api/sessions/{sid}/boards`：`{message_id,retry?}`，只接受当前凭据可访问的已提交授课消息；生成中返回 202，失败可重试，原文仍能展开。
- `POST /api/sessions/{sid}/boards/{board_id}/answers`：`{assessment_id,step_id,answer,idempotency_key,skip}`；仅接受独立测评 Agent 已保存的题目，调用共用的 `submit_assessment_result` 判答，保存 correct/partial/incorrect/uncertain/not_answer。明确跳过由程序记录 skipped，不调用模型。判答与学习证据、调度交接一并提交，私有 rubric 不返回前端。
- `POST /api/sessions/{sid}/boards/{board_id}/speech`：`{step_id,chunk}`，服务端查表生成配音，不接受任意外部文本，不播报后台标准或未来步骤。

所有接口沿用 Bearer 鉴权，模型/配音请求均在数据库锁外。重复创建缓存复用；重复提交同一幂等键不重复判答。重启将遗留 pending 标记为失败，允许重试。当前为单进程实现；没有多 worker 作业协调。板书生成失败只影响辅助呈现；主课堂和原文保留。网络中断后的后台生成可能完成，重开可读取缓存。

编排额外产生一次模型调用，未缓存重试也可能产生费用；每次非跳过答题另产生一次判答调用。用量以 `board_designer`、`assessment` 角色关联原 session，独立计量（旧 `board_check` 账目仍保留），不作为免费步骤。Edge TTS 仍是单独的在线服务。

验证：`python -m unittest discover -s tests -p test_digital_board.py -v` 覆盖源引用、字段限制、图引用、鉴权、缓存、幂等、私有标准隔离、失败恢复、跳过和配音范围。`node tests/digital_narrator.cjs` 另外验证板书配音路由、最后音频完成回调、取消不回调、补讲与返回语音路由。

### 可点选的选择题

`boardQuestion.ts` 将已保存题目中连续的 A/B/C 等标准选项拆成题干与选项卡片，保留原 Markdown 和公式。公式及代码内部的字母不作为选项标记；不完整或无法可靠拆分的题目仍保留文字作答。单选使用原生 radio，题干明确标注多选时使用 checkbox，支持键盘操作。点选只更新草稿，点击“检查这一步”才提交所选字母和选项原文，沿用原判答接口；答错可重选，答对锁定，恢复已提交回答时显示原选择。未选时不能提交。

`node tests/board_question.cjs` 验证当前旧题兼容、公式/代码隔离、常见标签、多选及选择恢复。

## 固定白板与逐笔展开

数字人授课的主区域使用固定高度的白板，不再把讲解、图示、题目和反馈拼成长列表。`StepBoard.tsx` 的每个授课小步对应一块白板；块内按“短板书 → 每张原图单独一页”切换；整段授课的最后一块再进入“小结问题 → 作答反馈”。文本按段落或句子停顿拆成几笔，点击“写下一笔”才展开下一个要点，已写内容保留在原位置。完整公式、代码和强调段不被截开，教学标记使用独立模型返回的原文锚点，不再使用旧 focus 或关键词兜底。

`WhiteboardSurface.tsx` 用 ResizeObserver 测量内容与可用画布，保持外部高度不随内容增加而变化；尚未展开的句子不占用布局，避免长篇未来内容把当前文字一并缩小。短内容适度缩放；宽度允许时将缩放保持在至少 0.8 倍，长内容在固定白板内部滚动，并跟随当前阅读句，不撑高整页，也不截断内容。图示独立一页，沿用原绘图组件和交互。短小屏幕可能触发缩放；当前未做任意长公式的语义重排。手机使用固定的独立白板区域，外层页面仍可滚动到老师或白板。

题目与反馈换页显示；选择题继续支持点选，错误反馈后返回原题重试。教学白板之间手动确认继续，不逐页强制出题；小结检查答对或明确跳过后才能点击继续课程，原课程节点继续事件不变。语音只按当前小步讲解合成，不做逐笔的时间戳对齐；展开由学生控制，语音结束不会自动翻页。

课堂路线、完整聊天/讲稿和 Agent 协作通过原生 dialog 查看，不再占用或撑高白板。提问输入框作为浮层展开，不挤压白板。浏览器阅读位置新增 page、revealed，恢复当前白板页及已写笔数；旧阅读位置数据仍兼容。未提交草稿不新增服务端持久化。

`node tests/whiteboard_blocks.cjs` 覆盖分笔停顿、原文偏移、完整公式、矩阵、代码、强调和字面换行兼容。页面验证覆盖展开前后、题目与反馈同高、换块清屏、资料弹窗及刷新恢复。

## 板书失败诊断与重试记录

`board_diagnostics.py` 将生成校验拆成带字段和步骤编号的 TeachingError。网络/供应商、JSON/工具参数、结果格式、未知内部异常分别保留原阶段，`diagnostic` 包含 id、stage、code、message、details。长度错误提供 actual_length/limit，引用错误指明 focus 或 source_quote，配图错误提供未知编号数量；不把模型文本、私有答案标准、密钥或原始异常写入诊断。

原文与重点先精确匹配，再允许空白连续段折叠后的匹配，匹配成功恢复原文本的实际片段，保持公式及前端字符位置。不会做模糊检索、增删符号、自动截断长板书或语义改写；真实不匹配仍失败并显示具体原因。文本首尾空白先去掉再计长度。

生成记录使用版本 3（版本 2 开始记录详细诊断）。`digital_boards` 保存当前结果和诊断；新增 `digital_board_runs` 按每次生成编号保存状态、源消息/哈希及诊断元数据，重试不覆盖此前的失败原因。模型用量通过同一 job_id 关联。GET `/api/sessions/{sid}/boards/source/{message_id}/diagnostics` 沿用会话鉴权，返回最近 10 次生成元数据。旧失败返回 board_legacy_failure，明确说明原因未保存；首次重试会将旧记录存入历史，不能倒推出当时的具体字段。

前端 `BoardFailure.tsx` 显示失败阶段、字段/第几步，展开可查看错误码、字符数、诊断编号和重试记录；当前错误正文直接说明原因。判答失败也附带同样的安全诊断。重启遗留操作记为 board_interrupted。HTTP 200 表示接口处理完成，结果仍需读取 status；模型用量的 completed 表示模型适配层完成，不保证后续板书校验通过。

验证：`python -m unittest discover -s tests -p test_digital_board.py -v` 覆盖字段级错误、空白兼容/数学符号不误配、网络和解析分流、诊断鉴权、历史保留、旧失败兼容和敏感内容隔离。

### 原文依据不再受 260 字符限制

版本 3 移除 source_quote 的 260 字符硬上限，同时移除模型工具 schema 的 maxLength 与提示词中的对应要求。引用可以保留完整段落和公式；仍要求非空、类型正确且能在原讲稿中找到，不截断引用，也不放宽来源匹配。整份模型工具参数的全局大小约束仍由通用适配器处理。版本 4 进一步取消所有板书生成文本的字段字符上限，见下文。旧的失败记录保留，点击重新整理按新规则生成。

## 文字注意力实验（逐句聚焦）

数字人白板提供可关闭的“逐句呈现”，默认开启；句子展开本身不调用模型，不改变授课、判答或课程推进。教学标注是下文独立模型调用，单独计量。`attentionModel.ts` 将原板书段落合并成较完整的句子：定义前提、独立公式和紧接的解释可组成一句，完整公式/代码不拆开，保留原文字符偏移。旧“写下一笔”模式可通过实验开关恢复，显示偏好单独保存在 aiteacher.digital.attention.v1。阅读位置新增 text_mode，句子模式与旧分笔模式的计数分别恢复；首次从旧数据进入句子模式，从当前白板第一句显示，保留原课程及白板位置。

`AttentionText.tsx` 保留前文，以清晰颜色和左侧标记突出当前阅读句，隐藏尚未显示的句子并从辅助技术树移除。红圈、划线与高亮只取自独立模型的已校验标记，不再按照条件词、加粗或第一个公式猜测；旧的样式下拉框已移除。当前句的左侧细线仅表示阅读位置，不表示模型认为它重要。

红圈等使用 MIT 开源库 rough-notation 0.5.1，许可原文保留于 public/assets/licenses/rough-notation.txt（部署后为 /assets/licenses/rough-notation.txt）。其注释绘制在未缩放的白板叠加层，按当前词语或公式的实际屏幕坐标定位；白板缩放、字体加载、窗口变化时重算位置。保留 KaTeX 的原 DOM 和文本排版，不模拟手写，也不新增几何画图。上一句、新一步或卸载时移除旧注释及监听器。

“上一句”“下一句”“看全文”只调整文字呈现；“自动”需主动开启，按当前句的估计阅读时长（2.8–9 秒）展开下一句，在本块末尾停止。暂停、切页/切课、生成忙碌和页面转入后台都会停止自动播放；不会自动出题、答题或进入下一课程节点。该阅读节奏尚未与数字人语音逐句同步。系统减少动态效果偏好下取消出现/标记动画。

验证：node tests/attention_text.cjs；node tests/rich_text.cjs；node tests/whiteboard_blocks.cjs；node tests/board_question.cjs；npm run build。浏览器重点检查当前句唯一、回看/自动暂停、公式完整、缩放后的圈画位置和固定白板高度。


## 小结测验与补讲支线（2026-11-26）

当前把一条已提交的授课消息及其 1–6 块白板视为一个小节。白板下方的“听懂了，继续”是阅读自述，存到 digital_board_reading；不调用判答、不增加成绩或长期掌握证据。文字的“下一句 / 自动 / 看全文”单独控制呈现，翻白板不再要求逐页答题。小结检查由独立测评 Agent 依据整段讲稿生成。旧缓存板书中的题目与评分标准不再用于新测评，首次进入检查页时重新请求测评 Agent。

“没懂”展开困惑浮层，既可鼠标选中当前白板词句，也可输入问题，两项至少一项。选区只来自当前白板内容区；数学公式的浏览器渲染文本按学生引文处理，不强制它等同原始 LaTeX。补讲请求同时带实际原板书、原口语讲解、当前目标/背景及下一步标题，给模型足够的衔接上下文，不带私有判答标准。输入只作为数据。

backend/board_detours.py 通过 teach_board_detour 工具生成 1–3 块短白板、开场承接语和 return_transition。支线复用当前授课角色，独立记作 lecturer_detour 模型用量；没有另造一个有权改课程的调度 Agent。支线不出题、不推进主线、不替换原授课消息。仍没懂时可再次指出词句或提问，带上此前补讲结果换角度解释，始终沿用最初的主线返回位置，不无限压入嵌套返回栈。

新表 digital_board_detours 保存原白板 step_id、index、page、revealed、text_mode、title，学生困惑、请求幂等键、生成结果、状态及 resolution（open / replaced / understood / unresolved）。支线内的阅读位置存在浏览器。刷新查询 active 恢复未结束支线；生成中轮询，重启遗留 pending 标为失败，允许继续补讲或先回主线。同一主线板书只允许一条开放支线。用户离开后迟到的生成结果保留返回状态，不重新激活支线。

补讲完成点“听懂了，回到主线”，恢复离开时的白板页和句子位置，显示承接说明；开启语音时播报返回过渡。不会顺便翻过原白板或把该页记为掌握；学生仍需在主线自己继续。“先回主线”保留未解决标记，不声称听懂。当前过渡句由模型生成，不代表学生已通过客观检查。

接口均沿用会话 Bearer 鉴权：

- POST /api/sessions/{sid}/boards/{bid}/understood：{step_id}，幂等记录学生自述。
- POST /api/sessions/{sid}/boards/{bid}/detours：{step_id,anchor:{page,revealed,text_mode},quote,question,idempotency_key,previous_detour_id?}；同步生成、锁外调用模型，相同请求复用；与同键不同请求冲突返回409。
- GET /api/sessions/{sid}/boards/{bid}/detours/active：读取开放支线，包含 pending、completed 或 failed。
- GET /api/sessions/{sid}/boards/{bid}/detours/{did}：恢复单条记录。
- POST /api/sessions/{sid}/boards/{bid}/detours/{did}/return：{understood:boolean}，保存返回决定。
- POST /api/sessions/{sid}/boards/{bid}/detours/{did}/speech：{step_id,part:'step'|'return',chunk}，仅播报服务端保存的补讲/过渡，首块补讲包含开场承接语。

验证：test_digital_board.py 覆盖自述不等于测评、补讲鉴权与幂等、原状态不变、同一返回锚点、连续求助、失败保留以及返回后迟到结果不复活。digital_narrator.cjs 验证支线与过渡配音路由。浏览器验证逐页不出题、末步小结、选中求助、打字求助、补讲刷新和原位置恢复。局限：当前是单进程本地课堂，未接入跨设备完整阅读位置同步，也没有把支线效果纳入长期认知模型。


## 复用文字课堂的选词答疑

数字人课堂与文字课堂共享 SelectionExplainer.tsx、selection-explainer.css 和 POST /api/sessions/{sid}/explain。鼠标选中当前白板、补讲白板或课堂记录里的词句，点击“解释选中内容”，右侧小窗显示简要解释，支持公式排版、失败重试和 Esc 关闭。打开快捷答疑暂停当前配音，不翻白板、不创建补讲、不写入聊天或学习进度；需要系统补讲时仍使用白板下方“没懂”。

白板 DOM 提供 data-message-id、data-board-id、data-step-id、data-page；补讲额外带 data-detour-id。组件仅接受当前可见教学内容区的选区，过滤 KaTeX 隐藏的 MathML 副本，避免公式重复。切页、切白板、返回主线、切课或关闭课堂记录时取消过期解释，避免把上一页的回复留在新页。小窗和浮动按钮通过 portal 挂到页面或当前原生 dialog 中，兼容课堂记录弹窗的顶层显示。

/explain 保持文字课堂原有请求 {message_id,text}。数字白板附加 {board_id,step_id,detour_id?}；服务端按 session 和 board 关联读取已保存内容，并校验来源消息、步骤及补讲归属，不接受客户端伪造的“原文上下文”。模型主要读取当前白板内容，并补充原始讲稿背景，避免用主线原文去猜支线新讲的概念。只白名单传递标题、板书、口语讲解及公开问题，不包含私有 rubric 或未来步骤。沿用 explainer 用量记录，不另造一套模型接口。使用者选区最多 2000 字符，数学排版文本作为学生选择处理，不要求与原始 LaTeX 完全一致。

验证：test_chat_classroom.py 覆盖主线/支线真实上下文、私有标准和未来步骤隔离、归属与失效步骤校验，以及解释前后课堂状态不变；test_api.py 保留原文字课堂的鉴权、输入校验和未配置反馈。浏览器验证浮动按钮、真实模型解释、公式显示和课堂记录弹窗可用。


## 独立教学标注 Agent（替代原启发式圈画）

设计采用分工：授课 Agent 讲解 → 板书编排工具整理白板 → backend/board_attention.py 独立分析已有讲稿和白板。标注分析使用独立工具调用 annotate_teaching_board，不能修改原文、出题、判答或推进课程。板书编排和补讲工具不再要求返回 focus；旧 focus 字段仍可读取用于兼容，但任何模式下都不驱动前端圈画。

分析输入白名单包括：原讲稿、各白板的 id/title/board/narration、学习目标、学生自述背景；补讲额外提供学生指出的引文与困惑。没有私有 rubric、判答答案或主线状态写权限。当前这一步是教学风险预测，不是对学生真实掌握的诊断。

模型输出结构：steps 列表，每项含 step_id、marks；每条 mark 包含 quote（板书原文连续片段）、occurrence（第几次出现）、style（circle / underline / highlight）、kind（key_point / pitfall / difficulty）、explanation（短提示）、evidence_quote（原讲稿或板书的内容依据）。每块最多三个，通常零至两个，允许 marks 为空、步骤省略或整份 steps 为空。没有要求每句、每块、每个类别必须出现。不按“必须/不能”等词、加粗、第一个公式或模型自报置信分数兜底决定重点。

程序只做可验证的定位与结构检查：步骤归属、原文逐字匹配、重复出现位置、完整公式/代码、标记不重叠、样式类别、提示格式及依据引用存在。offset 由程序根据 quote 计算，按浏览器 UTF-16 计数，支持 emoji 等字符；模型不直接猜字符偏移。任一校验失败整份标注不显示，不自动改字、模糊匹配、截断条件或回退关键词标记，正文始终可继续学习。引用存在仅证明来源，不能证明教学判断或原讲稿正确。

AttentionText.tsx 只渲染当前阅读单元内完整命中的结构化标记，跨单元锚点不截断为另一个意思；用 rough-notation 绘制模型指定的样式。条件与公式跨 Markdown 片段时合并同一行的实际位置，避免把一个条件画成多个碎圈。仅有 pitfall/difficulty 且有说明时，显示“可能易错 / 理解提示”标签，点击才展开短说明。提示放在未缩放的白板叠加层，展开不挤压原板书；小字注明是教学预测，不能视作学生已经犯错或不会。

### 生成与恢复

- POST /api/sessions/{sid}/boards/{bid}/attention：{detour_id?,retry?}，沿用 Bearer 鉴权，从服务端保存内容构建输入。首次返回202，后台独立生成，模型调用不持有课堂数据库锁。
- GET 同地址，补讲附 ?detour_id=...，读取 pending / completed / failed；尚未分析或来源变化返回404。
- digital_board_attention 按 session_id、board_id、detour_key 缓存；source_hash 包括讲稿、白板、背景、目标、困惑及有效模型 ID。不同补讲独立缓存，刷新不重复收费，内容或配置模型变化后重新分析。
- 重复请求复用 pending/已完成/已失败记录；失败只有明确 retry 才重新生成。前端轮询失败不会无限自动重试。服务重启将遗留 pending 标为失败。迟到结果按任务 id/source_hash 核验，不能覆盖新版本标注。
- 只有标注结果可写入辅助表；不改白板原文、阅读自述、测验、长期画像或课程进度。请求失败保留说明与重试入口，正常学习和语音独立继续。

### 模型与成本

沿用现有供应商地址和密钥，通过独立调用隔离角色。AI_ATTENTION_MODEL 可单独指定当前供应商的模型 ID，留空使用 AI_MODEL；这不代表另训练了一个模型，也不是第二家供应商连接。调用不修改全局 AI_MODEL，避免并发影响授课。用量角色 attention_designer，与授课、板书编排分别记录；账本使用实际调用模型，若未配置该模型单价则费用未知，不按零费用处理。

分开便于减少单次生成负担、单独调提示词/模型/评估，代价是多一次模型调用、费用和标注等待。采用后台生成使正文不等待标注；模型判断仍可能有误，同一模型的不同调用也可能重复同样的错误。当前没有教师标注的评测集，不能宣称达到“完全精准”。

验证：test_board_attention.py 覆盖空标记、严格定位、完整公式、重叠、UTF-16、缓存鉴权、后台锁释放、显式重试、补讲隔离、来源失效及迟到任务；test_usage.py 覆盖独立模型 ID 和实际计量；attention_text.cjs 覆盖无模型标记就不标、保留模型样式、过期/跨句锚点不误贴。另以真实模型检查现有一次函数讲稿，并用普通过渡句验证可以完全不生成标记/易错点/难点。当前实现面向单进程本地课堂，未引入跨 worker 的持久任务队列。


## 取消生成文本的字符上限（版本 4）

版本 4 移除板书生成文本在提示词、工具 schema 和后端校验中的字符上限，覆盖主线板书标题/正文/口语讲解/问题/后台标准/反馈、兼容 focus，以及补讲标题/正文/开场/讲解/返回过渡。教学标注 explanation 也不再限制字符数。继续要求语言清晰简洁、按概念组织，但不因 247 个字符超过旧 220 上限而拒绝整段板书，不裁剪句子或公式。

保留非空、字段类型、原文依据、图编号、数学完整性及标注定位等校验。学生输入、标识符和结构数量约束不属于生成文本字符上限，沿用原有规则；供应商模型输出 token 预算与通用响应大小保护仍独立存在。长内容由固定白板逐句呈现，超出时保留可读字号并在白板内滚动；未展开内容不参与缩放，当前句自动进入视野。公式圈画使用包含滚动偏移的定位，不新增字符截断。

旧失败诊断和历史记录保留原样，点击“重新整理板书”按新规则生成；旧报错不会被伪装成新成功记录。验证覆盖 247 字板书、长标题/讲解/问题/标准、长补讲/过渡、长标注说明及无 maxLength schema，并保留来源不匹配与结构错误的回归检查。


## 生成前约束、生成后校验与自动恢复（版本 5）

版本 5 在不恢复硬字符上限的前提下，加入 backend/board_recovery.py。主线和补讲的初次提示词明确“每块一个要点、board 源文本尽量在 300 个 Unicode 字符左右或以内”，含 Markdown/LaTeX；这是编排软目标，不是可见字数或词数，也不代表最终能装进一页。schema 仍没有 maxLength；长度超出不会使整课不可用。

处理顺序：初次生成并运行原有内容/结构校验 → 检查 board 篇幅 → 局部重排或带错误反馈重新生成 → 对修复结果重新校验。最多两次自动修复，整个生成流程约 75 秒请求预算，单次修复请求超时不超过 20 秒；初次沿用 45 秒超时。超时、密钥、网络和程序异常不按“输出格式错误”盲目重试。

- 有合法但偏长的板书：用 repair_board_step 只处理当前最长块，最多替换为两块，名额受原 6 块主线/3 块补讲上限约束。输入只包含问题块、相邻标题、源讲稿、具体反馈及公开题目，不带私有 rubric。模型精简重复或按意义拆分，不重讲整课、不改课程计划。
- 其他块的内容与 ID 保留；原题和后台标准由程序继承，原图放在拆分后的最后一块，补讲的开场与返回过渡保留。修复不能新增、遗漏或改写原 board/narration 中的完整公式/代码；逐字比较完整表达式集合，允许去掉完全相同的重复表达式。引用、字段及图编号仍执行原校验。自然语言条件的语义完整性仍依赖模型遵守要求，形式校验不能证明教学内容完全正确。
- 初次输出结构/JSON/来源错误，没有合法草稿可用：将具体错误码、步骤、字段等反馈给板书编排模型重新生成辅助板书。不会让授课 Agent 重新授课。
- 修复次数或时间预算用完：若存在合法版本，选取超出目标最少的合法版本作为 long_fallback，完整显示且允许滚动，不截断；若始终没有合法版本，保留失败诊断，并在主白板区域直接展示已提交授课原文。

缓存仍按原规则工作，刷新不会触发新的修复调用。已完成的旧缓存不自动改写；新生成和明确重试使用版本 5 流程。没有新数据库表：digital_boards / digital_board_detours 的 record 新增 recovery，digital_board_runs 历史保留同一安全摘要。摘要记录 target、metric、repair_count、status、stop_reason、各尝试类型/时长/问题字段及长度，不记录原文、学生答案、私有标准或供应商原始错误。

成功白板工具栏可展开“已自动整理 N 次”或“保留完整长板书”，失败时可查看自动恢复过程和原文。修复调用单独记为 board_repair 用量，沿用当前生成 job_id 并带 repair_attempt；初次生成与修复均可能产生费用。所有模型调用仍在课堂锁外，恢复过程不写课程进度、自述掌握、测验成绩或认知画像。

验证：test_board_recovery.py 覆盖无须修复、局部拆分、原题/图/ID 继承、公式保护、具体错误反馈、两次预算、最佳长版本保留、服务故障不盲重试、超时预算、补讲过渡保留、API 缓存/鉴权边界和状态不变；test_tutor.py 覆盖修复请求的单次超时传递。


## 可切换的授课风格（提示词版本 1）

文字聊天课堂与数字人课堂共用三种服务端教学配置：framework（框架式）、guided（引导式）、demonstration（示范式）。默认 framework，旧会话读取时采用该默认值，不追溯修改旧消息。经典固定行列式课堂不提供此切换入口。

完整附加提示词与多轮表达示范保存在 backend/prompts/teacher_framework.txt、teacher_guided.txt、teacher_demonstration.txt；backend/teacher_styles.py 为唯一注册表，计算版本与内容哈希。GET /api/teacher-styles 仅返回这些可公开的教学配置，不包含模型连接、私有评分标准或会话数据。界面可以展开查看实际追加的策略提示词；通用讲解、工具、公式格式和学科范围约束仍然生效。这是运行时提示配置，不是模型微调，也不保证每次都执行完美。

创建聊天会话可传 teacher_style。已存在会话通过标准鉴权事件 chat_teacher_style，payload 为 {"style_id":"guided"} 切换；沿用 expected_revision 与 idempotency_key。切换仅接受内置或当前使用者已保存的风格 ID；自定义教法通过独立创建接口保存，不能借切换事件提交系统提示。切换不调用模型、不新增学生消息、不推进节点、不清空待答题与证据、不重写缓存板书。会话完成或主课堂生成中禁止切换；前端禁用入口，后端同样校验。

每次聊天 job 冻结所选风格元数据，授课请求实际追加对应提示词。授课消息、交接任务和调用成本记录保存 ID、版本、提示哈希，可追查历史。测评与教学安排不采用教师风格提示。新发起的补讲读取当时会话所选老师并冻结；进行中的补讲继续使用发起时老师，返回主线位置不变。板书编排保留原讲稿的教学顺序、例子及引导问题，不给已缓存板书重新套风格。

实验建议：先固定模型、目标、背景与课堂场景，只切换教法；比较内容正确性、前置概念解释、引导与示范是否适当，以及后续独立作答表现。当前的接口与版本记录用于支持人工对比，不声称已实现随机分组、正式 A/B 实验或学习效果提升。


## 使用者自定义教学风格

入口：教学风格下方“创建我的老师”。原生模态弹窗填写名称、教学思路、教学示例，三项必填；“保存并使用”先持久化配置，再沿用课堂事件切换。关闭弹窗不保存；保存失败保留草稿，重试沿用同一幂等标识，修改草稿后使用新标识。保存本身不调用模型。

自定义配置存储在主课堂 SQLite 的 custom_teacher_styles 表，不修改内置提示词文件。每条配置有随机 custom_ ID、版本、实际编译提示的哈希以及原始三个字段。当前版本提供创建、选择、查看，不提供覆盖式编辑或删除。界面使用纯文本显示名称和提示词，不执行用户示例中的HTML或脚本。

自定义列表通过 X-Teacher-Style-Token 做匿名凭据隔离：浏览器保存32字节随机凭据，服务端只在独立列保存其哈希。GET /api/teacher-styles 不附凭据仍只返回三个内置风格；附带凭据时返回内置及该凭据拥有的自定义配置。POST /api/teacher-styles 接收 name、approach、examples、idempotency_key，要求该凭据；名称80、思路6000、示例10000字符是输入保护，不是板书输出限制。重复保存同一请求返回原配置，改变内容但复用标识返回409。

创建会话或提交 chat_teacher_style 时，客户端同时携带正常课堂/学习空间凭据和独立的风格凭据；后端校验归属后把完整教法快照保存到会话私有 teacher_style_config，公开快照仅返回老师元数据。每个生成 job 再冻结一份定义，授课模型使用冻结的实际提示，不查询可变全局配置。恢复已有会话只需要课堂凭据即可继续使用已保存的教法，不依赖内存注册表；新课堂选择该自定义风格仍需原浏览器的风格凭据。清除浏览器存储会丢失自定义风格库入口，不影响已有课堂中的快照。

文字课堂与数字人课堂在同一服务地址下共用风格凭据与列表；刷新或窗口重新获得焦点时更新列表。自定义提示只应用到授课及新补讲，评分模块保持独立。补讲冻结发起时教法，自动编排修复不重复传递整套自定义示例。自定义内容只能影响讲法，不能修改课程范围、工具协议、评分权限或公开私有标准；程序仍负责事件校验与状态修改。


## 豆包朗读与音色切换（2026-11-27）

左侧“朗读音色”提供晓晓与八种豆包音色，稳定 ID 与模型版本见 `backend/speech_providers.py` 的 `VOICES`；页面按后端模型版本显示 2.0 或 3.0。`GET /api/digital-human/voices` 只返回名称、供应商、配置可用性和默认 ID，不包含密钥。“可用”表示本机已配置，不代表实时探测了供应商授权。浏览器偏好保存在 `aiteacher.digital.voice.v1`，无偏好时采用后端 `TTS_DEFAULT_VOICE`。切换会取消正在播放和排队的旧音色，之后可重听当前内容。

普通消息、主线白板、补讲白板及回归过渡的 speech 请求都透传可选 `voice_id`。服务端只接受白名单音色，仍只朗读属于当前授权会话的已保存内容，不允许通过音色参数指定外部 URL 或提交任意文字。

后端 `.env` 配置 `DOUBAO_TTS_API_KEY`；部署时不要复制到前端或提交 Git。四郎、熊二、唐僧、悬疑解说、孙悟空、天才同桌、少年将军是 TTS 3.0，使用官方 `https://voice.cn-beijing.volces.com/api/v3/text-to-speech/{voice_id}/streaming`，模型 `doubao-seed-tts-3.0`，不能套用 TTS 2.0 的资源参数。妩媚御姐（`ICL_uranus_zh_female_wumeiyujie_tob`）是 TTS 2.0，走 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`，资源为 `seed-tts-2.0`。`backend/speech_providers.py` 按音色模型路由，分别处理 3.0 的 ready/audio/final/error 事件和 2.0 的 code/data 帧及 20000000 结束码；只有收到正常结束且音频有效才缓存、播放，部分音频后失败不会误报成功。权限、限流、格式与网络错误返回脱敏提示及请求编号，不自动替换成另一种声音。

四郎正确 ID 为 `multi_male_silang_v3_uranus_bigtts`；输入中多出的 `api` 前缀已通过实测纠正。熊二为 `multi_male_xionger_v3_uranus_bigtts`。云端语音无需安装 Edge/数字人 Python 环境；角色素材仍单独配置。阿里云尚未接入，等待配置。

验证：`python -m unittest tests.test_speech_providers tests.test_digital_human tests.test_digital_board tests.test_math_speech -q`；`node tests/digital_narrator.cjs`；`npm run build`。已分别用八种豆包音色做简短真实合成，未将测试音频或密钥提交仓库。


## Markdown 表格渲染修复（2026-11-27）

统一 `RichText` 组件支持 Markdown 表格：表头、数据行、对齐、单元格公式、行内代码和原文高亮；模型 HTML 仍按文本转义。`markdownTables.ts` 以原始字符位置识别表格，忽略代码和公式内部的竖线，并支持真实换行、CRLF 和正文二次转义换行。格式不完整的片段保留原文。

`whiteboardBlocks` 把完整表格作为一个不可拆分的展示单元，避免逐句讲授将表头、分隔行和数据行拆散；主线、补讲、注意力高亮模式和文字课堂共用。表格过宽时可横向滚动，原始 Markdown 与标注坐标不改写，旧课程刷新即可生效。文字对话正文改用 div，避免将块级表格放在 p 内。

回归：`node tests/rich_text.cjs`、`node tests/whiteboard_blocks.cjs`、`node tests/attention_text.cjs`、`npm run build`；已用数据库中 y=2x+1 的实际板书验证生成 4 列、3 行数据。桌面目视检查工具因无法确认浏览器 URL 停止，未完成目视验收。


## 音频驱动的板书同步（2026-11-27）

主线与补讲的“重听”默认开启句子/板书块跟读。浏览器按当前分块提交 UTF-16 原文范围；后端只从已授权会话读取保存的 board/narration，验证范围连续覆盖正文，不接受客户端传入讲稿或评分标准。原 MP3 接口保持兼容；带 synchronized=true 与 units 的请求返回音频 Base64、分段数量和当前块的 cue。

`backend/speech_sync.py` 调用独立 speech_alignment 模型角色：将连续讲稿片段对应到一个或相邻多个板书块，输出精确且唯一的 start_quote 锚点。程序校验顺序、覆盖、原文引用和完整讲稿保留；结构不合格最多修复一次。只有一个板书块时直接关联整段讲稿。模型不生成时间戳，不改写语音内容。语义对齐结果进程内缓存 1 小时；失败短暂缓存 30 秒，降级为保留声音、全文手动阅读，不能用字符比例猜测同步位置。模型调用记录在用量台账的 speech_alignment 角色下，TTS 字符费用仍以供应商账单为准。

按语义组切分原讲稿后，复用公式转读和最多 240 字符音频片段。豆包 3.0 开 enable_subtitle，收集 alignment.words；2.0 在 audio_params 开 enable_subtitle，收集 sentence.words。音频和真实秒级时间戳成包缓存，和普通 MP3 缓存分开，不跨音色混用。晓晓没有此链路的词时间戳，使用同一语义片段实际播放边界作为块级同步，界面不宣称逐字精度。

前端 `DigitalNarrator` 用 Audio.currentTime 和 requestAnimationFrame 触发 cue，而非定时估字数。读到片段首词才展开对应块，在词时间窗口内显示蓝色跟读背景；重点红圈/划线仍完全来自原教学标注 Agent。不可拆分的表格、公式整体高亮。可合并共同讲述的相邻块；首版不做公式内部字符级定位。下一张白板和课程继续仍需学生确认，听完不记录理解或掌握。

每次只预取下一片段，预取完成不能推进当前画面。暂停保留当前音频位置与文字，继续从原位置播放；准备中可停止，重听从当前板书开头重新同步。切音色、手动下一句/看全文、提问、翻页、补讲切换、恢复其他课或卸载时取消当前播放与预取，以代次和步骤 ID 拒绝晚到回调。补讲返回主线保留原阅读锚点，衔接过渡单独朗读。

验证：49 项相关 Python 检查，加上 digital_narrator、attention_text、rich_text、whiteboard_blocks 的 Node 回归与生产构建。使用已保存的 y=2x+1 讲稿实际调用语义对齐和豆包，两块板书分别返回真实时间窗；2.0 妩媚御姐也验证返回时间戳。首次播放可能先等待语义对齐，重听可复用缓存；并非已完成浏览器目视与听感验收。


## 统一独立测评 Agent（2026-11-27，板书版本 6）

职责链路：授课 Agent → assessment_request → 测评 Agent → 白板呈现与作答 → 测评 Agent 判答 → 学习证据与教学安排 Agent。

- `backend/assessment_agent.py` 是文字与白板共用的独立测评实现，统一提示词、工具结构、判答结论及职责边界。不是板书编排模型换一个显示名称。
- 授课输出必须包含结构化 `assessment_request`：objective（希望检查什么）、covered（实际讲过什么）、prerequisites（必要前置，未知明确说明）、reason（请求理由）。授课风格不能覆盖不自行出题的约束；授课可演示已解例题，不设计学生待答练习或评分标准。
- `digital_board.py` 的新编排 schema 只包含标题、board、narration、source_quote、visual_ids；程序拒绝编排输出中的 question/rubric。旧板书仍可阅读，旧题不再展示或作答。
- `backend/board_assessment.py` 是呈现适配层，不自带另一套出题/判答模型。小节末页请求出题，交接信息来自服务端保存的讲稿、授课请求、整个小节板书、课堂背景与历史证据。禁止前端上传题目或评分标准。
- `digital_board_assessments` 按会话与白板缓存测评任务；私有题目对象和 rubric 只在后端保存，公开输出白名单去除答案。题目失败可显式重试，不让授课模型或板书模型接管出题。
- 判答在 `digital_board_answers` 留存尝试；有效回答进入 session.evidence，not_answer 与主动跳过不记成错误或正确证据。测评反馈经 `assessment → planner` 交接，安排 Agent 的 context 可直接读取。答错可重答或点“请老师补讲”，正确或明确跳过后再由学生继续课程。
- 模型调用在数据库锁外执行。回答、学习证据、交接记录在同一数据库事务提交；幂等键避免重复记账。生成期间课堂 revision 变化则拒绝将迟到结果写进教学状态，避免覆盖新消息或串课。
- 白板请求会增加 session revision；前端在出题、判答完成后刷新课堂快照。阅读继续、语音播完和单题答对都不等同长期掌握。程序结构能约束调用归属与数据流，题目质量和自然语言是否完全遵守教学边界仍需评测。

接口（均使用课堂 Bearer 凭据）：

- `GET /api/sessions/{sid}/boards/{bid}/assessment`：读取独立测评任务，pending 返回 202。
- `POST /api/sessions/{sid}/boards/{bid}/assessment`：`{retry?: boolean}`；只从当前已保存讲稿构建请求。
- `POST /api/sessions/{sid}/boards/{bid}/answers`：`{assessment_id, step_id, answer, skip, idempotency_key}`；禁止沿用旧的无测评任务答题请求。

验证：`tests/test_assessment_agent.py` 覆盖共享实现、职责边界、结构化交接、白板接题、私有标准隔离、幂等、错误恢复、旧题退役、错题重试、证据回传以及课堂变化时丢弃迟到结果。

课前诊断与调度直接安排的测评同样接入白板：`AssessmentBoard.tsx` 展示现有 assessment 消息及 pending_question，支持选择题点选或输入答案。作答走原 chat_message → assessment 路由，使用同一测评实现；不重复出题、不复制私有 rubric。学生明确选择先讲解时暂停该题，不计错误。
