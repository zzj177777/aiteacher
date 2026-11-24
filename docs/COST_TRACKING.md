# 模型调用用量与估算成本

## 记录内容

backend/usage.py 使用 ContextVar 将 session_id、job_id、agent 关联到调用。tutor.complete / call_tool 每次结束独立落库 data/model_usage.sqlite3 的 model_calls 表：调用ID、时间、模型、角色、耗时、状态、错误码、供应商 usage 的输入/输出/总token及缓存命中/未命中token、估算费用和单价快照。未返回usage的字段为未知，不使用字符数猜测。

同一会话的安排、授课、测评、选中解释及旧模式调用都关联计量；无会话的开发调用记录 session_id=null，不计入任一课堂。数据库路径可用 AITEACHER_USAGE_DB 覆盖。

记录独立于课堂事务：模型返回后JSON解析失败仍保留usage，整轮回滚、结果过期或学生结束课堂也不删除调用。completed只代表模型调用和适配器解析完成；之后的业务字段校验失败可导致课堂失败，应通过job_id关联课堂诊断。未返回响应的网络失败可能已产生供应商费用，记用量/费用未知。进程被强制终止时，尚未结束的调用当前不能完整记录，不是计费系统。

不保存密钥、接口认证头、请求/回复正文。账本不是供应商账单，记录启用前的历史无法追溯。

## 单价配置

在服务器.env填写当前账户和模型价格，单位每百万token。例如以下是虚构测试价格，不是DeepSeek报价：

```ini
AI_PRICE_MODEL=your-exact-model-name
AI_PRICE_CURRENCY=CNY
AI_INPUT_PRICE_PER_MILLION=2
AI_OUTPUT_PRICE_PER_MILLION=8
AI_CACHE_HIT_PRICE_PER_MILLION=0.5
```

模型名必须与调用时AI_MODEL完全一致；未配置/不匹配/非法单价不计价。可选缓存命中价：有命中用量和该价格时按命中/未命中分别算；否则所有输入按标准输入价估算，并记录standard_input_rate。prompt_tokens包含缓存命中输入，不重复累计。

费用=(未命中输入token×输入价+命中token×命中价+输出token×输出价)/1,000,000。没有缓存差价时用输入总量。按调用时价格固化，改价不追溯重算；不同币种分组相加、不混加。输出推理token若已包含在供应商completion_tokens内，不重复计费。固定费用、优惠、税费、账户实际结算均未处理。

示例：1000输入、其中400命中、200输出，使用上述虚构价格，估算为0.003 CNY。重启服务后.env配置生效。不要把实际API密钥写入本文。

## 展示与接口

侧栏“模型用量与估算成本”显示调用次数、输入输出token、失败数、累计模型调用耗时、已知估算费用和未计价/用量未知次数。可刷新查看解释助手等辅助调用；旧课堂显示0次而不是声称以前免费。

GET /api/sessions/{sid}/usage 使用原会话Bearer凭据，返回汇总及最近30次调用。查询覆盖该会话完整账本，明细只返回最近30条；调用记录没有学生文本。当前没有全站管理员成本面板或预算拦截。
