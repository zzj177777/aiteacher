import base64
import io
import json
import os
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from fastapi import HTTPException
from backend import digital_human as dh, speech_providers as sp


def frames(*items):
    return io.BytesIO(b'\n'.join(json.dumps(item).encode() for item in items))


class SpeechProviderTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'DOUBAO_TTS_API_KEY': 'fixture-private-key', 'TTS_DEFAULT_VOICE': 'doubao-silang'})
        env.start(); self.addCleanup(env.stop)
        self.voice = sp.resolve_voice('doubao-silang')
        self.audio = b'fixture-mp3' * 50

    def test_transport_uses_3_0_voice_path_and_combines_audio(self):
        response = frames({'event': 'ready'},
                          {'event': 'audio', 'audio': base64.b64encode(self.audio[:100]).decode()},
                          {'event': 'audio', 'audio': base64.b64encode(self.audio[100:]).decode()},
                          {'event': 'final', 'is_final': True, 'reason': 'TTS_STREAM_FINAL_REASON_CLOSED'})
        with patch.object(sp, 'urlopen', return_value=response) as call:
            result = sp.doubao_synthesize('你好，X。', self.voice)
        self.assertEqual(result, self.audio)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, sp.DOUBAO_URL + '/multi_male_silang_v3_uranus_bigtts/streaming')
        self.assertEqual(request.get_header('X-api-key'), 'fixture-private-key')
        body = json.loads(request.data)
        self.assertEqual(body['model_id'], 'doubao-seed-tts-3.0')
        self.assertEqual(body['text'], '你好，X。')

    def test_partial_or_malformed_audio_is_not_treated_as_success(self):
        partial = {'event': 'audio', 'audio': base64.b64encode(self.audio).decode()}
        cases = [frames(partial), frames(partial, {'event': 'error', 'error': {'code': 'quota_exceeded'}}),
                 frames({'event': 'audio', 'audio': 'invalid%%%'}), frames(['invalid']),
                 frames(partial, {'event': 'final', 'is_final': True, 'reason': 'interrupted'})]
        for response in cases:
            with self.subTest(), patch.object(sp, 'urlopen', return_value=response), self.assertRaises(HTTPException) as error:
                sp.doubao_synthesize('测试', self.voice)
            self.assertEqual(error.exception.status_code, 502)

    def test_2_0_voice_uses_its_resource_and_completion_protocol(self):
        voice = sp.resolve_voice('doubao-wumeiyujie')
        self.assertEqual(voice['model'], 'doubao-seed-tts-2.0')
        response = frames({'code': 0, 'data': base64.b64encode(self.audio).decode()},
                          {'code': 20000000, 'data': None})
        with patch.object(sp, 'urlopen', return_value=response) as call:
            self.assertEqual(sp.doubao_synthesize('测试', voice), self.audio)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, sp.DOUBAO_V2_URL)
        self.assertEqual(request.get_header('X-api-resource-id'), 'seed-tts-2.0')
        self.assertEqual(json.loads(request.data)['req_params']['speaker'], 'ICL_uranus_zh_female_wumeiyujie_tob')
        for response in [frames({'code': 0, 'data': base64.b64encode(self.audio).decode()}),
                         frames({'code': 55000000, 'message': 'resource mismatch'})]:
            with patch.object(sp, 'urlopen', return_value=response), self.assertRaises(HTTPException):
                sp.doubao_synthesize('测试', voice)

    def test_voice_overrides_are_scoped_to_each_selected_voice(self):
        with patch.dict(os.environ, {'DOUBAO_TTS_XIONGER_SPEAKER': 'fixture-xionger'}):
            self.assertEqual(sp.resolve_voice('doubao-xionger')['speaker'], 'fixture-xionger')
            self.assertEqual(sp.resolve_voice('doubao-tangseng')['speaker'], 'multi_male_tangseng_v3_uranus_bigtts')
            self.assertEqual(sp.resolve_voice('doubao-wumeiyujie')['speaker'], 'ICL_uranus_zh_female_wumeiyujie_tob')

    def test_provider_errors_have_diagnostics_without_echoing_secret(self):
        for status in (401, 403, 429):
            raw = json.dumps({'event': 'error', 'error': {'code': 'forbidden', 'message': 'fixture-private-key'}}).encode()
            failure = HTTPError(sp.DOUBAO_URL, status, 'fixture-private-key', {}, io.BytesIO(raw))
            with patch.object(sp, 'urlopen', side_effect=failure), self.assertRaises(HTTPException) as error:
                sp.doubao_synthesize('测试', self.voice)
            self.assertNotIn('fixture-private-key', str(error.exception.detail))
            self.assertIn('请求编号', error.exception.detail)
            self.assertEqual(error.exception.status_code, 429 if status == 429 else 502)

    def test_missing_key_and_unknown_voice_do_not_call_provider(self):
        with patch.dict(os.environ, {'DOUBAO_TTS_API_KEY': ''}), self.assertRaises(HTTPException) as error:
            sp.resolve_voice('doubao-xionger')
        self.assertEqual(error.exception.status_code, 503)
        with self.assertRaises(HTTPException) as error: sp.resolve_voice('arbitrary-voice')
        self.assertEqual(error.exception.status_code, 422)

    def test_catalog_contains_no_credentials(self):
        catalog = sp.voice_catalog(False)
        self.assertEqual(catalog['default_voice'], 'doubao-silang')
        self.assertNotIn('fixture-private-key', json.dumps(catalog))
        self.assertFalse(catalog['voices'][0]['available'])
        self.assertTrue(catalog['voices'][1]['available'])

    def test_cache_separates_voices_and_does_not_require_avatar_python(self):
        with patch.object(dh, 'doubao_synthesize', side_effect=[b'silang', b'xionger']) as synth:
            self.assertEqual(dh.synthesize('cache-separation-fixture', 'doubao-silang'), b'silang')
            self.assertEqual(dh.synthesize('cache-separation-fixture', 'doubao-xionger'), b'xionger')
            self.assertEqual(dh.synthesize('cache-separation-fixture', 'doubao-silang'), b'silang')
        self.assertEqual(synth.call_count, 2)

    def test_connection_failure_is_actionable(self):
        with patch.object(sp, 'urlopen', side_effect=URLError('fixture-private-key')), self.assertRaises(HTTPException) as error:
            sp.doubao_synthesize('测试', self.voice)
        self.assertNotIn('fixture-private-key', error.exception.detail)
        self.assertIn('网络', error.exception.detail)

    def test_timestamp_packets_for_both_protocols_keep_timing_with_audio(self):
        for voice_id in ('doubao-silang','doubao-wumeiyujie'):
            legacy=voice_id=='doubao-wumeiyujie'
            words=[{'word':'先','startTime':.25,'endTime':.65},{'word':'坏','startTime':-1,'endTime':0}]
            response=frames(*([{'code':0,'data':base64.b64encode(self.audio).decode()}, {'code':0,'sentence':{'words':words}}, {'code':20000000}] if legacy else [
                {'event':'audio','audio':base64.b64encode(self.audio).decode()}, {'event':'alignment','words':words}, {'event':'final','is_final':True,'reason':'TTS_STREAM_FINAL_REASON_CLOSED'}]))
            with patch.object(sp,'urlopen',return_value=response) as call:
                packet=sp.doubao_synthesize('先看。',sp.resolve_voice(voice_id),with_timestamps=True)
            self.assertEqual(packet['audio'],self.audio)
            self.assertEqual(packet['words'],[{'text':'先','start':.25,'end':.65}])
            request=json.loads(call.call_args.args[0].data)
            self.assertTrue(request['req_params']['audio_params']['enable_subtitle'] if legacy else request['enable_subtitle'])


if __name__ == '__main__': unittest.main()
