"""Persistent segment/check state. Formative success is never mastery."""
from uuid import uuid4
from .teaching_content import PLANS, UNITS
from .math_engine import number


def emit(state, text, **kwargs):
    from .lesson import message
    return message(state, text, **kwargs)


def initialize(task, state, use_model):
    task["protocol"] = 2
    task["session"] = {"segment_index": 0, "segment_total": len(PLANS[task["topic"]]), "segment_status": "generating", "passed_segments": [], "checks": [], "variant": 0, "attempts": 0, "open_questions": [], "resolved_questions": [], "used_example_ids": [], "completed_points": [], "resume_point": {"phase": task["return_phase"], "problem_id": state.get("problem_id"), "step_count": len(state.get("steps", []))}, "latest_check_result": None}
    start_segment(task, state, use_model)


def unit(task):
    session = task["session"]
    return UNITS[PLANS[task["topic"]][session["segment_index"]]]


def start_segment(task, state, use_model, remedial=False):
    s = task["session"]
    spec = unit(task)
    s["generation_id"] = str(uuid4())
    s["check_id"] = str(uuid4())
    s["generation_mode"] = "remedial" if remedial else "initial"
    s["segment_status"] = "generating" if use_model else "awaiting_check"
    task["status"] = "pending" if use_model else "ready"
    task["scheduled"] = False
    s["used_example_ids"].append(f"{PLANS[task['topic']][s['segment_index']]}:{s['generation_mode']}:{s['variant']}")
    content = spec["remedy"] if remedial else spec["lesson"]
    m = emit(state, f"第{s['segment_index']+1}段 · {spec['title']}\n\n{content}", agent="lecturer", kind="lecture", task_id=task["id"], segment_id=s["generation_id"], status="pending" if use_model else "local")
    task["message_id"] = m["id"]
    s["lecture_message_id"] = m["id"]


def settle_generation(task, source):
    task["status"] = "ready"
    task["source"] = source
    if task.get("session", {}).get("segment_status") == "generating":
        task["session"]["segment_status"] = "awaiting_check"


def projection(task):
    if not task or "session" not in task:
        return task
    public = {k:v for k,v in task.items() if k not in ("scheduled",)}
    s = task["session"]
    spec = unit(task)
    check = spec["checks"][s["variant"]]
    visible_check = {k:v for k,v in check.items() if k not in ("answer", "explanation")}
    visible_check["id"] = s["check_id"]
    public["segment"] = {"index": s["segment_index"], "total": s["segment_total"], "title": spec["title"], "objective": spec["objective"], "status": s["segment_status"], "check": visible_check if s["segment_status"] in ("generating", "awaiting_check") else None}
    public["segments"] = [{"title": UNITS[key]["title"], "passed": i in s["passed_segments"]} for i,key in enumerate(PLANS[task["topic"]])]
    return public


def summaries(state):
    return [{"id":t["id"], "title":t["title"], "status":t["status"], "completed_points":t["session"]["completed_points"], "checks":t["session"]["checks"], "open_questions":t["session"]["open_questions"], "resolved_count":len(t["session"]["resolved_questions"]), "formative":True} for t in state.get("teaching_tasks", []) if t.get("session")]


def submit_check(state, task, payload, use_model):
    s = task["session"]
    if task["status"] != "ready" or s["segment_status"] != "awaiting_check":
        raise ValueError("当前理解检查尚未就绪，或已经提交。")
    if payload.get("task_id") != task["id"] or payload.get("check_id") != s["check_id"]:
        raise ValueError("理解检查已经更新，请重新加载后作答。")
    check = unit(task)["checks"][s["variant"]]
    answer = payload.get("answer")
    if check["kind"] == "number":
        parsed = number(answer)
        correct = parsed == number(check["answer"])
        display = str(parsed)
    else:
        if type(answer) is not int or answer not in range(len(check["choices"])):
            raise ValueError("请选择一个答案。")
        correct = answer == check["answer"]
        display = check["choices"][answer]
    s["attempts"] += 1
    result = {"task_id": task["id"], "segment_index": s["segment_index"], "segment_title": unit(task)["title"], "check_id": s["check_id"], "prompt": check["prompt"], "answer": display, "correct": correct, "attempt": s["attempts"], "formative": True}
    s["checks"].append(result)
    s["latest_check_result"] = result
    emit(state, display, role="student", kind="check_answer", task_id=task["id"])
    emit(state, ("本段理解检查通过。" if correct else "这次还需要再看一下。") + check["explanation"] + " 这是随堂检查，不作为独立掌握证明。", agent="assessment", kind="check_feedback", task_id=task["id"])
    if correct:
        s["segment_status"] = "passed"
        if s["segment_index"] not in s["passed_segments"]:
            s["passed_segments"].append(s["segment_index"])
            s["completed_points"].append(unit(task)["title"])
        if len(s["passed_segments"]) == s["segment_total"]:
            s["segment_status"] = "completed"
            emit(state, "本轮分段讲授与随堂检查已结束，交回调度器安排练习。检查通过不等于独立掌握。", agent="lecturer", kind="handoff", to_agent="scheduler", task_id=task["id"], status="receipt")
    else:
        if s["variant"]+1 >= len(unit(task)["checks"]):
            s["segment_status"] = "needs_review"
            emit(state, "本段连续检查尚未通过，先保留待复习记录。你可以提问，或暂存讲授回到练习；不会自动跳到下一要点。", agent="scheduler", kind="announcement", task_id=task["id"])
        else:
            s["variant"] += 1
            emit(state, "当前要点还需要补充。请授课 Agent 换一种解释，之后用不同问题再检查。", agent="scheduler", kind="handoff", to_agent="lecturer", task_id=task["id"])
            start_segment(task, state, use_model, remedial=True)
    return {"correct": correct, "formative": True}


def next_segment(state, task, use_model):
    s = task["session"]
    if s["segment_status"] != "passed":
        raise ValueError("请先通过当前要点的理解检查。")
    s["segment_index"] += 1
    s["variant"], s["attempts"], s["latest_check_result"] = 0, 0, None
    emit(state, f"当前要点检查通过，安排第{s['segment_index']+1}段讲授。", agent="scheduler", kind="handoff", to_agent="lecturer", task_id=task["id"])
    start_segment(task, state, use_model)


def register_question(task, question, message_id):
    if task and task.get("session"):
        s = task["session"]
        s["open_questions"].append({"id": message_id, "text": question, "segment_index": s["segment_index"], "status": "awaiting_answer"})


def question_answered(task, message_id, stale=False):
    if task and task.get("session"):
        for q in task["session"]["open_questions"]:
            if q["id"] == message_id:
                q["status"] = "needs_followup" if stale else "answered"


def resolve_question(task, question_id):
    if not task or not task.get("session"):
        raise ValueError("当前没有授课会话。")
    s = task["session"]
    q = next((q for q in s["open_questions"] if q["id"] == question_id), None)
    if not q or q["status"] == "awaiting_answer":
        raise ValueError("请等待回答后再确认疑问已解决。")
    s["open_questions"].remove(q)
    s["resolved_questions"].append({**q, "status": "student_confirmed"})


def context_key(state):
    from .lecturer import current_task
    task = current_task(state)
    if state["phase"] == "lecture" and task and task.get("session"):
        return ("lecture", task["id"], task["session"]["segment_index"])
    return (state["phase"], state.get("problem_id"), len(state.get("steps", [])), state.get("factor"))


def upgrade_legacy(state):
    from .lecturer import current_task
    task = current_task(state)
    if state["phase"] == "lecture" and task and not task.get("session"):
        emit(state, "已升级为分段授课。保留原讲稿，从第一个要点开始收集随堂理解证据。", agent="scheduler", kind="announcement", task_id=task["id"])
        initialize(task, state, use_model=False)
        return True
    return False


def pause(state, task):
    s = task["session"]
    if s["segment_status"] == "generating":
        settle_generation(task, "local")
    s["generation_id"] = str(uuid4())
    for m in state["messages"]:
        if m.get("task_id") == task["id"] and m.get("status") == "pending":
            m["status"] = "local"
    for q in s["open_questions"]:
        if q["status"] == "awaiting_answer":
            q["status"] = "needs_followup"
    task["status"] = "paused"
    state["phase"] = task["return_phase"]
    state["active_teaching_task"] = None
    emit(state, "已暂存授课进度和待解决疑问，恢复原课堂。尚未完成的要点保留，之后可继续；不认定掌握。", agent="scheduler", kind="handoff", to_agent="student", task_id=task["id"])


def resume(state, task):
    if state["phase"] not in ("guided_practice", "independent_assessment", "rule_check", "rule_remedy") or task["status"] != "paused":
        raise ValueError("当前不能恢复这项授课任务。")
    task["return_phase"] = state["phase"]
    task["session"]["resume_point"] = {"phase": state["phase"], "problem_id": state.get("problem_id"), "step_count": len(state.get("steps", []))}
    if state["phase"] == "independent_assessment" and not state.get("problem_done"):
        state["helped"] = True
    state["phase"], state["active_teaching_task"], task["status"] = "lecture", task["id"], "ready"
    emit(state, f"恢复「{task['title']}」第{task['session']['segment_index']+1}段，保留已有检查与疑问记录。", agent="scheduler", kind="handoff", to_agent="lecturer", task_id=task["id"])
