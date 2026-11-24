import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from backend.tutor import remote_answer


class TutorTests(unittest.TestCase):
    def state(self):
        return {'phase': 'guided_practice', 'matrix': [['1','0','0'],['0','2','0'],['0','0','3']], 'factor':'1', 'messages':[], 'token':'private-session-token'}

    def test_deepseek_non_thinking_request_and_secret_isolation(self):
        fake = io.BytesIO(json.dumps({'choices':[{'message':{'content':'倍加不改变行列式。'}}]}).encode())
        with patch.dict(os.environ, {'AI_API_URL':'https://api.deepseek.com/chat/completions','AI_API_KEY':'test-only-key','AI_MODEL':'deepseek-flash'}), patch('backend.tutor.urlopen',return_value=fake) as call:
            self.assertEqual(remote_answer('为什么？',self.state()),'倍加不改变行列式。')
            request = call.call_args.args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload['thinking'],{'type':'disabled'})
            self.assertFalse(payload['stream'])
            self.assertNotIn('test-only-key',request.data.decode())
            self.assertNotIn('private-session-token',request.data.decode())
            self.assertEqual(request.get_header('Authorization'),'Bearer test-only-key')

    def test_generic_provider_keeps_compatible_payload(self):
        fake=io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
        with patch.dict(os.environ, {'AI_API_URL':'https://example.test/chat/completions','AI_API_KEY':'test-only','AI_MODEL':'model'}), patch('backend.tutor.urlopen',return_value=fake) as call:
            remote_answer('question',self.state())
            self.assertNotIn('thinking',json.loads(call.call_args.args[0].data))

    def test_provider_error_is_sanitized(self):
        for code, expected in [(401,'密钥无效'),(402,'余额不足'),(429,'频率受限')]:
            with patch.dict(os.environ, {'AI_API_URL':'https://api.deepseek.com/chat/completions','AI_API_KEY':'test-only','AI_MODEL':'deepseek-flash'}), patch('backend.tutor.urlopen',side_effect=HTTPError('https://api.deepseek.com',code,'secret-provider-details',{},None)):
                with self.assertRaisesRegex(RuntimeError, expected) as ctx:
                    remote_answer('question',self.state())
                self.assertNotIn('secret-provider-details',str(ctx.exception))

    def test_empty_model_content_not_success(self):
        fake=io.BytesIO(b'{"choices":[{"message":{"content":""}}]}')
        with patch.dict(os.environ, {'AI_API_URL':'https://api.deepseek.com/chat/completions','AI_API_KEY':'test-only','AI_MODEL':'deepseek-flash'}), patch('backend.tutor.urlopen',return_value=fake):
            with self.assertRaises(ValueError):
                remote_answer('question',self.state())


class DiagnosticsTests(unittest.TestCase):
    def invoke(self, response):
        from backend.tutor import call_tool
        with patch.dict(os.environ, {'AI_MODEL':'test','AI_API_URL':'https://example.test','AI_API_KEY':'test'}), patch('backend.tutor.request_completion',return_value=response):
            return call_tool('synthetic',{},[])

    def test_truncated_response_has_explicit_code(self):
        from backend.errors import TeachingError
        with self.assertRaises(TeachingError) as ctx:
            self.invoke({'choices':[{'finish_reason':'length','message':{'tool_calls':[]}}]})
        self.assertEqual(ctx.exception.code,'output_truncated')

    def test_invalid_tool_json_does_not_expose_content(self):
        from backend.errors import TeachingError
        with self.assertRaises(TeachingError) as ctx:
            self.invoke({'choices':[{'message':{'tool_calls':[{'function':{'name':'test','arguments':'private invalid body'}}]}}]})
        self.assertEqual(ctx.exception.code,'arguments_json')
        self.assertNotIn('private',str(ctx.exception))

    def test_missing_response_and_missing_call_are_distinguished(self):
        from backend.errors import TeachingError
        for response,code in [({},'response_shape'),({'choices':[{'message':{}}]},'tool_count')]:
            with self.assertRaises(TeachingError) as ctx:self.invoke(response)
            self.assertEqual(ctx.exception.code,code)

    def test_timeout_and_provider_json_are_distinguished(self):
        from backend.tutor import request_completion
        from backend.errors import TeachingError
        for failure,code in [(TimeoutError('private'),'timeout'),(json.JSONDecodeError('private','private',0),'response_json')]:
            with patch.dict(os.environ, {'AI_API_URL':'https://example.test','AI_API_KEY':'secret','AI_MODEL':'test'}),patch('backend.tutor.urlopen',side_effect=failure):
                with self.assertRaises(TeachingError) as ctx:request_completion({})
                self.assertEqual(ctx.exception.code,code)
                self.assertNotIn('private',str(ctx.exception))
