import copy
import json
import os
import socket
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException
import uvicorn
from backend import digital_human as dh


class DigitalHumanTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'TTS_DEFAULT_VOICE': 'edge-xiaoxiao'})
        env.start(); self.addCleanup(env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'models'
        self.model.mkdir()
        (self.model / 'mao_pro.model3.json').write_text('{}')
        self.core = self.root / 'core.js'
        self.core.write_text('/* test core */')
        self.python = self.root / 'python.exe'
        self.python.touch()
        self.patches = [patch.object(dh, 'HOME', self.root), patch.object(dh, 'MODEL', self.model), patch.object(dh, 'CORE', self.core), patch.object(dh, 'PYTHON', self.python)]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        self.state = {'revision': 8, 'plan': {'current': 'node-1'}, 'messages': [
            {'id': 'lecture', 'agent': 'lecturer', 'status': 'ai', 'text': '先看一个例子。**这样就明白了。**'},
            {'id': 'student', 'agent': 'student', 'text': '不要播报我的内容'},
            {'id': 'pending', 'agent': 'lecturer', 'status': 'pending', 'text': '尚未提交'},
            {'id': 'handoff', 'agent': 'planner', 'status': 'ai', 'kind': 'handoff', 'text': '内部交接'},
            {'id': 'failed', 'agent': 'lecturer', 'status': 'failed', 'text': '失败'},
        ], 'pending_question': {'rubric': 'private grading criteria'}}
        self.before = copy.deepcopy(self.state)
        self.lock = threading.Lock()

        @contextmanager
        def connect(): yield object()

        def token_value(authorization: str = Header(default='')):
            if not authorization.startswith('Bearer '): raise HTTPException(401, 'missing')
            return authorization[7:]

        def read_session(db, sid, token):
            if sid != 'session-1' or token != 'secret': raise HTTPException(404, 'not found')
            return self.state

        app = FastAPI()
        dh.register_routes(app, connect, self.lock, read_session, token_value)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        for _ in range(100):
            if self.server.started: break
            time.sleep(.01)
        self.assertTrue(self.server.started)
        self.headers = {'Authorization': 'Bearer secret'}

    def shutdown(self):
        self.server.should_exit = True
        self.thread.join(5)

    def call(self, path, body=None, headers=None):
        req = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json', **(headers or {})})
        try: response = urlopen(req, timeout=5)
        except HTTPError as e: response = e
        with response:
            result = type('Reply', (), {})()
            result.status_code = response.status; result.headers = response.headers; result.content = response.read()
            result.json = lambda: json.loads(result.content)
            return result

    def speech(self, **body):
        return self.call('/api/sessions/session-1/digital-speech', headers=self.headers,
                         body={'message_id': 'lecture', **body})

    def test_only_authorized_committed_teacher_messages_can_be_spoken(self):
        with patch.object(dh, 'synthesize', return_value=b'audio') as synth:
            url = '/api/sessions/session-1/digital-speech'
            self.assertEqual(self.call(url, body={'message_id': 'lecture'}).status_code, 401)
            self.assertEqual(self.call(url, headers={'Authorization': 'Bearer wrong'}, body={'message_id': 'lecture'}).status_code, 404)
            for mid in ['student', 'pending', 'handoff', 'failed', 'missing']:
                self.assertEqual(self.speech(message_id=mid).status_code, 404)
            synth.assert_not_called()

    def test_speech_runs_outside_lesson_lock_and_does_not_change_progress(self):
        def synth(text):
            self.assertTrue(self.lock.acquire(blocking=False)); self.lock.release()
            self.assertNotIn('private', text)
            return b'audio'
        with patch.object(dh, 'synthesize', side_effect=synth):
            response = self.speech()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'audio')
        self.assertEqual(response.headers['x-speech-chunks'], '1')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.state, self.before)

    def test_audio_failure_never_rolls_back_or_advances_teaching(self):
        with patch.object(dh, 'synthesize', side_effect=HTTPException(502, 'voice unavailable')):
            self.assertEqual(self.speech().status_code, 502)
        self.assertEqual(self.state, self.before)
        self.assertEqual(self.speech(chunk=301).status_code, 422)
        self.assertEqual(self.speech(chunk=2).status_code, 422)

    def test_selected_voice_is_forwarded_without_session_changes(self):
        with patch.object(dh, 'synthesize', return_value=b'audio') as synth:
            response = self.speech(voice_id='doubao-xionger')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(synth.call_args.args[1], 'doubao-xionger')
        self.assertEqual(self.state, self.before)

    def test_assets_do_not_expose_arbitrary_files(self):
        (self.root / '.env').write_text('secret')
        self.assertEqual(self.call('/digital-assets/core.js').status_code, 200)
        self.assertEqual(self.call('/digital-assets/models/mao_pro.model3.json').status_code, 200)
        for path in ['../.env', '..%2f.env', '%2e%2e%2fcore.js', 'missing.json']:
            self.assertNotEqual(self.call('/digital-assets/models/' + path).status_code, 200)
        status = self.call('/api/digital-human/status').json()
        self.assertTrue(status['avatar_ready'])
        self.assertNotIn(str(self.root), str(status))

    def test_character_catalog_marks_hiyori_as_static_and_keeps_miku_lip_ids(self):
        miku = self.root / 'live2d-models/miku/runtime'
        miku.mkdir(parents=True); (miku / 'miku.model3.json').write_text('{}')
        portrait = self.root / 'live2d-models/hiyori_movie_preview/portrait.jpg'
        portrait.parent.mkdir(parents=True); portrait.write_bytes(b'jpeg fixture')
        result = self.call('/api/digital-human/characters')
        items = {c['id']: c for c in result.json()['characters']}
        self.assertEqual(set(items), {'mao', 'miku', 'hiyori_movie'})
        self.assertTrue(all(c['available'] for c in items.values()))
        self.assertEqual(items['miku']['mode'], 'live2d')
        self.assertEqual(items['miku']['mouth_parameter'], 'PARAM_MOUTH_OPEN_Y')
        self.assertEqual(items['hiyori_movie']['mode'], 'portrait')
        self.assertNotIn('model_url', items['hiyori_movie'])
        self.assertIn('尚不支持口型', items['hiyori_movie']['note'])
        self.assertEqual(self.call(items['hiyori_movie']['portrait_url']).content, b'jpeg fixture')
        self.assertNotIn(str(self.root), str(result.json()))
        self.assertEqual(self.state, self.before)

    def test_character_asset_roots_are_isolated(self):
        self.assertEqual(self.call('/digital-assets/characters/mao/mao_pro.model3.json').status_code, 200)
        for path in ['unknown/mao_pro.model3.json', 'mao/..%2f..%2f.env', 'miku/..%2f..%2f..%2fcore.js', 'mao/ReadMe.txt']:
            self.assertEqual(self.call('/digital-assets/characters/' + path).status_code, 404)

    def test_speech_chunks_preserve_prose_and_keep_tex_on_board(self):
        source = '看公式 $x^2+1$。\\n**先试一试。**' + '这是一段讲解。' * 100
        chunks = dh.speech_chunks(source)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(c) <= 240 for c in chunks))
        self.assertNotIn('$', ''.join(chunks))
        self.assertNotIn('**', ''.join(chunks))
        self.assertIn('先试一试', ''.join(chunks))
        self.assertIn('X 的平方加1', ''.join(chunks))

    def test_synthesis_timeout_and_missing_environment_are_recoverable(self):
        with patch.object(dh, 'PYTHON', self.root / 'missing.exe'):
            with self.assertRaises(HTTPException) as err: dh.synthesize('missing environment')
            self.assertEqual(err.exception.status_code, 503)
        with patch.object(dh.subprocess, 'run', side_effect=subprocess.TimeoutExpired('python', 40)):
            with self.assertRaises(HTTPException) as err: dh.synthesize('timeout fixture')
            self.assertEqual(err.exception.status_code, 504)


if __name__ == '__main__': unittest.main()
