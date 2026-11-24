import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import BackgroundTasks,HTTPException

from backend import plain_language as plain,chat_classroom as chat,app as server


SOURCE={'id':'lecture-1','agent':'lecturer','status':'ai','text':'分母表示把整体平均分成了多少份。分子表示取了其中几份。','objective':'理解分子和分母'}


def result():
    return {'takeaway':'先平均分，再看取了几份。','concepts':[
        {'term':'分母','quote':'分母表示把整体平均分成了多少份。','why_difficult':'可能把分的总份数和拿的份数混淆。','explanation':'它告诉你，一整个东西被平均分成几份。',
         'example':'把一张饼平均分成4块，分母就是4。','boundary':'必须平均分，每块一样大。'}]}


class PlainLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'AITEACHER_PLAIN_LANGUAGE_DB':str(Path(self.temp.name)/'plain.sqlite3')});self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()

    def test_grounded_result_uses_only_lecture_and_self_report(self):
        state=chat.new_state();state['profile'].update(background='刚学分数',intake={'stage':'小学','grade':'三年级','topic':'旧目标'})
        state['pending_question']={'question':'问题','objective':'测试','rubric':'private-key'}
        data=plain.context(state,SOURCE)
        self.assertNotIn('private-key',json.dumps(data));self.assertNotIn('旧目标',json.dumps(data))
        with patch.object(plain,'call_tool',return_value={'tool':'explain_lecture_plainly','arguments':result()}) as model:
            output=plain.generate(data)
        self.assertEqual(output,result())
        self.assertEqual(model.call_args.args[1]['lecture'],SOURCE['text'])
        self.assertEqual(model.call_args.args[1]['student_self_report']['grade'],'三年级')

    def test_enqueues_once_for_same_source_and_isolates_sessions(self):
        first,requested=plain.enqueue('session-a',SOURCE,'job-1');self.assertTrue(requested)
        duplicate,requested=plain.enqueue('session-a',SOURCE,'job-2');self.assertFalse(requested)
        self.assertEqual(duplicate['id'],first['id'])
        self.assertEqual(plain.recent('session-b')['explanations'],[])
        with patch.object(plain,'generate',return_value=result()):plain.run('session-a',first['id'],{})
        cached,requested=plain.enqueue('session-a',SOURCE)
        self.assertFalse(requested);self.assertEqual(cached['status'],'completed')

    def test_rejects_unquoted_or_oversized_or_unstructured_output(self):
        cases=[]
        bad=result();bad['concepts'][0]['quote']='不存在于授课中的文字';cases.append((bad,'plain_language_grounding'))
        bad=result();bad['concepts']*=4;cases.append((bad,'plain_language_concepts'))
        bad=result();bad['concepts'][0]['explanation']='字'*91;cases.append((bad,'plain_language_length'))
        bad=result();bad['takeaway']='字'*61;cases.append((bad,'plain_language_length'))
        bad=result();bad['concepts'][0]['extra']='unexpected';cases.append((bad,'plain_language_fields'))
        bad=result();bad['takeaway']='字'*60;bad['concepts']=[{**bad['concepts'][0],'term':'字'*30,'explanation':'字'*90,'example':'','boundary':'注意边界'} for _ in range(2)];cases.append((bad,'plain_language_length'))
        for output,code in cases:
            with self.subTest(code=code),patch.object(plain,'call_tool',return_value={'tool':'explain_lecture_plainly','arguments':output}):
                with self.assertRaises(ValueError) as error:plain.generate({'lecture':SOURCE['text']})
                self.assertEqual(error.exception.code,code)

    def test_failure_is_safe_and_retry_cannot_be_overwritten_by_old_job(self):
        first,_=plain.enqueue('session-a',SOURCE)
        with patch.object(plain,'generate',side_effect=RuntimeError('private-secret-prompt')):plain.run('session-a',first['id'],{})
        failed=plain.recent('session-a')['explanations'][0]
        self.assertEqual(failed['status'],'failed');self.assertNotIn('private-secret-prompt',json.dumps(failed))
        retry,requested=plain.enqueue('session-a',SOURCE);self.assertTrue(requested);self.assertNotEqual(first['id'],retry['id'])
        with patch.object(plain,'generate',return_value=result()):plain.run('session-a',first['id'],{})
        self.assertEqual(plain.recent('session-a')['explanations'][0]['status'],'pending')
        with patch.object(plain,'generate',return_value=result()):plain.run('session-a',retry['id'],{})
        self.assertEqual(plain.recent('session-a')['explanations'][0]['status'],'completed')

    def test_old_and_new_lecture_results_are_separate(self):
        old,_=plain.enqueue('session-a',SOURCE)
        newer,_=plain.enqueue('session-a',{**SOURCE,'id':'lecture-2'})
        with patch.object(plain,'generate',return_value=result()):
            plain.run('session-a',newer['id'],{});plain.run('session-a',old['id'],{})
        records=plain.recent('session-a')['explanations']
        self.assertEqual(records[0]['source_message_id'],'lecture-2')
        self.assertEqual({r['source_message_id'] for r in records},{'lecture-1','lecture-2'})

    def test_restart_marks_pending_failed_without_overwriting_completed(self):
        pending,_=plain.enqueue('a',SOURCE)
        ready,_=plain.enqueue('a',{**SOURCE,'id':'lecture-2'})
        with patch.object(plain,'generate',return_value=result()):plain.run('a',ready['id'],{})
        plain.recover()
        records={item['id']:item for item in plain.recent('a')['explanations']}
        self.assertEqual(records[pending['id']]['error']['code'],'plain_language_interrupted')
        self.assertEqual(records[ready['id']]['status'],'completed')

    def test_retention_is_bounded(self):
        for i in range(35):plain.enqueue('a',{**SOURCE,'id':str(i)})
        self.assertEqual(len(plain.recent('a')['explanations']),30)

    def test_legacy_result_remains_readable_and_can_be_upgraded(self):
        record,_=plain.enqueue('a',SOURCE)
        legacy={**record,'status':'completed','format_version':1,'result':result()}
        legacy['result']['concepts'][0].pop('why_difficult')
        db=plain.connect()
        try:
            with db:db.execute('UPDATE lecture_explanations SET record=? WHERE id=?',(json.dumps(legacy),record['id']))
        finally:db.close()
        self.assertEqual(plain.recent('a')['explanations'][0]['format_version'],1)
        upgraded,requested=plain.enqueue('a',SOURCE)
        self.assertTrue(requested);self.assertEqual(upgraded['format_version'],2)
        self.assertNotEqual(upgraded['id'],record['id'])

    def test_explains_difficulty_and_orders_by_original_passage(self):
        output=result()
        output['concepts'].insert(0,{'term':'分子','quote':'分子表示取了其中几份。','why_difficult':'可能不清楚分数上面的数在数什么。','explanation':'看拿了几份。','example':'','boundary':''})
        with patch.object(plain,'call_tool',return_value={'tool':'explain_lecture_plainly','arguments':output}):
            value=plain.generate({'lecture':SOURCE['text']})
        self.assertEqual([item['term'] for item in value['concepts']],['分母','分子'])
        self.assertTrue(all(item['why_difficult'] for item in value['concepts']))
        bad=result();bad['concepts'][0]['why_difficult']=''
        with patch.object(plain,'call_tool',return_value={'tool':'explain_lecture_plainly','arguments':bad}):
            with self.assertRaises(ValueError):plain.generate({'lecture':SOURCE['text']})

    def test_clear_passage_does_not_require_fabricated_difficulties(self):
        output={'takeaway':'这段已用直白的表达说明。','concepts':[]}
        with patch.object(plain,'call_tool',return_value={'tool':'explain_lecture_plainly','arguments':output}):
            self.assertEqual(plain.generate({'lecture':'一加一等于二。'}),output)

    def test_manual_api_validates_source_deduplicates_and_does_not_change_classroom(self):
        state=chat.new_state();state['messages'].append(SOURCE.copy());original=copy.deepcopy(state)
        with patch.object(server,'DB_PATH',Path(self.temp.name)/'classroom.sqlite3'),patch.object(server,'read_session',return_value=state):
            with self.assertRaises(HTTPException):server.request_lecture_explanation('a',server.ExplainLecture(message_id='missing'),BackgroundTasks(),'token')
            tasks=BackgroundTasks()
            first=server.request_lecture_explanation('a',server.ExplainLecture(message_id=SOURCE['id']),tasks,'token')
            self.assertEqual(len(tasks.tasks),1)
            other_tasks=BackgroundTasks()
            second=server.request_lecture_explanation('a',server.ExplainLecture(message_id=SOURCE['id']),other_tasks,'token')
            self.assertEqual(len(other_tasks.tasks),0);self.assertEqual(first['id'],second['id'])
        self.assertEqual(state,original)


class MainClassroomIsolationTests(unittest.TestCase):
    def test_optional_agent_failure_does_not_rollback_main_lecture(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(server,'DB_PATH',Path(directory)/'classroom.sqlite3'):
            with server.connect() as db:
                db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY,token_hash TEXT,state TEXT,created_at TEXT);CREATE TABLE events(session_id TEXT,event_key TEXT,kind TEXT,payload TEXT,response TEXT,created_at TEXT,PRIMARY KEY(session_id,event_key));')
                state=chat.new_state();chat.event(state,'chat_message',{'text':'解释分数','recipient':'lecturer'})
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',('session-a','hash',json.dumps(state),'today'))
            lecture={'message':SOURCE['text'],'covered':'分母和分子','next_suggestion':'检查理解','visuals':[]}
            with patch.object(server,'configured',return_value=True),patch.object(chat,'specialist',return_value=lecture),patch.object(plain,'enqueue',side_effect=OSError('private-path')),self.assertLogs('backend.app',level='ERROR') as logs:
                server.run_chat('session-a',state['job']['id'],state)
            with server.connect() as db:saved=json.loads(db.execute('SELECT state FROM sessions').fetchone()['state'])
            self.assertEqual(saved['job']['status'],'completed')
            self.assertTrue(any(m['agent']=='lecturer' and m.get('status')=='ai' for m in saved['messages']))
            self.assertEqual(saved['evidence'],[])
            self.assertNotIn('private-path',''.join(logs.output))
