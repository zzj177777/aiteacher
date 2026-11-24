"""Planner traces capture wire bodies, survive failures, and stay session scoped."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import chat_classroom as chat,model_debug as debug,tutor


def decision(action='plan'):
    return dict(action=action,message='先看这个安排。',reason='依据学习目标',goal='学习分数',
                background='学生自述刚开始学习',objective='理解平均分',
                steps=['平均分','分数意义'],plan_update='keep')


def response(arguments=None):
    return {'id':'test-response','model':'deepseek-test','choices':[{'finish_reason':'tool_calls','message':{
        'role':'assistant','content':None,'tool_calls':[{'id':'tool-1','type':'function','function':{
            'name':'arrange_learning','arguments':json.dumps(arguments or decision(),ensure_ascii=False)}}]}}],
        'usage':{'prompt_tokens':120,'completion_tokens':50}}


class ModelDebugTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'AITEACHER_DB':str(Path(self.temp.name)/'classroom.sqlite3'),
            'AITEACHER_MODEL_DEBUG_DB':str(Path(self.temp.name)/'debug.sqlite3'),
            'AITEACHER_USAGE_DB':str(Path(self.temp.name)/'usage.sqlite3'),
            'AI_API_URL':'https://api.deepseek.com/chat/completions','AI_API_KEY':'private-model-key','AI_MODEL':'deepseek-test'})
        self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()

    def invoke(self,raw,state=None):
        with debug.scope(session_id='session-a',job_id='job-a'),patch.object(tutor,'urlopen',return_value=io.BytesIO(json.dumps(raw,ensure_ascii=False).encode())):
            return chat.decide(state or chat.new_state(),'我的目标是理解分数')

    def test_actual_request_pending_capture_and_verbatim_response(self):
        raw=response()
        def provider(request,timeout):
            pending=debug.recent('session-a')['calls'][0]
            self.assertEqual(pending['status'],'pending')
            self.assertEqual(pending['request'],json.loads(request.data))
            self.assertEqual(pending['request']['thinking'],{'type':'disabled'})
            self.assertEqual(pending['request']['tool_choice'],'required')
            self.assertIsNone(pending['response'])
            return io.BytesIO(json.dumps(raw,ensure_ascii=False).encode())
        with debug.scope(session_id='session-a',job_id='job-a'),patch.object(tutor,'urlopen',side_effect=provider):
            chat.decide(chat.new_state(),'想学分数')
        calls=debug.recent('session-a')['calls']
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['status'],'completed')
        self.assertEqual(calls[0]['response'],raw)
        self.assertEqual(calls[0]['job_id'],'job-a')
        self.assertEqual(debug.recent('session-b')['calls'],[])
        self.assertNotIn('private-model-key',json.dumps(calls))
        self.assertIsNone(debug._call.get())

    def test_invalid_tool_json_stays_visible_after_parse_failure(self):
        raw=response();raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']='{invalid original JSON'
        with self.assertRaises(ValueError):self.invoke(raw)
        call=debug.recent('session-a')['calls'][0]
        self.assertEqual(call['status'],'failed')
        self.assertEqual(call['error']['code'],'arguments_json')
        self.assertEqual(call['response'],raw)

    def test_invalid_schema_is_a_failed_call_with_raw_reply(self):
        with self.assertRaises(ValueError):self.invoke(response(decision('invented_action')))
        call=debug.recent('session-a')['calls'][0]
        self.assertEqual(call['error']['code'],'invalid_enum')
        self.assertIn('invented_action',json.dumps(call['response']))

    def test_network_failure_records_request_without_unsafe_exception(self):
        with debug.scope(session_id='session-a'),patch.object(tutor,'urlopen',side_effect=TimeoutError('secret transport details')):
            with self.assertRaises(RuntimeError):chat.decide(chat.new_state(),'开始')
        call=debug.recent('session-a')['calls'][0]
        self.assertEqual(call['status'],'failed');self.assertEqual(call['error']['code'],'timeout')
        self.assertIsNotNone(call['request']);self.assertIsNone(call['response'])
        self.assertNotIn('secret transport details',json.dumps(call))

    def test_planner_never_receives_pending_private_rubric(self):
        state=chat.new_state();state['pending_question']={'question':'问题','rubric':'private-answer-key','objective':'平均分'}
        self.invoke(response(),state)
        call=debug.recent('session-a')['calls'][0]
        context=json.loads(call['request']['messages'][1]['content'])
        self.assertNotIn('rubric',context['classroom']['pending_question'])
        self.assertEqual(state['pending_question']['rubric'],'private-answer-key')
        self.assertNotIn('private-answer-key',json.dumps(call))

    def test_secret_and_reasoning_fields_are_redacted_in_nested_payloads(self):
        raw=response();message=raw['choices'][0]['message']
        message['reasoning_content']='hidden-private-reasoning'
        message['content']='private-model-key'
        self.invoke(raw)
        text=json.dumps(debug.recent('session-a'),ensure_ascii=False)
        self.assertNotIn('hidden-private-reasoning',text)
        self.assertNotIn('private-model-key',text)
        self.assertIn('已隐藏',text)
        cleaned=debug.safe({'content':json.dumps({'token':'private-session-token','rubric':'private-rubric'})})
        self.assertNotIn('private-session-token',str(cleaned));self.assertNotIn('private-rubric',str(cleaned))

    def test_later_specialist_failure_does_not_erase_or_overwrite_trace(self):
        state=chat.new_state();chat.event(state,'chat_message',{'text':'直接开始'})
        raw=response(decision('teach'))
        with debug.scope(session_id='session-a'),patch.object(tutor,'urlopen',return_value=io.BytesIO(json.dumps(raw).encode())),patch.object(chat,'specialist',side_effect=RuntimeError('later failure')):
            with self.assertRaises(RuntimeError):chat.run(state)
        calls=debug.recent('session-a')['calls']
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['response'],raw)
        self.assertEqual(calls[0]['status'],'completed')

    def test_retention_and_finish_order_use_start_time(self):
        for i in range(32):debug.save(dict(id=f'id-{i}',session_id='session-a',at=f'2026-10-30T00:00:{i:02d}',status='pending'))
        debug.save(dict(id='id-0',session_id='session-a',at='2026-10-30T00:00:00',status='completed'))
        calls=debug.recent('session-a')['calls']
        self.assertEqual(len(calls),30);self.assertEqual(calls[0]['id'],'id-31')
        self.assertNotIn('id-0',[call['id'] for call in calls])

    def test_specialist_transport_is_not_captured_as_planner_reply(self):
        raw=response()
        with debug.scope(session_id='session-a'),patch.object(tutor,'urlopen',side_effect=[
                io.BytesIO(json.dumps(raw).encode()),io.BytesIO(b'{"choices":[{"message":{"content":"specialist reply"}}]}')]):
            chat.decide(chat.new_state(),'学习分数')
            tutor.complete('specialist prompt',{'specialist':'private context'})
        calls=debug.recent('session-a')['calls']
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['response'],raw)
        self.assertNotIn('specialist prompt',json.dumps(calls))

    def test_debug_storage_failure_does_not_break_teaching(self):
        with patch.object(debug,'connect',side_effect=OSError('private local path')),self.assertLogs('backend.model_debug',level='ERROR') as logs:
            self.assertEqual(self.invoke(response())['action'],'plan')
        self.assertNotIn('private local path',''.join(logs.output))


if __name__=='__main__':unittest.main()
