"""Safe diagnostics: never persist exception text, prompts, or provider bodies."""
class TeachingError(ValueError, RuntimeError):
    def __init__(self, stage, code, message, **details):
        super().__init__(message)
        self.stage, self.code, self.message, self.details = stage, code, message, details


def diagnostic(exc, agent, incident_id):
    if isinstance(exc, TeachingError):
        return dict(id=incident_id, agent=agent, stage=exc.stage, code=exc.code,
                    message=exc.message, details=exc.details)
    return dict(id=incident_id, agent=agent, stage='workflow', code='internal_error',
                message='教学流程内部处理异常。', details={'exception_type':type(exc).__name__})


def failure_text(failure):
    agents={'planner':'教学安排 Agent','lecturer':'授课 Agent','assessment':'测评 Agent','auto':'教学调度'}
    stages={'configuration':'模型配置','provider_request':'模型请求','response_parse':'模型响应解析','tool_parse':'工具参数解析','schema_validation':'结果格式校验','workflow':'教学流程处理'}
    return (f"本次处理失败：{agents.get(failure['agent'],'教学调度')} · {stages.get(failure['stage'],'教学流程处理')}。"
            f"{failure['message']} 错误码：{failure['code']}；诊断编号：{failure['id'][:8]}。"
            '学习记录已保留，可重新发送上一条消息。')
