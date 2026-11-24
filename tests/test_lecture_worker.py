import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import app as server
from backend.lesson import new_state, apply_event


class LectureWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = patch.object(server,'DB_PATH',Path(self.temp.name)/'worker.sqlite3')
        self.database.start()
        with server.connect() as db:
            db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, token_hash TEXT, state TEXT, created_at TEXT)')
        with patch('backend.lecturer.configured',return_value=True):
            self.state = new_state()
            for _ in range(3):
                apply_event(self.state,'submit_diagnostic_answer',{'choice':0})
        self.state['revision']=3
        self.save(self.state)

    def tearDown(self):
        self.database.stop(); self.temp.cleanup()

    def save(self,state):
        with server.connect() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',('test','hash',json.dumps(state),'today'))

    def read(self):
        with server.connect() as db:
            return json.loads(db.execute('SELECT state FROM sessions WHERE id=?',('test',)).fetchone()['state'])

    def test_model_lecture_completes_real_task(self):
        task=server.current_task(self.state)
        with patch.object(server,'remote_lecture',return_value='本次模型讲解'):
            server.enrich_lecture('test',3,task['id'],self.state)
        state=self.read(); task=server.current_task(state)
        self.assertEqual(task['status'],'ready')
        self.assertEqual(task['source'],'ai')
        lecture=next(m for m in state['messages'] if m['id']==task['message_id'])
        self.assertEqual(lecture['text'],'本次模型讲解')
        self.assertEqual(lecture['status'],'ai')
        self.assertFalse(state['completed'])

    def test_new_chat_revision_does_not_discard_current_segment(self):
        task=server.current_task(self.state)
        newer=json.loads(json.dumps(self.state)); newer['revision']=4; self.save(newer)
        with patch.object(server,'remote_lecture',return_value='同一教学段仍然有效'):
            server.enrich_lecture('test',3,task['id'],self.state)
        state=self.read()
        self.assertIn('同一教学段仍然有效',str(state))
        self.assertEqual(state['revision'],4)
        self.assertEqual(server.current_task(state)['status'],'ready')

    def test_old_segment_generation_is_discarded(self):
        task=server.current_task(self.state)
        context=json.loads(json.dumps(self.state))
        task['session']['generation_id']='new-generation'
        self.save(self.state)
        with patch.object(server,'remote_lecture',return_value='stale-output'):
            server.enrich_lecture('test',3,task['id'],context)
        state=self.read()
        self.assertNotIn('stale-output',str(state))
        self.assertEqual(server.current_task(state)['status'],'pending')

    def test_failure_keeps_local_lecture_ready(self):
        task=server.current_task(self.state)
        with patch.object(server,'remote_lecture',side_effect=RuntimeError('private-provider-error')):
            server.enrich_lecture('test',3,task['id'],self.state)
        state=self.read()
        self.assertEqual(server.current_task(state)['source'],'local')
        self.assertNotIn('private-provider-error',str(state))

    def test_restart_recovers_pending_lecture(self):
        server.recover_interrupted_generations()
        state=self.read()
        self.assertEqual(server.current_task(state)['status'],'ready')
        self.assertFalse(any(m.get('status')=='pending' for m in state['messages']))

    def test_finishing_cancels_pending_work(self):
        task=server.current_task(self.state)
        context=json.loads(json.dumps(self.state))
        apply_event(self.state,'finish',{}); self.save(self.state)
        with patch.object(server,'remote_lecture',return_value='不应该回写'):
            server.enrich_lecture('test',3,task['id'],context)
        state=self.read()
        self.assertEqual(state['phase'],'report')
        self.assertIsNone(server.current_task(state))
        self.assertFalse(any(m.get('status')=='pending' for m in state['messages']))
