"""Optional presentation adapter: assets and speech, never teaching decisions."""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import re
import subprocess
import threading

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .tutor import ROOT
from .math_speech import spoken_math_text
from .speech_providers import default_voice, resolve_voice, voice_catalog, doubao_synthesize

HOME = Path(os.environ.get('DIGITAL_HUMAN_HOME', str(ROOT.parent / 'Open-LLM-VTuber')))
PYTHON = Path(os.environ.get('DIGITAL_HUMAN_PYTHON', str(HOME / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))))
MODEL = HOME / 'live2d-models' / 'mao_pro' / 'runtime'
CORE = HOME / 'frontend' / 'libs' / 'live2dcubismcore.min.js'
SPEAKERS = {'planner', 'lecturer', 'assessment'}
_slots = threading.BoundedSemaphore(2)
_cache_lock = threading.Lock()
_cache = OrderedDict()
_cache_bytes = 0
_cache_limit = 16 * 1024 * 1024
_timed_cache = OrderedDict()
_timed_bytes = 0


def character_catalog():
    return [
        {'id': 'mao', 'name': 'Mao', 'mode': 'live2d', 'description': '魔法少女 · 动态形象',
         'available': CORE.is_file() and (MODEL / 'mao_pro.model3.json').is_file(),
         'model_url': '/digital-assets/characters/mao/mao_pro.model3.json',
         'credit': 'Sample model © Live2D Inc.', 'source_url': 'https://www.live2d.com/en/learn/sample/niziiro-mao/'},
        {'id': 'miku', 'name': '初音未来', 'mode': 'live2d', 'description': '初音未来 · 动态形象',
         'available': CORE.is_file() and (HOME / 'live2d-models/miku/runtime/miku.model3.json').is_file(),
         'model_url': '/digital-assets/characters/miku/miku.model3.json',
         'mouth_parameter': 'PARAM_MOUTH_OPEN_Y',
         'credit': '© Crypton Future Media, INC. www.piapro.net · Live2D sample',
         'source_url': 'https://www.live2d.com/en/learn/sample/hatsune-miku/'},
        {'id': 'hiyori_movie', 'name': 'Hiyori · 趴桌', 'mode': 'portrait', 'description': '趴桌造型 · 静态形象配音',
         'available': (HOME / 'live2d-models/hiyori_movie_preview/portrait.jpg').is_file(),
         'portrait_url': '/digital-assets/portraits/hiyori-movie.jpg',
         'note': '当前为你提供的静态图片，可听语音讲解；动画工程需要另行导出可运行模型，尚不支持口型。',
         'credit': 'Hiyori Momose © Live2D Inc.',
         'source_url': 'https://www.live2d.com/en/learn/sample/momose-hiyori-video/'},
    ]


class SpeechRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=100)
    chunk: int = Field(default=0, ge=0, le=300)
    voice_id: str | None = Field(default=None, max_length=80)


def speech_chunks(text):
    # The board keeps TeX; only the optional audio adapter receives its reading.
    text = spoken_math_text(text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'(?<!\\)\\(?:r\\n|n)(?![a-zA-Z])', '\n', text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-*>]\s+)', '', text)
    text = text.replace('**', '').replace('`', '').strip()
    chunks, current = [], ''
    for sentence in re.split(r'(?<=[。！？!?；;\n])', text):
        while sentence:
            count = min(len(sentence), 240 - len(current))
            current += sentence[:count]
            sentence = sentence[count:]
            if len(current) >= 220 or sentence:
                chunks.append(current.strip()); current = ''
    if current.strip(): chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def synthesize(text, voice_id=None):
    global _cache_bytes
    voice = resolve_voice(voice_id)
    key = hashlib.sha256((repr(sorted(voice.items())) + '\0' + text).encode()).digest()
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if voice['provider'] == 'edge' and not PYTHON.is_file():
        raise HTTPException(503, '数字人语音环境未安装，板书仍可正常学习。')
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, '语音正在生成，请稍后重试。')
    try:
        if voice['provider'] == 'doubao':
            audio = doubao_synthesize(text, voice)
        else:
            result = subprocess.run([str(PYTHON), str(Path(__file__).with_name('digital_human_speech.py'))],
                input=text.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode or len(result.stdout) < 100:
                raise HTTPException(502, '中文配音暂时不可用，可以继续看板书，或点击重听再试。')
            audio = result.stdout
        with _cache_lock:
            if key not in _cache:
                _cache[key] = audio; _cache_bytes += len(audio)
            while _cache_bytes > _cache_limit:
                _, removed = _cache.popitem(last=False); _cache_bytes -= len(removed)
        return audio
    except (subprocess.TimeoutExpired, OSError):
        raise HTTPException(504, '语音生成超时或启动失败，板书已保留，可以稍后重听。') from None
    finally:
        _slots.release()


def synthesize_timed(text, voice_id=None):
    """Keep audio and its timestamps in the same cache entry; never mix voices."""
    global _timed_bytes
    voice = resolve_voice(voice_id)
    if voice['provider'] != 'doubao':
        return {'audio': synthesize(text, voice_id), 'words': []}
    key = hashlib.sha256((repr(sorted(voice.items())) + '\0' + text).encode()).digest()
    with _cache_lock:
        if key in _timed_cache:
            _timed_cache.move_to_end(key)
            return _timed_cache[key]
    if not _slots.acquire(blocking=False): raise HTTPException(429, '语音正在生成，请稍后重试。')
    try:
        packet = doubao_synthesize(text, voice, with_timestamps=True)
        with _cache_lock:
            if key not in _timed_cache:
                _timed_cache[key] = packet; _timed_bytes += len(packet['audio'])
            while _timed_bytes > _cache_limit:
                _, removed = _timed_cache.popitem(last=False); _timed_bytes -= len(removed['audio'])
        return packet
    finally:
        _slots.release()


def register_routes(app, connect, lock, read_session, token_value):
    @app.get('/api/digital-human/characters')
    def characters():
        return {'characters': character_catalog(), 'voice_note': '老师形象与朗读音色可以分别选择。'}

    @app.get('/api/digital-human/voices')
    def voices():
        return voice_catalog(PYTHON.is_file())

    @app.get('/api/digital-human/status')
    def status():
        return {'avatar_ready': CORE.is_file() and (MODEL / 'mao_pro.model3.json').is_file(),
                'speech_ready': any(v['available'] for v in voice_catalog(PYTHON.is_file())['voices']),
                'default_voice': default_voice(), 'character': 'Mao',
                'model_url': '/digital-assets/models/mao_pro.model3.json'}

    @app.get('/digital-assets/core.js')
    def core():
        if not CORE.is_file(): raise HTTPException(503, '请先安装独立数字人演示包。')
        return FileResponse(CORE, media_type='application/javascript')

    @app.get('/digital-assets/models/{asset_path:path}')
    def model_asset(asset_path: str):
        target = (MODEL / asset_path).resolve()
        if not target.is_relative_to(MODEL.resolve()) or target.suffix.lower() not in {'.json', '.moc3', '.png', '.jpg', '.wav', '.ogg'} or not target.is_file():
            raise HTTPException(404, '角色素材不存在。')
        return FileResponse(target)

    @app.get('/digital-assets/characters/{character_id}/{asset_path:path}')
    def character_asset(character_id: str, asset_path: str):
        roots = {'mao': MODEL, 'miku': HOME / 'live2d-models/miku/runtime'}
        root = roots.get(character_id)
        if root is None: raise HTTPException(404, '角色不存在。')
        target = (root / asset_path).resolve()
        if not target.is_relative_to(root.resolve()) or target.suffix.lower() not in {'.json', '.moc3', '.png', '.jpg', '.wav', '.ogg'} or not target.is_file():
            raise HTTPException(404, '角色素材不存在。')
        return FileResponse(target)

    @app.get('/digital-assets/portraits/hiyori-movie.jpg')
    def hiyori_portrait():
        target = HOME / 'live2d-models/hiyori_movie_preview/portrait.jpg'
        if not target.is_file(): raise HTTPException(404, '趴桌造型图片尚未安装。')
        return FileResponse(target, media_type='image/jpeg')

    @app.post('/api/sessions/{sid}/digital-speech')
    def speech(sid: str, body: SpeechRequest, token=Depends(token_value)):
        with lock, connect() as db:
            state = read_session(db, sid, token)
            message = next((m for m in state.get('messages', []) if m.get('id') == body.message_id
                            and m.get('agent') in SPEAKERS and m.get('status') == 'ai'
                            and m.get('kind') != 'handoff'), None)
            if not message: raise HTTPException(404, '没有找到可播报的老师消息。')
            chunks = speech_chunks(message['text'])
        if body.chunk >= len(chunks): raise HTTPException(422, '该段语音不存在。')
        # Synthesis happens outside the teaching/database lock. No session writes.
        return Response(synthesize(chunks[body.chunk], body.voice_id) if body.voice_id else synthesize(chunks[body.chunk]), media_type='audio/mpeg',
                        headers={'X-Speech-Chunks': str(len(chunks)), 'Cache-Control': 'no-store'})
