# 数字人课堂（并行实验入口）

入口 `/digital-classroom`；原来的 `/`、文字课堂、课程管理和教学事件语义保持不变。课程中心和文字课堂页头提供新标签页入口。

## 职责

`DigitalClassroom.tsx` 是独立展示层，仍使用 `/api/sessions` 和已有 `chat_*` 事件。安排、授课、测评、结构化计划、任务交接与测评证据均由现有后端产生；Open-LLM-VTuber 的闲聊 Agent 不参与教学。数字人展示层新增辅助板书编排与本步判答调用，将已经提交的授课正文整理成短步骤；原教学 Agent 和主课程推进逻辑不变。

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

- `GET /api/digital-human/status`：检查角色文件和语音 Python 是否存在，不返回本地路径或凭据。
- `GET /digital-assets/core.js`、`GET /digital-assets/models/{path}`：限定角色目录、扩展名和真实路径，禁止任意文件读取。
- `POST /api/sessions/{sid}/digital-speech`：沿用会话 Bearer 鉴权，请求只有 `message_id`、`chunk`，不接受任意外部文字。服务端从已授权会话查找可播报消息。
- 成功返回 MP3 和 `X-Speech-Chunks`，配音通过隔离 Python 进程内的 Edge TTS 生成，会发送待配音正文至微软语音服务。公式转换在服务端执行，原课堂正文不变；公式批量解析最多 8 秒，生成读法按原始消息缓存，重听不需要每段重复解析。
- 生成在数据库锁外进行；40 秒超时，最多两个并发，16 MiB 进程内音频缓存。未增加持久化音频库。页面取消后，已开始的子进程可能运行至本次生成结束或超时，但其结果不会继续播放。
- 缺环境、服务失败、繁忙、播放权限等错误只影响声音；板书、学习状态及教学反馈仍保留。重听可重试。
- Edge TTS 是独立的在线语音服务，没有接入课程 LLM token 用量计费；当前不估算语音成本。

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
- 角色外观不等于角色原声：所有形象仍用当前晓晓配音，教学风格仍沿用原 Agent。

素材目录在独立 Open-LLM-VTuber 下，不复制进代码仓库或前端 dist。该功能只在本地技术体验范围验证；初音角色不适用 Live2D 原创角色的一般商业使用许可，商业发布前需单独确认 Crypton/Piapro 的角色使用条件。页面保留来源和版权说明。

官方资料：
- https://www.live2d.com/en/learn/sample/hatsune-miku/
- https://www.live2d.com/en/learn/sample/momose-hiyori-video/
- https://www.live2d.com/en/learn/sample/model-terms/
- https://piapro.jp/license/pcl/summary

## 逐步互动板书（2026-11-26）

授课不再默认铺开整段消息。`StepBoard.tsx` 展示当前一小步，黄色标出本步重点，原对话、完整讲稿和任务交接折叠保留。每步包含短板书、口语讲解、一道理解题和原文依据；公式仍由现有 KaTeX 渲染，图仍复用原文已有的 TeachingDrawing，未生成新的可执行代码。

数据流：已提交的 lecturer 消息 → `backend/digital_board.py` 的 `design_step_board` 工具调用 → 字段和长度/原文引用/图 ID 校验 → 持久化 → 前端逐步展示。通常 2–4 小步，硬上限 6；每步板书 220 字、讲解 400 字、问题 160 字以内。不是按字数分页。结构校验不能证明内容正确，当前仍依赖模型编排和判答。

播放只请求当前小步的 narration 和 question。最后一段声音结束后显示答题区并停下，不自动进入下一步；取消或播放失败不会触发完成回调。学生也可以点“我想自己看，显示问题”。正确后手动进入下一小步；答错给提示重试，求助发给原授课 Agent。明确跳过会标记“稍后再练”，允许继续，也保留补答入口，不记为答对。

板书小步和课程计划节点是两层进度。小步答对不写长期掌握，也不自动发送 `chat_continue`。全部小步答对或明确跳过后，学生点击“我确认理解，继续课程”，才沿用原继续事件。文本聊天中的明确指令仍由原调度逻辑处理，因此这些界面约束不是后端课程权限系统。

### 持久化与接口

同一课堂 SQLite 新增 `digital_boards`、`digital_board_answers` 表。板书按 `(session_id, source_id)` 缓存，记录源文本哈希、结构版本和生成状态；答题记录带幂等键，保留尝试。源文在原 session 中不改写。恢复时读取已完成的最新答题反馈；阅读位置另存浏览器 `aiteacher.digital.board.view.<sid>.<sourceid>`，不能越过最早未答步骤。浏览器清理后位置可能回到首步，服务端答题记录仍在。

- `GET /api/sessions/{sid}/boards/source/{message_id}`：读取缓存板书和反馈。
- `POST /api/sessions/{sid}/boards`：`{message_id,retry?}`，只接受当前凭据可访问的已提交授课消息；生成中返回 202，失败可重试，原文仍能展开。
- `POST /api/sessions/{sid}/boards/{board_id}/answers`：`{step_id,answer,idempotency_key,skip}`。工具 `check_board_answer` 只接收当前板书、问题、后台答案标准和学生答案。公开响应不含私有 rubric；返回 correct/partial/incorrect/uncertain/not_answer，明确跳过由程序记录 skipped，不调用模型。
- `POST /api/sessions/{sid}/boards/{board_id}/speech`：`{step_id,chunk}`，服务端查表生成配音，不接受任意外部文本，不播报后台标准或未来步骤。

所有接口沿用 Bearer 鉴权，模型/配音请求均在数据库锁外。重复创建缓存复用；重复提交同一幂等键不重复判答。重启将遗留 pending 标记为失败，允许重试。当前为单进程实现；没有多 worker 作业协调。板书生成失败只影响辅助呈现；主课堂和原文保留。网络中断后的后台生成可能完成，重开可读取缓存。

编排额外产生一次模型调用，未缓存重试也可能产生费用；每次非跳过答题另产生一次判答调用。用量以 `board_designer`、`board_check` 角色关联原 session，独立计量，不作为免费步骤。Edge TTS 仍是单独的在线服务。

验证：`python -m unittest discover -s tests -p test_digital_board.py -v` 覆盖源引用、字段限制、图引用、鉴权、缓存、幂等、私有标准隔离、失败恢复、跳过和配音范围。`node tests/digital_narrator.cjs` 另外验证板书配音路由、最后音频完成才开放问题、取消不回调。

### 可点选的选择题

`boardQuestion.ts` 将已保存题目中连续的 A/B/C 等标准选项拆成题干与选项卡片，保留原 Markdown 和公式。公式及代码内部的字母不作为选项标记；不完整或无法可靠拆分的题目仍保留文字作答。单选使用原生 radio，题干明确标注多选时使用 checkbox，支持键盘操作。点选只更新草稿，点击“检查这一步”才提交所选字母和选项原文，沿用原判答接口；答错可重选，答对锁定，恢复已提交回答时显示原选择。未选时不能提交。

`node tests/board_question.cjs` 验证当前旧题兼容、公式/代码隔离、常见标签、多选及选择恢复。
