"""Real HTTP tests with a temporary database; no external model or extra test dependencies."""
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
from urllib.request import Request, urlopen
from uuid import uuid4


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}'
        env = dict(os.environ, AITEACHER_DB=str(Path(cls.temp.name)/'test.sqlite3'), AI_API_URL='', AI_API_KEY='', AI_MODEL='')
        cls.process = subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(port)], cwd=Path(__file__).resolve().parents[1], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                with urlopen(cls.url+'/api/health',timeout=1): return
            except OSError:
                time.sleep(.1)
        cls.process.terminate(); cls.temp.cleanup()
        raise RuntimeError('test server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate(); cls.process.wait(timeout=10); cls.temp.cleanup()

    def call(self,path,method='GET',body=None,token=None):
        req = Request(self.url+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try:
            with urlopen(req,timeout=5) as response: return response.status,json.load(response)
        except HTTPError as e:
            return e.code,json.load(e)

    def test_selection_explanation_auth_validation_and_no_progress_change(self):
        _,data=self.call('/api/sessions','POST',{'mode':'chat'})
        path='/api/sessions/'+data['session_id']; token=data['token']
        original=data['snapshot']
        payload={'message_id':original['messages'][0]['id'],'text':'教学安排'}
        self.assertEqual(self.call(path+'/explain','POST',payload)[0],401)
        self.assertEqual(self.call(path+'/explain','POST',payload,'wrong')[0],404)
        self.assertEqual(self.call(path+'/explain','POST',{'message_id':'missing','text':'词句'},token)[0],422)
        self.assertEqual(self.call(path+'/explain','POST',{'message_id':payload['message_id'],'text':'x'*2001},token)[0],422)
        self.assertEqual(self.call(path+'/explain','POST',payload,token)[0],503)
        _,restored=self.call(path,token=token)
        self.assertEqual(restored['snapshot'],original)

    def test_generic_chat_mode_persists_failure_and_report(self):
        status, data = self.call('/api/sessions','POST',{'mode':'chat'})
        self.assertEqual(status,200)
        path='/api/sessions/'+data['session_id']; token=data['token']
        self.assertEqual(data['snapshot']['mode'],'chat')
        self.assertNotIn('matrix',data['snapshot'])
        def submit(kind,payload):
            nonlocal data
            event={'expected_revision':data['snapshot']['revision'],'idempotency_key':str(uuid4()),'type':kind,'payload':payload}
            status,data=self.call(path+'/events','POST',event,token)
            self.assertEqual(status,200)
            for _ in range(30):
                _,data=self.call(path,token=token)
                if not data['snapshot']['working']:break
                time.sleep(.05)
            return event
        event=submit('chat_message',{'text':'我想学积分'})
        self.assertFalse(data['snapshot']['working'])
        self.assertEqual(data['snapshot']['messages'][-1]['status'],'failed')
        status,duplicate=self.call(path+'/events','POST',event,token)
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(sum(m['agent']=='student' for m in duplicate['snapshot']['messages']),1)
        submit('chat_end',{})
        self.assertTrue(data['snapshot']['completed'])
        _,report=self.call(path+'/report',token=token)
        self.assertEqual(report['status'],'ready')

    def test_plain_language_auth_and_invalid_source(self):
        _,created=self.call('/api/sessions','POST',{'mode':'chat'})
        path='/api/sessions/'+created['session_id']+'/plain-language';token=created['token']
        self.assertEqual(self.call(path)[0],401)
        self.assertEqual(self.call(path,token='wrong')[0],404)
        self.assertEqual(self.call(path,token=token)[1]['explanations'],[])
        body={'message_id':created['snapshot']['messages'][0]['id']}
        self.assertEqual(self.call(path,'POST',body)[0],401)
        self.assertEqual(self.call(path,'POST',body,token)[0],422)
        _,classic=self.call('/api/sessions','POST',{'mode':'classic'})
        self.assertEqual(self.call('/api/sessions/'+classic['session_id']+'/plain-language',token=classic['token'])[0],422)

    def test_planner_debug_requires_session_credential(self):
        _,created=self.call('/api/sessions','POST',{'mode':'chat'})
        path='/api/sessions/'+created['session_id']+'/debug/planner'
        self.assertEqual(self.call(path)[0],401)
        self.assertEqual(self.call(path,token='wrong')[0],404)
        status,data=self.call(path,token=created['token'])
        self.assertEqual(status,200)
        self.assertEqual(data,{'calls':[],'limit':30})
        _,classic=self.call('/api/sessions','POST',{'mode':'classic'})
        self.assertEqual(self.call('/api/sessions/'+classic['session_id']+'/debug/planner',token=classic['token'])[0],422)

    def test_chat_intake_persistence_validation_and_idempotency(self):
        _,created=self.call('/api/sessions','POST',{'mode':'chat'})
        path='/api/sessions/'+created['session_id'];token=created['token']
        payload={'topic':'分数','goals':['入门理解'],'stage':'小学','grade':'三年级'}
        event={'expected_revision':0,'idempotency_key':str(uuid4()),'type':'chat_intake','payload':{**payload,'topic':''}}
        self.assertEqual(self.call(path+'/events','POST',event,token)[0],422)
        _,unchanged=self.call(path,token=token)
        self.assertEqual(unchanged['snapshot'],created['snapshot'])
        event.update(idempotency_key=str(uuid4()),payload=payload)
        self.assertEqual(self.call(path+'/events','POST',event)[0],401)
        status,accepted=self.call(path+'/events','POST',event,token)
        self.assertEqual(status,200)
        status,duplicate=self.call(path+'/events','POST',event,token)
        self.assertEqual(status,200)
        self.assertTrue(duplicate['duplicate'])
        _,restored=self.call(path,token=token)
        snapshot=restored['snapshot']
        self.assertEqual(snapshot['profile']['intake']['source'],'student_self_report')
        self.assertEqual(snapshot['profile']['intake']['grade'],'三年级')
        self.assertEqual(sum(m['agent']=='student' for m in snapshot['messages']),1)
        self.assertEqual(snapshot['evidence'],[])

    def test_planner_confirmation_and_background_tool(self):
        status, data = self.call('/api/sessions', 'POST', {'mode':'planner'})
        self.assertEqual(status, 200)
        path = '/api/sessions/' + data['session_id']; token = data['token']
        self.assertEqual(data['snapshot']['phase'], 'planning')
        def submit(kind, payload):
            nonlocal data
            status, data = self.call(path+'/events', 'POST', {'expected_revision':data['snapshot']['revision'], 'idempotency_key':str(uuid4()), 'type':kind, 'payload':payload}, token)
            self.assertEqual(status, 200)
            for _ in range(30):
                _, data = self.call(path, token=token)
                if data['snapshot']['planner']['status'] != 'pending': break
                time.sleep(.05)
            return data['snapshot']
        snapshot = submit('planner_message', {'text':'我想学三阶行列式'})
        self.assertEqual(snapshot['planner']['status'], 'awaiting_confirmation')
        self.assertEqual(snapshot['planner']['history'][-1]['source'], 'fallback')
        snapshot = submit('confirm_learning_plan', {'plan_id':snapshot['planner']['plan']['id']})
        self.assertEqual(snapshot['phase'], 'diagnosis')
        for _ in range(3): snapshot = submit('submit_diagnostic_answer', {'choice':0})
        self.assertEqual(snapshot['phase'], 'lecture')
        self.assertEqual(snapshot['planner']['history'][-1]['tool'], 'start_teaching')
        self.assertIsNotNone(snapshot['teaching_task'])

    def test_restore_auth_idempotency_conflict(self):
        status,s = self.call('/api/sessions','POST')
        self.assertEqual(status,200)
        path = '/api/sessions/'+s['session_id']; token=s['token']
        self.assertEqual(self.call(path)[0],401)
        self.assertEqual(self.call(path,token='wrong')[0],404)
        event={'expected_revision':0,'idempotency_key':str(uuid4()),'type':'submit_diagnostic_answer','payload':{'choice':0}}
        status,first=self.call(path+'/events','POST',event,token)
        self.assertEqual(status,200)
        self.assertEqual(first['snapshot']['revision'],1)
        status,second=self.call(path+'/events','POST',event,token)
        self.assertTrue(second['duplicate'])
        self.assertEqual(second['snapshot']['diagnostic_index'],1)
        event['idempotency_key']=str(uuid4())
        self.assertEqual(self.call(path+'/events','POST',event,token)[0],409)
        self.assertEqual(self.call(path,token=token)[1]['snapshot']['revision'],1)

    def test_invalid_event_atomic_and_report(self):
        _,s=self.call('/api/sessions','POST'); path='/api/sessions/'+s['session_id']; token=s['token']
        event={'expected_revision':0,'idempotency_key':str(uuid4()),'type':'submit_diagnostic_answer','payload':{'choice':True}}
        self.assertEqual(self.call(path+'/events','POST',event,token)[0],422)
        self.assertEqual(self.call(path,token=token)[1]['snapshot']['revision'],0)
        self.assertEqual(self.call(path+'/report',token=token)[1]['status'],'not_ready')
        event.update(type='finish',payload={},idempotency_key=str(uuid4()))
        self.assertEqual(self.call(path+'/events','POST',event,token)[0],200)
        report=self.call(path+'/report',token=token)[1]
        self.assertEqual(report['status'],'ready'); self.assertFalse(report['report']['passed'])

    def test_diagnostic_dispatch_and_lecture_return(self):
        _,s=self.call('/api/sessions','POST'); path='/api/sessions/'+s['session_id']; token=s['token']
        revision=0
        for _ in range(3):
            event={'expected_revision':revision,'idempotency_key':str(uuid4()),'type':'submit_diagnostic_answer','payload':{'choice':0}}
            status,data=self.call(path+'/events','POST',event,token)
            self.assertEqual(status,200); revision=data['snapshot']['revision']
        self.assertEqual(data['snapshot']['phase'],'lecture')
        self.assertEqual(data['snapshot']['teaching_task']['status'],'ready')
        task_id=data['snapshot']['teaching_task']['id']
        event={'expected_revision':revision,'idempotency_key':str(uuid4()),'type':'finish_lecture','payload':{}}
        self.assertEqual(self.call(path+'/events','POST',event,token)[0],422)
        for index,answer in enumerate([1,'-2','-6']):
            task=data['snapshot']['teaching_task']
            check=task['segment']['check']
            self.assertNotIn('answer',check)
            event={'expected_revision':revision,'idempotency_key':str(uuid4()),'type':'submit_teaching_check','payload':{'task_id':task_id,'check_id':check['id'],'answer':answer}}
            status,data=self.call(path+'/events','POST',event,token)
            self.assertEqual(status,200); revision=data['snapshot']['revision']
            if index<2:
                event={'expected_revision':revision,'idempotency_key':str(uuid4()),'type':'next_teaching_segment','payload':{}}
                status,data=self.call(path+'/events','POST',event,token)
                self.assertEqual(status,200); revision=data['snapshot']['revision']
        event={'expected_revision':revision,'idempotency_key':str(uuid4()),'type':'finish_lecture','payload':{}}
        status,data=self.call(path+'/events','POST',event,token)
        self.assertEqual(status,200)
        self.assertEqual(data['snapshot']['phase'],'guided_practice')
        self.assertIsNone(data['snapshot']['teaching_task'])
        self.assertTrue(any(m.get('task_id')==task_id and m['agent']=='lecturer' for m in data['snapshot']['messages']))

    def test_check_remedy_and_pause_survive_http_restore(self):
        _,created=self.call('/api/sessions','POST')
        path='/api/sessions/'+created['session_id']; token=created['token']; data=created
        def submit(kind,payload):
            nonlocal data
            event={'expected_revision':data['snapshot']['revision'],'idempotency_key':str(uuid4()),'type':kind,'payload':payload}
            status,data=self.call(path+'/events','POST',event,token)
            self.assertEqual(status,200)
        for _ in range(3): submit('submit_diagnostic_answer',{'choice':0})
        task=data['snapshot']['teaching_task']; task_id=task['id']; old_id=task['segment']['check']['id']
        submit('submit_teaching_check',{'task_id':task_id,'check_id':old_id,'answer':0})
        task=data['snapshot']['teaching_task']; new_id=task['segment']['check']['id']
        self.assertNotEqual(old_id,new_id)
        submit('pause_lecture',{})
        _,data=self.call(path,token=token)
        self.assertEqual(data['snapshot']['phase'],'guided_practice')
        submit('resume_lecture',{'task_id':task_id})
        task=data['snapshot']['teaching_task']
        self.assertEqual(task['segment']['check']['id'],new_id)
        self.assertEqual(len(task['session']['checks']),1)
        submit('finish',{})
        _,report=self.call(path+'/report',token=token)
        self.assertEqual(report['report']['teaching_sessions'][0]['checks'][0]['correct'],False)


if __name__ == '__main__':
    unittest.main()
