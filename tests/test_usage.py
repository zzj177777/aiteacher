import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import tutor,usage

class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'AITEACHER_USAGE_DB':str(Path(self.temp.name)/'usage.sqlite3'),'AI_API_URL':'https://example.test/chat/completions','AI_API_KEY':'private-secret','AI_MODEL':'test-model','AI_PRICE_MODEL':'test-model','AI_INPUT_PRICE_PER_MILLION':'2','AI_OUTPUT_PRICE_PER_MILLION':'8','AI_CACHE_HIT_PRICE_PER_MILLION':'0.5','AI_PRICE_CURRENCY':'CNY'})
        self.env.start()
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def invoke(self,response,sid='session-a'):
        with usage.scope(session_id=sid,job_id='job-1',agent='lecturer'),patch('backend.tutor.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            return tutor.complete('private-prompt',{'answer':'private-answer'})
    def test_usage_prices_cache_and_isolates_sessions(self):
        self.invoke({'choices':[{'message':{'content':'private-result'}}],'usage':{'prompt_tokens':1000,'completion_tokens':200,'prompt_cache_hit_tokens':400}})
        a=usage.summary('session-a');self.assertEqual(a['call_count'],1)
        self.assertAlmostEqual(a['estimated_costs']['CNY'],.003)
        self.assertEqual(a['recent_calls'][0]['agent'],'lecturer')
        self.assertEqual(usage.summary('session-b')['call_count'],0)
        text=json.dumps(a)
        for secret in ['private-secret','private-prompt','private-answer','private-result']:self.assertNotIn(secret,text)
    def test_failed_parse_still_keeps_provider_usage(self):
        with self.assertRaises(ValueError):self.invoke({'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':5}})
        a=usage.summary('session-a');self.assertEqual(a['failed_calls'],1)
        self.assertEqual(a['prompt_tokens'],20)
        self.assertEqual(a['recent_calls'][0]['error_code'],'response_shape')
    def test_missing_usage_and_wrong_model_price_are_unknown(self):
        self.invoke({'choices':[{'message':{'content':'ok'}}]})
        a=usage.summary('session-a');self.assertEqual(a['unpriced_calls'],1)
        self.assertEqual(a['usage_unknown_calls'],1)
        self.assertEqual(a['estimated_costs'],{})
        with patch.dict(os.environ,{'AI_PRICE_MODEL':'another-model'}):
            self.invoke({'choices':[{'message':{'content':'ok'}}],'usage':{'prompt_tokens':10,'completion_tokens':2}})
        self.assertEqual(usage.summary('session-a')['unpriced_calls'],2)
    def test_network_failure_is_recorded_and_context_resets(self):
        with usage.scope(session_id='session-a',agent='planner'),patch('backend.tutor.urlopen',side_effect=TimeoutError('private')):
            with self.assertRaises(RuntimeError):tutor.complete('x',{})
        a=usage.summary('session-a');self.assertEqual(a['failed_calls'],1)
        self.assertEqual(a['unpriced_calls'],1)
        self.assertEqual(usage._scope.get(),{})

    def test_course_planning_usage_is_separate_from_other_courses_and_sessions(self):
        response={'choices':[{'message':{'content':'ok'}}],'usage':{'prompt_tokens':10,'completion_tokens':5}}
        with usage.scope(course_id='course-a',agent='course_planner'),patch('backend.tutor.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            tutor.complete('course planning',{})
        self.invoke(response,sid='session-b')
        self.assertEqual(usage.summary(course_id='course-a')['call_count'],1)
        self.assertEqual(usage.summary(course_id='course-b')['call_count'],0)
        self.assertEqual(usage.summary('session-b')['call_count'],1)
        self.assertEqual(usage.summary(course_id='course-a')['recent_calls'][0]['agent'],'course_planner')
