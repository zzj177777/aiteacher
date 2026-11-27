"""Assessment ownership and real HTTP/SQLite handoff regression tests."""
from contextlib import contextmanager
from copy import deepcopy
import json
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

from backend import assessment_agent, chat_classroom as chat, digital_board as board
from backend.errors import TeachingError
from tests.test_digital_board import presentation, source


class AssessmentOwnershipTests(unittest.TestCase):
    def test_lecturer_only_requests_assessment_and_style_cannot_override_boundary(self):
        state = chat.new_state()
        lecture = {'message':'系数表示变化量。', 'covered':'系数', 'next_suggestion':'请求测评', 'visuals':[],
                   'assessment_request':{'objective':'检查系数','covered':'系数表示变化量','prerequisites':'加法','reason':'讲解完成'}}
        with patch.object(chat, 'call_tool', return_value={'tool':'submit_lecturer_result','arguments':lecture}) as model:
            self.assertEqual(chat.specialist(state, 'lecturer', '讲系数'), lecture)
        instruction, data, tools = model.call_args.args
        self.assertIn('不得自行出练习题', instruction)
        self.assertIn('assessment_request', tools[0]['function']['parameters']['required'])
        bad = deepcopy(lecture); bad['assessment_request'] = {'question':'偷偷出题'}
        with patch.object(chat, 'call_tool', return_value={'tool':'submit_lecturer_result','arguments':bad}):
            with self.assertRaises(TeachingError): chat.specialist(state, 'lecturer', '讲系数')

    def test_chat_and_whiteboard_share_one_assessment_prompt(self):
        state = chat.new_state(); result = {'message':'请作答','question':'题目','rubric':'PRIVATE','objective':'检查理解'}
        with patch.object(chat, 'call_tool', return_value={'tool':'submit_assessment_result','arguments':result}) as model:
            chat.specialist(state, 'assessment', '检查理解')
            chat_prompt = model.call_args.args[0]
            assessment_agent.run(chat.checked_call, chat.context(state), '检查理解', request={'requested_by':'lecturer'})
            self.assertEqual(chat_prompt, model.call_args.args[0])

    def test_board_designer_schema_has_no_question_or_rubric_and_rejects_them(self):
        raw = presentation()
        with patch.object(board, 'call_tool', return_value={'tool':'design_step_board','arguments':raw}) as model:
            board.design(source(), '初二')
        properties = model.call_args.args[2][0]['function']['parameters']['properties']['steps']['items']['properties']
        self.assertNotIn('question', properties); self.assertNotIn('rubric', properties)
        raw['steps'][0]['question'] = '不允许板书模型出题'
        with patch.object(board, 'call_tool', return_value={'tool':'design_step_board','arguments':raw}):
            with self.assertRaises(TeachingError) as caught: board.design(source(), '初二')
        self.assertEqual(caught.exception.code, 'board_assessment_boundary')


class WhiteboardAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'class.sqlite3'; self.lock = threading.Lock(); self.calls = []

        @contextmanager
        def connect():
            db = sqlite3.connect(self.path, timeout=10); db.row_factory = sqlite3.Row
            try:
                with db: yield db
            finally: db.close()
        self.connect = connect
        state = chat.new_state(); state['profile'] = {'goal':'一次函数','background':'初二'}
        state['plan'] = {'id':'plan','steps':['系数和起点']}; chat.ensure_outline(state)
        lecture = source(); lecture.update(plan_id='plan',node_id=chat.current_node(state)['id'],
            assessment_request={'objective':'理解系数和起点','covered':'系数表示变化量，常数表示起点','prerequisites':'加法','reason':'本小节讲完'})
        state['messages'].append(lecture)
        with connect() as db:
            db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,state TEXT)')
            db.execute('INSERT INTO sessions VALUES(?,?)', ('s', json.dumps(state)))

        def token_value(authorization: str = Header(default='')):
            if not authorization.startswith('Bearer '): raise HTTPException(401, 'missing')
            return authorization[7:]

        def read_session(db, sid, token):
            if sid != 's' or token != 'secret': raise HTTPException(404, 'not found')
            return json.loads(db.execute('SELECT state FROM sessions WHERE id=?', (sid,)).fetchone()[0])

        def model(system, data, tools, **options):
            self.assertTrue(self.lock.acquire(blocking=False)); self.lock.release()
            name = tools[0]['function']['name']; self.calls.append((name, deepcopy(data)))
            if name == 'design_step_board': args = presentation()
            elif data['student_answer'] is None:
                args = {'message':'试一道迁移题。','question':'$y=5x+7$，当x增加1时y增加多少？',
                        'rubric':'PRIVATE:5，接受等价答案','objective':'检查变化量理解'}
            else:
                answer = data['student_answer']
                verdict = {'5':'correct','求提示':'not_answer'}.get(answer, 'incorrect')
                args = {'message':'本题答对了。' if verdict=='correct' else '再关注每次变化多少。',
                        'verdict':verdict,'observation':'对变化量的本次回答证据','next_suggestion':'继续' if verdict=='correct' else '补讲系数'}
            return {'tool':name,'arguments':args}
        for mock in (patch.object(board,'configured',return_value=True), patch.object(board,'call_tool',side_effect=model), patch.object(chat,'call_tool',side_effect=model)):
            mock.start(); self.addCleanup(mock.stop)
        self.model = model
        app = FastAPI(); board.register_routes(app, connect, self.lock, read_session, token_value)
        with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}/api/sessions/s'
        self.server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=self.server.run,daemon=True); thread.start()
        self.addCleanup(lambda: (setattr(self.server,'should_exit',True),thread.join(5)))
        for _ in range(100):
            if self.server.started: break
            time.sleep(.01)
        self.assertTrue(self.server.started)
        self.board = self.call('/boards', {'message_id':'lecture'})[1]
        self.assertEqual(self.board['status'],'completed')
        self.base=f"/boards/{self.board['id']}"

    def call(self, path, body=None, token='secret'):
        req=Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try: response=urlopen(req,timeout=8)
        except HTTPError as exc: response=exc
        with response: return response.status,json.load(response)

    def state(self):
        with self.connect() as db: return json.loads(db.execute('SELECT state FROM sessions').fetchone()[0])

    def change(self, mutate):
        with self.connect() as db:
            state=json.loads(db.execute('SELECT state FROM sessions').fetchone()[0]); mutate(state)
            db.execute('UPDATE sessions SET state=?',(json.dumps(state),))

    def create(self):
        code,value=self.call(self.base+'/assessment',{}); self.assertEqual(code,200)
        self.assertEqual(value['status'],'completed'); self.assertNotIn('PRIVATE',json.dumps(value))
        return value

    def answer(self, q, text='5', key='answer-key-1', **extra):
        return self.call(self.base+'/answers',{'assessment_id':q['id'],'step_id':q['step_id'],
                                             'answer':text,'idempotency_key':key,**extra})

    def test_handoff_has_context_private_answer_stays_backend_and_generation_is_cached(self):
        q=self.create(); self.assertEqual(self.create()['id'],q['id']); self.assertEqual(len(self.calls),2)
        request=self.calls[-1][1]['assessment_request']
        self.assertEqual(request['requested_by'],'lecturer'); self.assertEqual(request['covered'],'系数表示变化量，常数表示起点')
        self.assertEqual(len(request['board_summary']),2)
        state=self.state(); self.assertEqual(state['revision'],1)
        self.assertEqual(state['tasks'][0]['sender'],'lecturer'); self.assertEqual(state['tasks'][0]['recipient'],'assessment')
        self.assertEqual(state['tasks'][0]['delivery'],'whiteboard')
        self.assertNotIn('PRIVATE',json.dumps(chat.public(state)))
        self.assertNotIn('question', self.board['result']['steps'][-1])

    def test_answer_enters_shared_evidence_and_planner_context_once(self):
        q=self.create(); code,attempt=self.answer(q)
        self.assertEqual(code,200); self.assertEqual(attempt['verdict'],'correct')
        self.assertEqual(self.answer(q)[1]['id'],attempt['id']); self.assertEqual(len(self.calls),3)
        state=self.state(); self.assertEqual(len(state['evidence']),1); self.assertEqual(state['revision'],2)
        self.assertEqual(state['evidence'][0]['question_id'],q['id']); self.assertEqual(state['evidence'][0]['agent'],'assessment')
        self.assertEqual(chat.context(state)['evidence'][0]['verdict'],'correct')
        self.assertEqual(state['tasks'][-1]['feedback']['next_suggestion'],'继续')
        self.assertEqual(state['tasks'][-1]['evidence_ids'],[attempt['id']])
        self.assertNotIn('PRIVATE',json.dumps(chat.public(state)))
        restored=self.call('/boards/source/lecture')[1]
        self.assertEqual(restored['checks'][q['step_id']]['assessment_id'],q['id'])
        self.assertEqual(self.answer(q,'different')[0],409)

    def test_wrong_answer_retains_question_and_retry_records_real_evidence(self):
        q=self.create(); self.assertEqual(self.answer(q,'7')[1]['verdict'],'incorrect')
        self.assertEqual(self.call(self.base+'/assessment')[1]['id'],q['id'])
        self.assertEqual(self.answer(q,'5','answer-retry')[1]['verdict'],'correct')
        self.assertEqual([e['verdict'] for e in self.state()['evidence']],['incorrect','correct'])
        self.assertEqual(chat.current_node(self.state())['status'],'current')

    def test_skip_and_requests_for_help_are_not_mastery_or_wrong_answer(self):
        q=self.create(); self.assertEqual(self.answer(q,'求提示')[1]['verdict'],'not_answer')
        _,attempt=self.answer(q,'','explicit-skip',skip=True)
        self.assertEqual(attempt['verdict'],'skipped'); self.assertEqual(self.state()['evidence'],[])
        self.assertEqual(self.state()['tasks'][-1]['evidence_ids'],[])
        self.assertEqual(len(self.calls),3)  # No model call for explicit skip.

    def test_auth_payload_injection_and_wrong_question_are_rejected(self):
        self.assertEqual(self.call(self.base+'/assessment',{},None)[0],401)
        self.assertEqual(self.call(self.base+'/assessment',{},'wrong')[0],404)
        self.assertEqual(self.call(self.base+'/assessment',{'question':'CLIENT OVERRIDE'})[0],422)
        q=self.create()
        self.assertEqual(self.answer({**q,'id':'other'})[0],409)
        self.assertEqual(self.answer({**q,'step_id':self.board['result']['steps'][0]['id']})[0],422)
        self.assertEqual(self.answer(q,' ')[0],422)

    def test_failed_generation_is_visible_retryable_and_does_not_fallback_to_lecturer(self):
        with patch.object(chat,'call_tool',side_effect=RuntimeError('PRIVATE provider body')):
            _,failed=self.call(self.base+'/assessment',{})
        self.assertEqual(failed['status'],'failed'); self.assertNotIn('PRIVATE',json.dumps(failed))
        self.assertEqual(self.state()['tasks'],[])
        _,q=self.call(self.base+'/assessment',{'retry':True})
        self.assertEqual(q['status'],'completed'); self.assertNotEqual(q['id'],failed['id'])

    def test_failed_grading_never_creates_evidence_and_can_be_retried(self):
        q=self.create()
        with patch.object(chat,'call_tool',side_effect=RuntimeError('PRIVATE rubric')):
            _,failed=self.answer(q)
        self.assertEqual(failed['status'],'failed'); self.assertNotIn('PRIVATE',json.dumps(failed))
        self.assertEqual(self.state()['evidence'],[])
        self.assertEqual(self.answer(q,key='new-after-fail')[1]['verdict'],'correct')

    def test_changed_classroom_during_generation_or_grading_discards_stale_result(self):
        def changed(*args,**kwargs):
            self.change(lambda state: state.update(revision=state['revision']+1))
            return self.model(*args,**kwargs)
        with patch.object(chat,'call_tool',side_effect=changed):
            _,stale=self.call(self.base+'/assessment',{})
        self.assertEqual(stale['status'],'failed'); self.assertNotIn('question',stale)
        q=self.call(self.base+'/assessment',{'retry':True})[1]
        with patch.object(chat,'call_tool',side_effect=changed): _,stale=self.answer(q)
        self.assertEqual(stale['status'],'failed'); self.assertEqual(self.state()['evidence'],[])

    def test_old_board_questions_are_not_reused(self):
        with self.connect() as db:
            row=db.execute('SELECT record FROM digital_boards').fetchone(); value=json.loads(row[0])
            value['result']['steps'][-1].update(question='LEGACY QUESTION',rubric='PRIVATE LEGACY ANSWER')
            db.execute('UPDATE digital_boards SET record=?',(json.dumps(value),))
        restored=self.call('/boards/source/lecture')[1]
        self.assertNotIn('LEGACY QUESTION',json.dumps(restored)); q=self.create()
        self.assertNotIn('LEGACY QUESTION',q['question'])
        self.assertNotIn('PRIVATE LEGACY',json.dumps(self.calls[-1][1]))

    def test_finished_or_busy_classroom_cannot_start_new_assessment(self):
        self.change(lambda state:state.update(completed=True))
        self.assertEqual(self.call(self.base+'/assessment',{})[0],409)
        self.change(lambda state:state.update(completed=False,job={'status':'pending'}))
        self.assertEqual(self.call(self.base+'/assessment',{})[0],409)


if __name__ == '__main__': unittest.main()
