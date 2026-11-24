> 范围说明：旧版 mode=planner 的受限课程安排协议；“只支持行列式”的限制不适用于 mode=chat。 当前系统见 [系统说明](IMPLEMENTATION.md)，默认开发入口见 [通用 Agent 协议](CHAT_AGENTS_DEVELOPMENT.md)。文内测试数量为历史快照。

# 教学安排 Agent 开发说明

## 职责与边界

教学安排 Agent 澄清目标、整理学生自述、生成待确认计划，并依据诊断、授课和练习反馈选择下一步。模型通过原生 function calling 返回一个工具请求；后端校验并执行，不从自然语言中解析状态跳转。

当前只执行三阶行列式课程。其他课程可以生成不可执行的计划草案；确认按钮禁用，后端也拒绝启动。学生基础与偏好是未验证的自述，独立掌握仍由原有精确计算与测评模块判定。

## 数据与工具

`backend/planner.py` 管理 profile、plan、history、job、return_phase 和对话摘要。任务使用独立 job id；新请求替代旧请求后，迟到的结果不执行。公开接口隐藏内部 job 和原始上下文，展示最近十二次执行记录。

工具统一返回 message、reason，后端拒绝未知工具、未知字段与越界参数。

| 工具 | 额外参数 | 作用 |
| --- | --- | --- |
| ask_student | options | 澄清需求或请求选择 |
| propose_plan | goal、course_id、prior_knowledge、time_minutes、preference、steps | 提出计划，等待学生确认 |
| start_diagnostic | 无 | 开始现有三题诊断 |
| start_teaching | topic | 调用授课 Agent，继承现有分段会话 |
| return_to_classroom | resume_teaching | 回原课堂，可恢复暂存授课 |
| start_assessment | 无 | 使用现有未通过的新题或规则辨析 |
| end_session | 无 | 学生明确请求结束时生成报告 |

`allowed_tools` 按当前进度动态限制模型可见工具，`validate` 再次校验。`execute` 只负责调用现有领域模块，不生成分数。每次执行保存参数、简短依据、来源、结果阶段；依据是可公开的安排说明，不是模型内部推理。

## 请求与执行流程

前端创建课堂时 POST `/api/sessions`，请求体为 `{"mode":"planner"}`。无请求体仍创建传统课堂，兼容已有客户端。

事件 `planner_message` 接收 text，显式选择体验课程时附 select_supported_course。事件 `confirm_learning_plan` 必须提交当前 plan_id。诊断完成、讲授完成、连续检查困难、题目完成会自动请求重新安排。

`backend/app.py` 的 arrange_classroom 在后台调用模型。模型请求在数据库锁外进行；执行时核对当前阶段、job id 和 pending 状态，以副本执行成功后原子保存状态及事件。模型失败或工具被拒绝时使用明确标记的规则回退。重启后的未完成任务要求学生重新发起，保留课堂记录。

`backend/tutor.py` 的 call_tool 要求且只接受一个 tool_call，解析 JSON 参数；普通散文不能触发执行。模型配置沿用现有环境变量，密钥只留后端。

## 前端

PlanningPanel 展示能力范围、澄清选项、计划、确认按钮与执行历史。聊天中“排”标识教学安排 Agent；可切换提问对象，已有课堂可通过“调整教学安排”接入。计划状态下提问统一交给安排 Agent。后台结果沿用消息 pending 轮询恢复。

## 验证与扩展

`tests/test_planner.py` 覆盖确认门槛、诊断到授课、范围保护、非法工具与参数、任务替代、公开投影和结束意图限制。完整回归：`python -m unittest discover -s tests -q`；前端构建：`npm run build`。

若扩展新课程，应先增加可执行课程注册、知识点与授课材料、题目验证和测评工具，再开放 course_id。目前计划步骤是教学意图，执行仍由每次反馈后的决策决定；尚无通用知识生成与验证流水线，也未做跨课程的长期认知建模。

在配置了真实模型的目录运行离线测试前，需在当前 PowerShell 进程设置 `$env:AI_API_KEY=''; $env:AI_API_URL=''; $env:AI_MODEL=''`，避免本机 .env 使讲授保持远程生成状态；这些设置不修改 .env 文件。真实模型联调另行运行。
