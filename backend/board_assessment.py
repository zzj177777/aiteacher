"""Whiteboard adapter for the independent assessment agent.

Only server-owned lecture context is handed over. Model work runs outside the
database lock; question/feedback handoffs and learning evidence commit together.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import assessment_agent, chat_classroom as chat, usage
from .board_diagnostics import failure
from .errors import TeachingError


class AssessmentRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    retry: bool = False


class AnswerRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    step_id: str = Field(min_length=1, max_length=100)
    assessment_id: str = Field(min_length=1, max_length=100)
    answer: str = Field(default='', max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    skip: bool = False


def public(record):
    # Explicit whitelist: never serialize the private question/rubric or request.
    result = {k: record[k] for k in ('id', 'agent', 'status', 'step_id', 'source_message_id',
                                   'message', 'question', 'objective', 'error', 'diagnostic') if k in record}
    return result


def ready(state):
    if state.get('completed'): raise HTTPException(409, '本次学习已结束，不能再安排测评。')
    if (state.get('job') or {}).get('status') == 'pending':
        raise HTTPException(409, '课堂正在生成内容，请稍后安排测评。')


def source_for(state, board):
    source = next((m for m in state['messages'] if m['id'] == board['source_message_id'] and m['agent'] == 'lecturer'), None)
    if not source: raise HTTPException(404, '测评所需的授课原文不存在。')
    return source


def register_routes(app, connect, lock, read_session, token_value, board_for):
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS digital_board_assessments('
                   'id TEXT PRIMARY KEY,session_id TEXT NOT NULL,board_id TEXT NOT NULL,record TEXT NOT NULL,UNIQUE(session_id,board_id))')

    def read(db, sid, bid):
        row = db.execute('SELECT record FROM digital_board_assessments WHERE session_id=? AND board_id=?', (sid, bid)).fetchone()
        return json.loads(row['record']) if row else None

    def store(db, sid, bid, record):
        db.execute('INSERT INTO digital_board_assessments VALUES(?,?,?,?) ON CONFLICT(session_id,board_id) '
                   'DO UPDATE SET id=excluded.id,record=excluded.record', (record['id'], sid, bid, json.dumps(record, ensure_ascii=False)))

    def save_state(db, sid, state):
        state['revision'] += 1
        db.execute('UPDATE sessions SET state=? WHERE id=?', (json.dumps(state, ensure_ascii=False), sid))

    def board_ready(board):
        if board['status'] != 'completed' or not (board.get('result') or {}).get('steps'):
            raise HTTPException(409, '板书尚未准备好。')

    @app.on_event('startup')
    def recover():
        with lock, connect() as db:
            for row in db.execute('SELECT * FROM digital_board_assessments').fetchall():
                record = json.loads(row['record'])
                if record['status'] == 'pending':
                    record.update(status='failed', error='测评准备被服务重启打断，请重试。')
                    store(db, row['session_id'], row['board_id'], record)

    @app.get('/api/sessions/{sid}/boards/{board_id}/assessment')
    def get(sid: str, board_id: str, token=Depends(token_value)):
        with lock, connect() as db:
            read_session(db, sid, token); board_for(db, sid, board_id)
            record = read(db, sid, board_id)
            if not record: raise HTTPException(404, '测评 Agent 尚未接到本小节任务。')
            return JSONResponse(public(record), status_code=202 if record['status'] == 'pending' else 200)

    @app.post('/api/sessions/{sid}/boards/{board_id}/assessment')
    def create(sid: str, board_id: str, body: AssessmentRequest, token=Depends(token_value)):
        with lock, connect() as db:
            state = deepcopy(read_session(db, sid, token)); board = board_for(db, sid, board_id)
            board_ready(board); ready(state)
            prior = read(db, sid, board_id)
            if prior and (prior['status'] != 'failed' or not body.retry):
                return JSONResponse(public(prior), status_code=202 if prior['status'] == 'pending' else 200)
            source = source_for(state, board)
            if state.get('pending_question'):
                raise HTTPException(409, '当前已有测评题，请先完成或暂停它。')
            latest_lecture = next((m for m in reversed(state['messages']) if m.get('agent')=='lecturer' and m.get('status')=='ai' and m.get('kind')!='handoff'), None)
            if not latest_lecture or latest_lecture['id'] != source['id']:
                raise HTTPException(409, '这段板书已不是当前讲授，请在当前小节请求测评。')
            request = assessment_agent.lecture_request(state, source)
            request['board_summary'] = [{k: s[k] for k in ('title', 'board', 'narration')} for s in board['result']['steps']]
            record = {'id': str(uuid4()), 'agent': 'assessment', 'status': 'pending',
                      'source_message_id': source['id'], 'step_id': board['result']['steps'][-1]['id'],
                      'request': request, 'created_at': datetime.now(timezone.utc).isoformat()}
            revision = state['revision']; store(db, sid, board_id, record)
        try:
            with usage.scope(session_id=sid, agent='assessment', job_id=record['id']):
                result = assessment_agent.run(chat.checked_call, chat.context(state), request['objective'], request=request)
                chat.check_course_output({**state, 'job': {'text': request['objective']}}, result['message'] + '\n' + result['question'])
            record.update(status='completed', message=result['message'], question=result['question'], objective=result['objective'],
                          private_question={'id': record['id'], 'question': result['question'], 'rubric': result['rubric'],
                                            'objective': result['objective'], 'node_id': request['node_id']})
        except Exception as exc:
            record.update(status='failed', diagnostic=failure(exc, record['id'], 'assessment'), error='测评 Agent 出题未完成，请重试。')
        with lock, connect() as db:
            latest = deepcopy(read_session(db, sid, token))
            if record['status'] == 'completed':
                if latest['revision'] != revision or latest.get('completed'):
                    record = {**record, 'status': 'failed', 'error': '课堂已变化，请重新请求测评。'}
                    record.pop('private_question', None); record.pop('question', None)
                else:
                    task = chat.handoff(latest, 'lecturer', 'assessment', request['objective'], request['reason'])
                    task.update(status='completed', delivery='whiteboard', board_id=board_id, assessment_id=record['id'], request=request)
                    chat.handoff(latest, 'assessment', 'planner', request['objective'], '题目已交给白板展示，等待学生作答。',
                                 {'next_suggestion': '等待本小节作答，不以讲完代替测评。'})
                    save_state(db, sid, latest)
            store(db, sid, board_id, record)
        return public(record)

    @app.post('/api/sessions/{sid}/boards/{board_id}/answers')
    def answer(sid: str, board_id: str, body: AnswerRequest, token=Depends(token_value)):
        with lock, connect() as db:
            state = deepcopy(read_session(db, sid, token)); board = board_for(db, sid, board_id); board_ready(board)
            record = read(db, sid, board_id)
            if not record or record['status'] != 'completed' or record['id'] != body.assessment_id:
                raise HTTPException(409, '请先由测评 Agent 准备本小节题目。')
            if body.step_id != record['step_id']: raise HTTPException(422, '只能回答本小节末尾的测评题。')
            if not body.skip and not body.answer.strip(): raise HTTPException(422, '请作答或明确选择稍后再练。')
            row = db.execute('SELECT record FROM digital_board_answers WHERE session_id=? AND board_id=? AND event_key=?', (sid, board_id, body.idempotency_key)).fetchone()
            if row:
                prior = json.loads(row['record'])
                if any(prior.get(k) != v for k, v in {'assessment_id': body.assessment_id, 'step_id': body.step_id, 'answer': body.answer.strip(), 'skipped': body.skip}.items()):
                    raise HTTPException(409, '提交标识已用于另一份回答。')
                return JSONResponse(prior, status_code=202 if prior['status'] == 'pending' else 200)
            ready(state)
            rows = db.execute('SELECT record FROM digital_board_answers WHERE session_id=? AND board_id=?', (sid, board_id)).fetchall()
            if any(json.loads(r['record']).get('status') == 'pending' for r in rows):
                raise HTTPException(409, '当前回答仍在检查，请稍候。')
            attempt = {'id': str(uuid4()), 'agent': 'assessment', 'assessment_id': record['id'], 'step_id': body.step_id,
                       'answer': body.answer.strip(), 'skipped': body.skip, 'status': 'pending'}
            revision = state['revision']
            db.execute('INSERT INTO digital_board_answers VALUES(?,?,?,?,?,?)',
                       (attempt['id'], sid, board_id, body.step_id, body.idempotency_key, json.dumps(attempt, ensure_ascii=False)))
        try:
            if body.skip:
                result = {'verdict': 'skipped', 'message': '已标记稍后再练，跳过不代表理解。', 'observation': '学生主动跳过，未取得作答证据。', 'next_suggestion': '记录为未测，后续安排补测。'}
            else:
                with usage.scope(session_id=sid, agent='assessment', job_id=attempt['id']):
                    result = assessment_agent.run(chat.checked_call, chat.context(state), record['objective'], body.answer.strip(),
                                                  request=record['request'], question=record['private_question'])
            attempt.update(status='completed', verdict=result['verdict'], feedback=result['message'],
                           observation=result['observation'], next_suggestion=result['next_suggestion'])
        except Exception as exc:
            attempt.update(status='failed', diagnostic=failure(exc, attempt['id'], 'assessment'), error='测评 Agent 判答未完成，请保留答案重试。')
        with lock, connect() as db:
            latest = deepcopy(read_session(db, sid, token))
            if attempt['status'] == 'completed':
                if latest['revision'] != revision or latest.get('completed'):
                    attempt.update(status='failed', error='课堂已变化，本次结果未计入学习证据，请重试。')
                else:
                    if result['verdict'] not in ('not_answer', 'skipped'):
                        latest['evidence'].append({'id': attempt['id'], 'node_id': record['request']['node_id'],
                            'question_id': record['id'], 'question': record['question'], 'answer': body.answer.strip(),
                            'verdict': result['verdict'], 'observation': result['observation'], 'next_suggestion': result['next_suggestion'],
                            'source': 'model_judgment', 'agent': 'assessment', 'delivery': 'whiteboard', 'board_id': board_id})
                    task = chat.handoff(latest, 'assessment', 'planner', record['objective'], '白板测评已反馈，请据此安排补讲、再测或继续。', result)
                    task.update(board_id=board_id, assessment_id=record['id'])
                    if result['verdict'] in ('not_answer', 'skipped'): task['evidence_ids'] = []
                    save_state(db, sid, latest)
            db.execute('UPDATE digital_board_answers SET record=? WHERE id=? AND session_id=?',
                       (json.dumps(attempt, ensure_ascii=False), attempt['id'], sid))
        return attempt
