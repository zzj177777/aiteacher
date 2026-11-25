from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException
import uvicorn
from backend import digital_board as board


def source():
    return {'id': 'lecture', 'agent': 'lecturer', 'status': 'ai', 'text': '一次函数是 $y=2x+3$。系数表示变化量。常数项表示起点。',
            'visuals': [{'id': 'figure-1', 'tool': 'draw_function', 'expression': '2*x+3'}]}


def designed():
    common = {'source_quote': '系数表示变化量。', 'rubric': 'PRIVATE:接受合理等价答案', 'visual_ids': []}
    return {'title': '理解两个数', 'steps': [
        {**common, 'title': '先看系数', 'board': '$y=2x+3$\n系数决定每次变化多少。', 'focus': '$y=2x+3$',
         'narration': '只看系数的作用。', 'question': '系数换成5，每增加1，函数值增加多少？'},
        {**common, 'title': '再看起点', 'board': '常数项决定起点。', 'focus': '起点',
         'narration': '现在看看常数项。', 'question': '常数项换成7，图象与纵轴交在哪里？'},
    ]}


class BoardDesignTests(unittest.TestCase):
    def test_structured_design_checks_grounding_and_preserves_original_diagram(self):
        with patch.object(board, 'call_tool', return_value={'tool': 'design_step_board', 'arguments': designed()}):
            result = board.design(source(), '初二')
        self.assertEqual(len(result['steps']), 2)
        self.assertEqual(result['steps'][-1]['visual_ids'], ['figure-1'])
        self.assertIn('PRIVATE', result['steps'][0]['rubric'])

    def test_invalid_focus_quote_length_and_unknown_visual_fail_explicitly(self):
        for key, value in [('focus', '不存在的重点'), ('source_quote', '不是原文'), ('board', '长' * 221), ('visual_ids', ['unknown'])]:
            raw = designed(); raw['steps'][0][key] = value
            with patch.object(board, 'call_tool', return_value={'tool': 'design_step_board', 'arguments': raw}):
                with self.assertRaises(ValueError): board.design(source(), 'unknown')


class BoardApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'class.sqlite3'
        self.env = patch.dict(os.environ, {'AITEACHER_USAGE_DB': str(Path(self.temp.name) / 'usage.sqlite3')})
        self.env.start(); self.addCleanup(self.env.stop)
        self.state = {'revision': 12, 'plan': {'nodes': [{'status': 'current'}]}, 'messages': [source()],
                      'profile': {'background': '初二'}, 'evidence': [], 'pending_question': None}
        self.original = deepcopy(self.state); self.lock = threading.Lock()

        @contextmanager
        def connect():
            db = sqlite3.connect(self.path, timeout=10); db.row_factory = sqlite3.Row
            try:
                with db: yield db
            finally: db.close()

        def token_value(authorization: str = Header(default='')):
            if not authorization.startswith('Bearer '): raise HTTPException(401, 'missing')
            return authorization[7:]

        def read_session(db, sid, token):
            if sid != 'session' or token != 'secret': raise HTTPException(404, 'not found')
            return self.state

        self.model_calls = []
        def model(system, data, tools, **options):
            self.assertTrue(self.lock.acquire(blocking=False)); self.lock.release()
            name = tools[0]['function']['name']; self.model_calls.append((name, deepcopy(data)))
            args = designed() if name == 'design_step_board' else {'verdict': 'correct' if data['student_answer'] == '5' else 'incorrect', 'feedback': '再对照变化量想一想。'}
            return {'tool': name, 'arguments': args}
        for p in [patch.object(board, 'configured', return_value=True), patch.object(board, 'call_tool', side_effect=model)]:
            p.start(); self.addCleanup(p.stop)
        app = FastAPI(); board.register_routes(app, connect, self.lock, read_session, token_value)
        with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'; self.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
        self.thread = threading.Thread(target=self.server.run, daemon=True); self.thread.start(); self.addCleanup(self.close)
        for _ in range(100):
            if self.server.started: break
            time.sleep(.01)
        self.assertTrue(self.server.started)

    def close(self): self.server.should_exit = True; self.thread.join(5)

    def call(self, path, body=None, token='secret'):
        req = Request(self.url + '/api/sessions/session' + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token is not None else {})})
        try: response = urlopen(req, timeout=6)
        except HTTPError as e: response = e
        with response: return response.status, json.load(response)

    def create(self):
        code, result = self.call('/boards', {'message_id': 'lecture'})
        self.assertEqual(code, 200); self.assertEqual(result['status'], 'completed')
        return result

    def test_retries_an_invalid_source_quote_with_specific_feedback(self):
        invalid = designed()
        invalid['steps'][0]['source_quote'] = '这句话没有出现在原文中。'
        responses = [{'tool': 'design_step_board', 'arguments': args} for args in (invalid, designed())]
        with patch.object(board, 'call_tool', side_effect=responses) as model:
            result = self.create()
        self.assertEqual(model.call_count, 2)
        self.assertEqual(model.call_args.args[1]['previous_validation_error'], 'source_quote_not_in_lecture')
        self.assertEqual(result['result']['steps'][0]['source_quote'], designed()['steps'][0]['source_quote'])
        self.assertEqual(self.state, self.original)

    def test_auth_private_rubric_and_cache_without_teaching_changes(self):
        self.assertEqual(self.call('/boards', {'message_id': 'lecture'}, None)[0], 401)
        self.assertEqual(self.call('/boards', {'message_id': 'lecture'}, 'wrong')[0], 404)
        self.assertEqual(self.call('/boards', {'message_id': 'student'})[0], 404)
        first = self.create(); second = self.create()
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.model_calls), 1)
        self.assertNotIn('PRIVATE', json.dumps(first))
        self.assertNotIn('rubric', first['result']['steps'][0])
        self.assertEqual(self.state, self.original)

    def test_check_is_idempotent_and_only_gets_current_question(self):
        value = self.create(); step = value['result']['steps'][0]
        path = f"/boards/{value['id']}/answers"
        payload = {'step_id': step['id'], 'answer': '5', 'idempotency_key': 'same-answer-1'}
        code, attempt = self.call(path, payload); self.assertEqual(code, 200)
        self.assertEqual(attempt['verdict'], 'correct')
        self.assertEqual(self.call(path, payload)[1]['id'], attempt['id'])
        self.assertEqual(len(self.model_calls), 2)
        self.assertEqual(self.call(path, {**payload, 'answer': 'other'})[0], 409)
        grade_data = self.model_calls[-1][1]
        self.assertEqual(grade_data['question'], step['question'])
        self.assertNotIn(value['result']['steps'][1]['question'], json.dumps(grade_data, ensure_ascii=False))
        restored = self.call('/boards/source/lecture')[1]
        self.assertEqual(restored['checks'][step['id']]['verdict'], 'correct')
        self.assertNotIn('PRIVATE', json.dumps(restored))
        self.assertEqual(self.state, self.original)

    def test_skip_is_explicit_not_a_correct_answer_and_does_not_call_model(self):
        value = self.create(); step = value['result']['steps'][0]
        path = f"/boards/{value['id']}/answers"
        self.assertEqual(self.call(path, {'step_id': step['id'], 'answer': ' ', 'idempotency_key': 'empty-answer'})[0], 422)
        code, attempt = self.call(path, {'step_id': step['id'], 'skip': True, 'idempotency_key': 'explicit-skip'})
        self.assertEqual(code, 200); self.assertEqual(attempt['verdict'], 'skipped')
        self.assertEqual(len(self.model_calls), 1)
        self.assertEqual(self.state, self.original)

    def test_generation_and_check_failures_leave_original_readable_and_retryable(self):
        with patch.object(board, 'design', side_effect=ValueError('PRIVATE FAILURE')):
            code, failed = self.call('/boards', {'message_id': 'lecture'})
        self.assertEqual(code, 200); self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('PRIVATE', json.dumps(failed))
        code, ready = self.call('/boards', {'message_id': 'lecture', 'retry': True})
        self.assertEqual(ready['status'], 'completed'); self.assertNotEqual(ready['id'], failed['id'])
        with patch.object(board, 'grade', side_effect=ValueError('private rubric')):
            code, result = self.call(f"/boards/{ready['id']}/answers", {'step_id': ready['result']['steps'][0]['id'], 'answer': '5', 'idempotency_key': 'failed-grade'})
        self.assertEqual(result['status'], 'failed'); self.assertNotIn('rubric', json.dumps(result))
        self.assertEqual(self.state, self.original)

    def test_step_speech_never_reads_rubric_or_next_step(self):
        value = self.create(); step = value['result']['steps'][0]
        from backend import digital_human as dh
        spoken = []
        with patch.object(dh, 'speech_chunks', side_effect=lambda text: spoken.append(text) or [text]), patch.object(dh, 'synthesize', return_value=b'fake mp3'):
            url = self.url + f"/api/sessions/session/boards/{value['id']}/speech"
            req = Request(url, data=json.dumps({'step_id': step['id'], 'chunk': 0}).encode(), headers={'Authorization': 'Bearer secret', 'Content-Type': 'application/json'})
            with urlopen(req) as response: self.assertEqual(response.read(), b'fake mp3')
        self.assertIn(step['question'], spoken[0]); self.assertNotIn('PRIVATE', spoken[0])
        self.assertNotIn(value['result']['steps'][1]['question'], spoken[0])
        self.assertEqual(self.state, self.original)


if __name__ == '__main__': unittest.main()
