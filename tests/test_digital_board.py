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
from backend import board_detours as detours
from backend.board_diagnostics import validate_board, reference_span
from backend.errors import TeachingError


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


def presentation():
    raw = designed()
    for step in raw['steps']:
        step.pop('question'); step.pop('rubric')
    return raw


class BoardDesignTests(unittest.TestCase):
    def test_247_character_board_and_other_generated_text_are_preserved_without_caps(self):
        raw = presentation(); formula = r'$\begin{pmatrix}1&2\\0&1\end{pmatrix}$'
        content = '起点：' + '字' * (247 - 3 - len(formula)) + formula
        self.assertEqual(len(content), 247)
        raw['title'] = '课程标题' * 30
        raw['steps'][1].update(board=content, focus=content, title='白板标题' * 30,
                               narration='口语讲解。' * 100)
        with patch.object(board, 'call_tool', return_value={'tool':'design_step_board','arguments':raw}) as call:
            result = board.design(source(), '初学者')
        for key in ('board','focus','title','narration'):
            self.assertEqual(result['steps'][1][key], raw['steps'][1][key])
        self.assertTrue(result['steps'][1]['board'].endswith(formula))
        schema = call.call_args.args[2][0]['function']['parameters']['properties']
        self.assertNotIn('maxLength', schema['title'])
        for key in ('board','title','narration','source_quote'):
            self.assertNotIn('maxLength', schema['steps']['items']['properties'][key])

    def test_detour_text_has_no_character_caps_in_schema_or_validation(self):
        raw = {'title':'标题'*50, 'intro':'衔接说明。'*100, 'return_transition':'回到主线。'*100,
               'steps':[{'title':'小步标题'*30, 'board':'完整的板书内容。'*100, 'narration':'完整讲解。'*200}]}
        with patch.object(detours, 'call_tool', return_value={'tool':'teach_board_detour','arguments':raw}) as call:
            result = detours.teach({})
        self.assertEqual(result['steps'][0]['board'], raw['steps'][0]['board'])
        self.assertEqual(result['steps'][0]['narration'], raw['steps'][0]['narration'])
        self.assertEqual(result['return_transition'], raw['return_transition'])
        self.assertNotIn('maxLength', json.dumps(call.call_args.args[2]))

    def test_new_board_designer_delegates_marking_and_no_longer_requires_focus(self):
        raw = presentation()
        for step in raw['steps']: step.pop('focus')
        with patch.object(board, 'call_tool', return_value={'tool': 'design_step_board', 'arguments': raw}) as call:
            result = board.design(source(), '初学者')
        self.assertEqual(result['steps'][0]['focus'], '')
        fields = call.call_args.args[2][0]['function']['parameters']['properties']['steps']['items']['properties']
        self.assertNotIn('focus', fields)

    def test_detour_tool_validates_structure_and_keeps_readable_explanation_if_focus_misses(self):
        raw = {'title': '补基础', 'intro': '先补一个概念。', 'return_transition': '回到主线继续。',
               'steps': [{'title': '先看例子', 'board': '多一个输入，输出多2。', 'focus': '不在原文', 'narration': '看看两次的差。'}]}
        with patch.object(detours, 'call_tool', return_value={'tool': 'teach_board_detour', 'arguments': raw}):
            result = detours.teach({'student_confusion': '系数是什么意思'})
        self.assertEqual(result['steps'][0]['focus'], ''); self.assertEqual(result['steps'][0]['board'], raw['steps'][0]['board'])
        raw['steps'] = []
        with patch.object(detours, 'call_tool', return_value={'tool': 'teach_board_detour', 'arguments': raw}):
            with self.assertRaises(TeachingError): detours.teach({})

    def test_long_source_quote_remains_complete_and_no_longer_blocks_board(self):
        quote = '保留完整的原文证据与条件。' * 30 + r'$\lambda=2$，不能丢失公式。'
        self.assertGreater(len(quote), 260)
        lecture = source(); lecture['text'] += quote
        raw = presentation(); raw['steps'][1]['source_quote'] = quote
        with patch.object(board, 'call_tool', return_value={'tool': 'design_step_board', 'arguments': raw}) as call:
            value = board.design(lecture, '初学者')
        self.assertEqual(value['steps'][1]['source_quote'], quote)
        schema = call.call_args.args[2][0]['function']['parameters']['properties']['steps']['items']['properties']['source_quote']
        self.assertNotIn('maxLength', schema)
        raw['steps'][1]['source_quote'] = quote.replace(r'\lambda=2', r'\lambda=3')
        with self.assertRaises(TeachingError) as caught:
            validate_board({'tool': 'design_step_board', 'arguments': raw}, lecture)
        self.assertEqual(caught.exception.code, 'board_source_quote_mismatch')

    def test_field_failures_identify_step_and_field_without_field_contents(self):
        cases = [('focus', '找不到的重点', 'board_focus_mismatch'),
                 ('source_quote', '改写的依据', 'board_source_quote_mismatch'),
                 ('board', None, 'board_field_type'),
                 ('visual_ids', ['PRIVATE'], 'board_visual_unknown'),
                 ('question', '', 'board_field_empty'),
                 ('narration', 123, 'board_field_type')]
        for field, value, code in cases:
            raw = designed(); raw['steps'][1][field] = value
            with self.assertRaises(TeachingError) as caught:
                validate_board({'tool': 'design_step_board', 'arguments': raw}, source())
            error = caught.exception
            self.assertEqual(error.code, code); self.assertEqual(error.details['step'], 2)
            self.assertEqual(error.details['field'], field)
            self.assertNotIn('PRIVATE', json.dumps(error.details))

    def test_whitespace_only_matches_restore_actual_source_and_preserve_math(self):
        lecture = source(); lecture['text'] = '系数\n  表示变化量。'
        raw = designed(); raw['steps'][0].update(board='每次\n  变化多少。', focus='每次 变化多少。')
        for step in raw['steps']: step['source_quote'] = '系数 表示变化量。'
        value = validate_board({'tool': 'design_step_board', 'arguments': raw}, lecture)
        self.assertEqual(value['steps'][0]['focus'], '每次\n  变化多少。')
        self.assertEqual(value['steps'][0]['source_quote'], lecture['text'])
        self.assertIsNone(reference_span('$x+1$', '$x-1$'))
        self.assertIsNone(reference_span(r'$\sin x$', r'$\sinx$'))
        self.assertEqual(reference_span('$x + 1$', '$x  +  1$'), '$x + 1$')

    def test_missing_extra_fields_and_step_count_have_specific_codes(self):
        cases = []
        raw = designed(); del raw['steps'][0]['narration']; cases.append((raw, 'board_missing_fields'))
        raw = designed(); raw['steps'][0]['PRIVATE_UNEXPECTED'] = 'PRIVATE'; cases.append((raw, 'board_extra_fields'))
        raw = designed(); raw['steps'] = []; cases.append((raw, 'board_step_count'))
        raw = designed(); raw['steps'] = 'PRIVATE'; cases.append((raw, 'board_steps_type'))
        for raw, code in cases:
            with self.assertRaises(TeachingError) as caught:
                validate_board({'tool': 'design_step_board', 'arguments': raw}, source())
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn('PRIVATE', json.dumps(caught.exception.details))

    def test_structured_design_checks_grounding_and_preserves_original_diagram(self):
        with patch.object(board, 'call_tool', return_value={'tool': 'design_step_board', 'arguments': presentation()}):
            result = board.design(source(), '初二')
        self.assertEqual(len(result['steps']), 2)
        self.assertEqual(result['steps'][-1]['visual_ids'], ['figure-1'])
        self.assertNotIn('rubric', result['steps'][0]); self.assertNotIn('question', result['steps'][0])

    def test_invalid_focus_quote_and_unknown_visual_fail_explicitly(self):
        for key, value in [('focus', '不存在的重点'), ('source_quote', '不是原文'), ('visual_ids', ['unknown'])]:
            raw = presentation(); raw['steps'][0][key] = value
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
            args = presentation() if name == 'design_step_board' else {'verdict': 'correct' if data['student_answer'] == '5' else 'incorrect', 'feedback': '再对照变化量想一想。'}
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

    def test_diagnostic_survives_retry_and_history_is_authorized_and_content_free(self):
        legacy = TeachingError('schema_validation','board_text_too_long','第 2 步的短板书有 280 个字符，超过旧上限。',field='board',step=2,actual_length=280,limit=220)
        with patch.object(board, 'design', side_effect=legacy):
            _, failed = self.call('/boards', {'message_id': 'lecture'})
        self.assertEqual(failed['diagnostic']['code'], 'board_text_too_long')
        self.assertEqual(failed['diagnostic']['details'], {'field': 'board', 'step': 2, 'actual_length': 280, 'limit': 220})
        self.assertIn('280', failed['error']); self.assertNotIn('PRIVATE', json.dumps(failed))
        _, ready = self.call('/boards', {'message_id': 'lecture', 'retry': True})
        self.assertEqual(ready['status'], 'completed')
        path = '/boards/source/lecture/diagnostics'
        self.assertEqual(self.call(path, token='wrong')[0], 404)
        self.assertEqual(self.call(path, token=None)[0], 401)
        _, history = self.call(path)
        self.assertEqual(len(history['attempts']), 2)
        prior = next(item for item in history['attempts'] if item['id'] == failed['id'])
        self.assertEqual(prior['diagnostic']['details']['actual_length'], 280)
        self.assertNotIn('PRIVATE', json.dumps(history))
        self.assertNotIn('student_answer', json.dumps(history)); self.assertNotIn('result', json.dumps(history))
        self.assertEqual(self.state, self.original)

    def test_provider_parse_and_unknown_failures_are_distinct_without_raw_exception(self):
        cases = [(TeachingError('provider_request', 'timeout', '模型请求超时。'), 'provider_request', 'timeout'),
                 (TeachingError('tool_parse', 'arguments_json', '工具参数不是有效 JSON。'), 'tool_parse', 'arguments_json'),
                 (RuntimeError('PRIVATE token should not escape'), 'board_processing', 'internal_error')]
        for error, stage, code in cases:
            with patch.object(board, 'design', side_effect=error):
                _, failed = self.call('/boards', {'message_id': 'lecture', 'retry': True})
            self.assertEqual(failed['diagnostic']['stage'], stage)
            self.assertEqual(failed['diagnostic']['code'], code)
            self.assertNotIn('PRIVATE', json.dumps(failed))

    def test_old_failed_records_explicitly_report_unknown_cause_and_are_kept_on_retry(self):
        with patch.object(board, 'design', side_effect=ValueError('old failure')):
            _, failed = self.call('/boards', {'message_id': 'lecture'})
        with sqlite3.connect(self.path) as db:
            value = json.loads(db.execute('select record from digital_boards').fetchone()[0]); value.pop('diagnostic')
            db.execute('update digital_boards set record=?', (json.dumps(value),)); db.execute('delete from digital_board_runs')
        db.close()
        _, old = self.call('/boards/source/lecture')
        self.assertEqual(old['diagnostic']['code'], 'board_legacy_failure')
        self.assertEqual(self.call('/boards/source/lecture/diagnostics')[1]['attempts'][0]['diagnostic']['code'], 'board_legacy_failure')
        self.call('/boards', {'message_id': 'lecture', 'retry': True})
        history = self.call('/boards/source/lecture/diagnostics')[1]['attempts']
        self.assertTrue(any(item.get('diagnostic', {}).get('code') == 'board_legacy_failure' for item in history))

    def test_legacy_board_answer_cannot_bypass_independent_agent(self):
        value = self.create(); step = value['result']['steps'][-1]
        path = f"/boards/{value['id']}/answers"
        body = {'step_id':step['id'], 'answer':'5', 'idempotency_key':'legacy-answer'}
        self.assertEqual(self.call(path, body)[0], 422)
        self.assertEqual(self.call(path, {**body, 'assessment_id':'fabricated'})[0], 409)
        self.assertEqual(self.state, self.original)
        self.assertNotIn('question', step)

    def test_generation_and_check_failures_leave_original_readable_and_retryable(self):
        with patch.object(board, 'design', side_effect=ValueError('PRIVATE FAILURE')):
            code, failed = self.call('/boards', {'message_id': 'lecture'})
        self.assertEqual(code, 200); self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('PRIVATE', json.dumps(failed))
        code, ready = self.call('/boards', {'message_id': 'lecture', 'retry': True})
        self.assertEqual(ready['status'], 'completed'); self.assertNotEqual(ready['id'], failed['id'])
        self.assertEqual(self.state, self.original)

    def test_step_speech_never_reads_rubric_or_next_step(self):
        value = self.create(); step = value['result']['steps'][0]
        from backend import digital_human as dh
        spoken = []
        with patch.object(dh, 'speech_chunks', side_effect=lambda text: spoken.append(text) or [text]), patch.object(dh, 'synthesize', return_value=b'fake mp3'):
            url = self.url + f"/api/sessions/session/boards/{value['id']}/speech"
            req = Request(url, data=json.dumps({'step_id': step['id'], 'chunk': 0}).encode(), headers={'Authorization': 'Bearer secret', 'Content-Type': 'application/json'})
            with urlopen(req) as response: self.assertEqual(response.read(), b'fake mp3')
        self.assertEqual(step['narration'], spoken[0]); self.assertNotIn('PRIVATE', spoken[0])
        self.assertNotIn('rubric', step); self.assertNotIn('question', step)
        self.assertEqual(self.state, self.original)

    def test_sync_routes_use_saved_content_outside_lock_and_keep_progress(self):
        value=self.create();step=value['result']['steps'][0]
        payload={'step_id':step['id'],'chunk':0,'voice_id':'doubao-silang','synchronized':True,
                 'units':[{'start':0,'end':len(step['board'])}], 'narration':'CLIENT INJECTION'}
        calls=[]
        def synced(board_text,narration,ranges,chunk,voice,sid):
            self.assertTrue(self.lock.acquire(blocking=False));self.lock.release()
            calls.append((board_text,narration,voice,sid))
            self.assertNotIn('PRIVATE',narration);self.assertNotIn('CLIENT INJECTION',narration)
            return {'audio':'YXVkaW8=','chunks':1,'aligned':True,'cue':None}
        with patch.object(board,'sync_response',side_effect=synced):
            path=f"/boards/{value['id']}/speech"
            self.assertEqual(self.call(path,payload,token=None)[0],401)
            self.assertEqual(self.call(path,payload,token='wrong')[0],404)
            self.assertEqual(self.call(path,payload)[0],200)
        self.assertEqual(calls,[(step['board'],step['narration'],'doubao-silang','session')])
        with patch.object(detours,'teach',return_value=self.lesson()):
            record=self.call(f"/boards/{value['id']}/detours",self.detour(value))[1]
        branch_step=record['result']['steps'][0]
        with patch.object(detours,'sync_response',side_effect=synced):
            path=f"/boards/{value['id']}/detours/{record['id']}/speech"
            self.assertEqual(self.call(path,{**payload,'step_id':branch_step['id']})[0],200)
        self.assertEqual(calls[-1][0],branch_step['board'])
        self.assertIn(branch_step['narration'],calls[-1][1])
        self.assertEqual(self.state,self.original)

    def detour(self, value, **changes):
        return {'step_id': value['result']['steps'][0]['id'], 'anchor': {'page': 0, 'revealed': 2, 'text_mode': 'sentence'},
                'question': '为什么系数表示变化量？', 'quote': '', 'idempotency_key': 'detour-request-1', **changes}

    def lesson(self):
        return {'title': '用加法看变化', 'intro': '先停在系数这里，补一个具体例子。', 'return_transition': '每多一个2就多加一次；回到先看系数，从原处继续。',
                'steps': [{'id': 'branch-step', 'title': '看一组数字', 'board': '当输入多1，输出多2。', 'focus': '多2', 'narration': '先看相邻两次的差。'}]}

    def test_reading_is_self_report_not_mastery_and_has_no_model_call(self):
        value = self.create(); path = f"/boards/{value['id']}/understood"; step = value['result']['steps'][0]['id']
        self.assertEqual(self.call(path, {'step_id': 'missing'})[0], 404)
        self.assertEqual(self.call(path, {'step_id': step}, token=None)[0], 401)
        for _ in range(2): self.assertEqual(self.call(path, {'step_id': step})[1]['understood_step_ids'], [step])
        restored = self.call('/boards/source/lecture')[1]
        self.assertEqual(restored['understood_step_ids'], [step]); self.assertEqual(restored['checks'], {})
        self.assertEqual(len(self.model_calls), 1); self.assertEqual(self.state, self.original)

    def test_detour_anchor_idempotence_authorization_and_return_leave_main_unchanged(self):
        value = self.create(); path = f"/boards/{value['id']}/detours"; payload = self.detour(value)
        with patch.object(detours, 'teach', return_value=self.lesson()) as teach:
            self.assertEqual(self.call(path, payload, token='wrong')[0], 404)
            self.assertEqual(self.call(path, {**payload, 'question': ''})[0], 422)
            self.assertEqual(self.call(path, {**payload, 'anchor': {'page': 90}})[0], 422)
            code, created = self.call(path, payload); self.assertEqual(code, 200)
            self.assertEqual(self.call(path, payload)[1]['id'], created['id']); self.assertEqual(teach.call_count, 1)
            self.assertEqual(self.call(path, {**payload, 'question': '别的问题'})[0], 409)
            self.assertEqual(self.call(path, {**payload, 'idempotency_key': 'other-request'})[0], 409)
            context = teach.call_args.args[0]
            self.assertNotIn('PRIVATE', json.dumps(context)); self.assertNotIn('rubric', json.dumps(context))
            self.assertEqual(context['return_anchor']['revealed'], 2)
        self.assertEqual(self.call(path+'/active')[1]['detour']['id'], created['id'])
        returned = self.call(path+f"/{created['id']}/return", {'understood': True})[1]
        self.assertEqual(returned['anchor'], created['anchor']); self.assertEqual(returned['resolution'], 'understood')
        self.assertIsNone(self.call(path+'/active')[1]['detour'])
        self.assertEqual(self.state, self.original)
        self.assertEqual(self.call('/boards/source/lecture')[1]['checks'], {})

    def test_followup_reuses_original_anchor_and_retains_confusion(self):
        value = self.create(); path = f"/boards/{value['id']}/detours"
        payload = self.detour(value, question='', quote='系数')
        with patch.object(detours, 'teach', return_value=self.lesson()) as teach:
            first = self.call(path, payload)[1]
            second = self.call(path, {**payload, 'question': '还是不理解，换个例子', 'idempotency_key': 'followup-request', 'previous_detour_id': first['id'], 'anchor': {'page': 1, 'revealed': 1}})[1]
            self.assertEqual(first['anchor'], second['anchor'])
            self.assertEqual(teach.call_args.args[0]['previous_detour'], self.lesson())
        self.assertEqual(self.call(path+f"/{first['id']}")[1]['resolution'], 'replaced')
        self.assertEqual(self.call(path+'/active')[1]['detour']['id'], second['id'])
        self.call(path+f"/{second['id']}/return", {'understood': False})
        self.assertIsNone(self.call(path+'/active')[1]['detour'])
        self.assertEqual(self.call('/boards/source/lecture')[1]['understood_step_ids'], [])
        self.assertEqual(self.state, self.original)

    def test_detour_speech_has_intro_and_return_transition_without_private_main_content(self):
        value = self.create(); path = f"/boards/{value['id']}/detours"
        with patch.object(detours, 'teach', return_value=self.lesson()): created = self.call(path, self.detour(value))[1]
        from backend import digital_human as dh
        texts = []
        with patch.object(dh, 'speech_chunks', side_effect=lambda text: texts.append(text) or [text]), patch.object(dh, 'synthesize', return_value=b'mp3'):
            for part in ('step', 'return'):
                req = Request(self.url+'/api/sessions/session'+path+f"/{created['id']}/speech", data=json.dumps({'step_id': 'branch-step', 'part': part}).encode(), headers={'Authorization': 'Bearer secret', 'Content-Type': 'application/json'})
                with urlopen(req) as response: self.assertEqual(response.read(), b'mp3')
        self.assertEqual(texts[0], self.lesson()['intro']+'\n'+self.lesson()['steps'][0]['narration'])
        self.assertEqual(texts[1], self.lesson()['return_transition']); self.assertNotIn('PRIVATE', str(texts))
        self.assertEqual(self.state, self.original)

    def test_detour_failure_and_late_completion_preserve_return_resolution(self):
        value = self.create(); path = f"/boards/{value['id']}/detours"; payload = self.detour(value)
        with patch.object(detours, 'teach', side_effect=RuntimeError('PRIVATE secret')):
            failed = self.call(path, payload)[1]
        self.assertEqual(failed['status'], 'failed'); self.assertNotIn('PRIVATE', json.dumps(failed))
        self.call(path+f"/{failed['id']}/return", {'understood': False})
        started, release = threading.Event(), threading.Event(); results = []
        def slow(context): started.set(); release.wait(4); return self.lesson()
        with patch.object(detours, 'teach', side_effect=slow):
            thread = threading.Thread(target=lambda: results.append(self.call(path, {**payload, 'idempotency_key': 'slow-request'})))
            thread.start(); self.assertTrue(started.wait(2))
            pending = self.call(path+'/active')[1]['detour']; self.assertEqual(pending['status'], 'pending')
            self.assertEqual(self.call(path+f"/{pending['id']}/return", {'understood': True})[0], 409)
            self.call(path+f"/{pending['id']}/return", {'understood': False})
            release.set(); thread.join(5)
        self.assertEqual(results[0][1]['status'], 'completed'); self.assertEqual(results[0][1]['resolution'], 'unresolved')
        self.assertIsNone(self.call(path+'/active')[1]['detour']); self.assertEqual(self.state, self.original)


if __name__ == '__main__': unittest.main()
