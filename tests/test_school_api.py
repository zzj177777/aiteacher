"""Actual HTTP + background workers; all model calls use the local fixture."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from uuid import uuid4

from backend import school_learning as school


class SchoolApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        cls.url=f'http://127.0.0.1:{cls.port}'
        cls.env=dict(os.environ,COURSE_FIXTURE_PORT=str(cls.port))
        for key,name in [('AITEACHER_DB','classroom'),('AITEACHER_USAGE_DB','usage'),('AITEACHER_MODEL_DEBUG_DB','debug'),('AITEACHER_PLAIN_LANGUAGE_DB','plain')]:
            cls.env[key]=str(Path(cls.temp.name)/(name+'.sqlite3'))
        cls.start()

    @classmethod
    def start(cls):
        cls.process=subprocess.Popen([sys.executable,'tests/course_library_fixture.py'],cwd=Path(__file__).resolve().parents[1],
            env=cls.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urlopen(cls.url+'/api/health',timeout=1):return
            except OSError:time.sleep(.1)
        cls.process.terminate();cls.process.wait(timeout=10)
        raise RuntimeError('School API fixture did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=10);cls.temp.cleanup()

    def call(self,path,body=None,token=None,method=None):
        req=Request(self.url+path,method=method,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try:response=urlopen(req,timeout=8)
        except HTTPError as error:response=error
        with response:return response.status,json.load(response)

    def create(self,stage='primary',subject='math'):
        _,library=self.call('/api/learning-library',{})
        code,session=self.call('/api/sessions',{'mode':'chat','school_context':{'stage_id':stage,'subject_id':subject}},library['token'])
        self.assertEqual(code,200)
        return library,session

    def latest(self,session):
        code,data=self.call('/api/sessions/'+session['session_id'],token=session['token'])
        self.assertEqual(code,200);return data['snapshot']

    def send(self,session,kind,payload=None,key=None):
        snapshot=self.latest(session)
        body=dict(type=kind,payload=payload or {},expected_revision=snapshot['revision'],idempotency_key=key or str(uuid4()))
        code,result=self.call('/api/sessions/'+session['session_id']+'/events',body,session['token'])
        self.assertEqual(code,200,result)
        for _ in range(100):
            latest=self.latest(session)
            if not latest['working']:
                self.assertFalse(any(m.get('status')=='failed' for m in latest['messages']),latest['messages'][-1])
                return latest,body
            time.sleep(.05)
        self.fail('School teaching task did not finish')

    def test_all_21_entries_open_without_intake_or_model_calls(self):
        before=self.call('/_observed_school')[1]
        for stage,subjects in school.ALLOWED.items():
            for subject in subjects:
                library,session=self.create(stage,subject)
                snapshot=session['snapshot']
                context=snapshot['school_context']
                self.assertEqual(context,school.SchoolSelection(stage_id=stage,subject_id=subject).context())
                self.assertEqual(snapshot['profile']['goal'],'')
                self.assertIsNone(snapshot['plan']);self.assertFalse(snapshot['working'])
                rows=self.call('/api/learning-library',token=library['token'])[1]['unassigned_sessions']
                self.assertEqual(rows[0]['school_context'],context)
                self.assertIn(context['subject_label'],rows[0]['title'])
        self.assertEqual(self.call('/_observed_school')[1],before)

    def test_unknown_choose_confirm_and_scope_survive_http_and_restore(self):
        library,session=self.create()
        result,_=self.send(session,'chat_message',dict(text='我不知道学什么',recipient='auto'))
        self.assertEqual(len(result['topic_choices']),3);self.assertIsNone(result['plan'])
        choice=result['topic_choices'][0]
        result,body=self.send(session,'chat_choose_topic',dict(choice_id=choice['id']))
        self.assertEqual(result['plan']['goal'],'分数的意义')
        self.assertFalse(any(m['agent']=='lecturer' and m.get('status')=='ai' for m in result['messages']))
        self.assertEqual(result['topic_choices'],[])
        code,duplicate=self.call('/api/sessions/'+session['session_id']+'/events',body,session['token'])
        self.assertEqual(code,200);self.assertTrue(duplicate['duplicate'])
        before=self.latest(session)
        code,error=self.call('/api/sessions/'+session['session_id']+'/events',dict(type='chat_message',payload={'text':'我想学英语语法'},expected_revision=before['revision'],idempotency_key=str(uuid4())),session['token'])
        self.assertEqual(code,422)
        self.assertEqual(self.latest(session)['revision'],before['revision'])
        result,_=self.send(session,'chat_message',dict(text='开始吧'))
        self.assertTrue(any(m['agent']=='lecturer' and m.get('status')=='ai' for m in result['messages']))
        restored=self.call('/api/sessions/'+session['session_id'],token=library['token'])[1]['snapshot']
        self.assertEqual(restored['school_context'],session['snapshot']['school_context'])
        observed=self.call('/_observed_school')[1]
        for tool in ('suggest_learning_topics','arrange_learning','submit_lecturer_result'):
            self.assertTrue(any(r['tool']==tool and r['school_context']==restored['school_context'] for r in observed))
        traces=self.call('/api/sessions/'+session['session_id']+'/debug/planner',token=session['token'])[1]
        self.assertIn('suggest_learning_topics',json.dumps(traces))

    def test_specific_topic_does_not_require_recommendations(self):
        _,session=self.create()
        result,_=self.send(session,'chat_message',dict(text='我想学分数的意义'))
        self.assertEqual(result['plan']['goal'],'分数的意义')
        self.assertEqual(result['topic_choices'],[])
        self.assertNotIn('intake',result['profile'])

    def test_invalid_context_and_unauthorized_requests_are_rejected(self):
        for body in [dict(mode='chat',school_context={'stage_id':'primary','subject_id':'physics'}),
                     dict(mode='classic',school_context={'stage_id':'primary','subject_id':'math'}),
                     dict(mode='chat',course_id='fake-course',school_context={'stage_id':'primary','subject_id':'math'}),
                     dict(mode='chat',school_context={'stage_id':'primary','subject_id':'math','grade':'一年级'})]:
            self.assertEqual(self.call('/api/sessions',body)[0],422)
        _,session=self.create()
        self.assertEqual(self.call('/api/sessions/'+session['session_id'],token='other')[0],404)
        before=self.latest(session)
        code,_=self.call('/api/sessions/'+session['session_id']+'/events',dict(type='chat_choose_topic',payload={'choice_id':'invented'},expected_revision=before['revision'],idempotency_key=str(uuid4())),session['token'])
        self.assertEqual(code,422)
        self.assertEqual(self.latest(session)['revision'],before['revision'])

    def test_z_school_context_and_choices_survive_process_restart(self):
        _,session=self.create('junior','physics')
        result,_=self.send(session,'chat_suggest_topics')
        self.__class__.process.terminate();self.__class__.process.wait(timeout=10)
        self.__class__.start()
        restored=self.latest(session)
        self.assertEqual(restored['school_context'],result['school_context'])
        self.assertEqual(restored['topic_choices'],result['topic_choices'])

    def test_school_session_cannot_move_into_an_unrelated_course(self):
        library,session=self.create()
        code,course=self.call('/api/courses',dict(title='初中英语'),library['token'])
        self.assertEqual(code,200)
        code,_=self.call('/api/learning-library/sessions/'+session['session_id'],dict(course_id=course['id']),library['token'],method='PATCH')
        self.assertEqual(code,422)
        self.assertIsNone(self.latest(session)['course'])
        self.assertEqual(self.latest(session)['school_context']['subject_id'],'math')


if __name__=='__main__':unittest.main()
