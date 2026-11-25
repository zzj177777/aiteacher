"""Real HTTP coverage for durable course ownership and legacy-session migration."""
import json
from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class CourseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / 'classroom.sqlite3'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{cls.port}'
        cls.env = dict(os.environ, AITEACHER_DB=str(cls.db), AI_API_URL='', AI_API_KEY='', AI_MODEL='',
            AITEACHER_USAGE_DB=str(Path(cls.temp.name)/'usage.sqlite3'),
            AITEACHER_MODEL_DEBUG_DB=str(Path(cls.temp.name)/'debug.sqlite3'),
            AITEACHER_PLAIN_LANGUAGE_DB=str(Path(cls.temp.name)/'plain.sqlite3'))
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app:app', '--host',
            '127.0.0.1', '--port', str(cls.port)], cwd=Path(__file__).resolve().parents[1], env=cls.env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                with urlopen(cls.url+'/api/health', timeout=1):
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError('Isolated course test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()

    def call(self, path, method='GET', body=None, token=None):
        req = Request(self.url+path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+token} if token else {})})
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def library(self):
        status, result = self.call('/api/learning-library', 'POST')
        self.assertEqual(status, 200)
        return result['token']

    def course(self, token, title='初二数学'):
        status, result = self.call('/api/courses', 'POST', {'title':title,'description':'跟上学校进度'}, token)
        self.assertEqual(status, 200)
        return result

    def lesson(self, token=None, course=None):
        status, result = self.call('/api/sessions', 'POST', {'mode':'chat','course_id':course,'title':'一次函数'}, token)
        self.assertEqual(status, 200)
        return result

    def test_create_resume_and_progress_preservation(self):
        token = self.library()
        course = self.course(token)
        lesson = self.lesson(token, course['id'])
        sid = lesson['session_id']
        with closing(sqlite3.connect(self.db)) as db, db:
            state = json.loads(db.execute('SELECT state FROM sessions WHERE id=?', (sid,)).fetchone()[0])
            state['revision'] = 8
            state['profile']['goal'] = '一次函数入门'
            state['plan'] = dict(id='p',goal='一次函数',steps=['含义','图像'],nodes=[
                dict(id='a',title='含义',status='completed',delivered=True),
                dict(id='b',title='图像',status='current',delivered=True)])
            state['evidence'] = [dict(question='判断图像',answer='直线',verdict='correct',observation='模型判断',source='assessment')]
            db.execute('UPDATE sessions SET state=? WHERE id=?', (json.dumps(state), sid))
        status, listing = self.call('/api/courses/'+course['id'], token=token)
        self.assertEqual(status, 200)
        self.assertEqual(listing['sessions'][0]['confirmed_nodes'], 1)
        self.assertEqual(listing['sessions'][0]['total_nodes'], 2)
        self.assertEqual(listing['sessions'][0]['title'], '一次函数入门')
        self.assertEqual(listing['sessions'][0]['current_node'], '图像')
        for credential in (token, lesson['token']):
            status, resumed = self.call('/api/sessions/'+sid, token=credential)
            self.assertEqual(status, 200)
            self.assertEqual(resumed['snapshot']['revision'], 8)
            self.assertEqual(resumed['snapshot']['evidence'], state['evidence'])
            self.assertEqual(resumed['snapshot']['course']['title'], '初二数学')
        self.assertNotIn('token', json.dumps(listing))

    def test_other_library_cannot_read_link_or_edit(self):
        owner, other = self.library(), self.library()
        course = self.course(owner)
        lesson = self.lesson(owner, course['id'])
        other_course = self.course(other, '英语')
        for path in ('/api/courses/'+course['id'], '/api/sessions/'+lesson['session_id'],
                     '/api/sessions/'+lesson['session_id']+'/usage', '/api/sessions/'+lesson['session_id']+'/debug/planner'):
            self.assertEqual(self.call(path, token=other)[0], 404)
        self.assertEqual(self.call('/api/courses/'+course['id'],'PATCH',{'title':'越权修改'},other)[0],404)
        self.assertEqual(self.call('/api/learning-library/sessions/'+lesson['session_id'],'PATCH',{'course_id':other_course['id']},other)[0],404)
        self.assertEqual(self.call('/api/learning-library/sessions/'+lesson['session_id'],'PATCH',{'course_id':other_course['id']},owner)[0],404)
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat','course_id':course['id']},other)[0],404)
        self.assertEqual(self.call('/api/learning-library',token=lesson['token'])[0],404)
        self.assertEqual(self.call('/api/learning-library')[0],401)

    def test_legacy_import_is_partial_idempotent_and_does_not_claim_other_space(self):
        owner, other = self.library(), self.library()
        old = self.lesson()
        bad = self.lesson()
        payload={'sessions':[dict(session_id=old['session_id'],token=old['token'],title='历史函数课'),
                             dict(session_id=bad['session_id'],token='wrong',title='不可导入')]}
        status,result=self.call('/api/learning-library/import','POST',payload,owner)
        self.assertEqual(status,200)
        self.assertEqual(result['imported'],[old['session_id']])
        self.assertEqual(result['rejected'],[bad['session_id']])
        self.assertEqual(self.call('/api/learning-library/import','POST',payload,owner)[1],result)
        stolen=self.call('/api/learning-library/import','POST',{'sessions':[payload['sessions'][0]]},other)[1]
        self.assertEqual(stolen['rejected'],[old['session_id']])
        self.assertEqual(self.call('/api/sessions/'+old['session_id'],token=other)[0],404)
        listing=self.call('/api/learning-library',token=owner)[1]
        self.assertEqual(len(listing['unassigned_sessions']),1)
        self.assertEqual(listing['unassigned_sessions'][0]['title'],'历史函数课')
        self.assertEqual(self.call('/api/sessions/'+old['session_id'],token=old['token'])[0],200)

    def test_moves_preserve_session_and_current_course_context(self):
        token=self.library()
        one,two=self.course(token,'初二数学'),self.course(token,'数学复习')
        lesson=self.lesson(token,one['id']);sid=lesson['session_id']
        before=self.call('/api/sessions/'+sid,token=token)[1]['snapshot']
        self.assertEqual(self.call('/api/learning-library/sessions/'+sid,'PATCH',{'course_id':two['id']},token)[0],200)
        after=self.call('/api/sessions/'+sid,token=token)[1]['snapshot']
        self.assertEqual(after['course']['title'],'数学复习')
        for key in ('revision','messages','plan','evidence','completed'):
            self.assertEqual(after[key],before[key])
        self.call('/api/courses/'+two['id'],'PATCH',{'title':'期末数学复习','description':'查漏补缺'},token)
        self.assertEqual(self.call('/api/sessions/'+sid,token=token)[1]['snapshot']['course']['title'],'期末数学复习')
        self.assertEqual(self.call('/api/learning-library/sessions/'+sid,'PATCH',{'course_id':None},token)[0],200)
        self.assertIsNone(self.call('/api/sessions/'+sid,token=token)[1]['snapshot']['course'])
        self.assertEqual(len(self.call('/api/learning-library',token=token)[1]['unassigned_sessions']),1)

    def test_validation_and_authenticated_unassigned_creation(self):
        token=self.library();course=self.course(token)
        for body in ({'title':'   '},{'title':'a'*81},{'title':'课程','description':'a'*401}):
            self.assertEqual(self.call('/api/courses','POST',body,token)[0],422)
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat','course_id':course['id']})[0],401)
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'classic'},token)[0],422)
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat'},'invalid-library-token')[0],404)
        lesson=self.lesson(token)
        self.assertEqual(len(self.call('/api/learning-library',token=token)[1]['unassigned_sessions']),1)
        self.assertEqual(self.call('/api/learning-library/sessions/'+lesson['session_id'],'PATCH',{'course_id':'unknown'},token)[0],404)

    def test_courses_and_linked_session_survive_server_restart(self):
        token=self.library();course=self.course(token);lesson=self.lesson(token,course['id'])
        self.__class__.process.terminate();self.__class__.process.wait(timeout=10)
        self.__class__.start_server()
        listing=self.call('/api/learning-library',token=token)[1]
        self.assertEqual(listing['courses'][0]['id'],course['id'])
        self.assertEqual(listing['courses'][0]['session_count'],1)
        self.assertEqual(self.call('/api/sessions/'+lesson['session_id'],token=token)[0],200)

    def test_course_context_contains_no_capability_or_invented_mastery(self):
        from backend import chat_classroom
        state=chat_classroom.new_state()
        state['course']=dict(id='course-id',title='初二数学',description='循序渐进')
        context=chat_classroom.context(state)
        self.assertEqual(context['course'],{'title':'初二数学','description':'循序渐进'})
        self.assertEqual(context['evidence'],[])
        self.assertNotIn('course-id',json.dumps(context))

    def test_wrong_subject_is_blocked_in_intake_and_every_chat_recipient_without_state_changes(self):
        token=self.library();course=self.course(token);lesson=self.lesson(token,course['id']);sid=lesson['session_id']
        with closing(sqlite3.connect(self.db)) as db, db:
            state=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()[0])
            state['pending_question']={'id':'waiting','question':'一次函数的图像是什么？','objective':'检查理解','rubric':'private-answer'}
            db.execute('UPDATE sessions SET state=? WHERE id=?',(json.dumps(state),sid))
        before=self.call('/api/sessions/'+sid,token=token)[1]['snapshot']
        for recipient in ('auto','planner','lecturer','assessment'):
            status,_=self.call('/api/sessions/'+sid+'/events','POST',{'expected_revision':0,'idempotency_key':'scope-'+recipient,
                'type':'chat_message','payload':{'text':'我想学习英语语法','recipient':recipient}},token)
            self.assertEqual(status,422)
        status,_=self.call('/api/sessions/'+sid+'/events','POST',{'expected_revision':0,'idempotency_key':'scope-intake',
            'type':'chat_intake','payload':{'topic':'英语单词','goals':['入门理解'],'stage':'初中'}},token)
        self.assertEqual(status,422)
        self.assertEqual(self.call('/api/sessions/'+sid,token=token)[1]['snapshot'],before)

    def test_wrong_subject_cannot_be_created_moved_or_introduced_by_course_rename(self):
        token=self.library();course=self.course(token);self.lesson(token,course['id'])
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat','course_id':course['id'],'title':'英语语法'},token)[0],422)
        english=self.call('/api/sessions','POST',{'mode':'chat','title':'英语语法'},token)[1]
        self.assertEqual(self.call('/api/learning-library/sessions/'+english['session_id'],'PATCH',{'course_id':course['id']},token)[0],422)
        self.assertEqual(self.call('/api/courses/'+course['id'],'PATCH',{'title':'初中英语'},token)[0],422)
        listing=self.call('/api/learning-library',token=token)[1]
        self.assertEqual(listing['courses'][0]['title'],'初二数学')
        self.assertEqual(listing['courses'][0]['session_count'],1)
        self.assertEqual(listing['unassigned_sessions'][0]['id'],english['session_id'])
