"""Voice allowlist and Doubao TTS transport. Credentials never leave the backend."""
import base64
import binascii
import json
import os
import socket
import time
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException

DOUBAO_URL = 'https://voice.cn-beijing.volces.com/api/v3/text-to-speech'
DOUBAO_V2_URL = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'
VOICES = {
    'edge-xiaoxiao': {'name': '晓晓', 'provider': 'edge', 'speaker': 'zh-CN-XiaoxiaoNeural'},
    'doubao-silang': {'name': '四郎', 'provider': 'doubao', 'speaker': 'multi_male_silang_v3_uranus_bigtts'},
    'doubao-xionger': {'name': '熊二', 'provider': 'doubao', 'speaker': 'multi_male_xionger_v3_uranus_bigtts'},
    'doubao-tangseng': {'name': '唐僧', 'provider': 'doubao', 'speaker': 'multi_male_tangseng_v3_uranus_bigtts'},
    'doubao-xuanyi': {'name': '悬疑解说', 'provider': 'doubao', 'speaker': 'multi_male_xuanyijieshuo_v3_uranus_bigtts'},
    'doubao-sunwukong': {'name': '孙悟空', 'provider': 'doubao', 'speaker': 'multi_male_sunwukong_v3_uranus_bigtts'},
    'doubao-tiancaitongzhuo': {'name': '天才同桌', 'provider': 'doubao', 'speaker': 'ICL_uranus_male_zh_tiancaitongzhuo_tob_v3'},
    'doubao-shaonianjiangjun': {'name': '少年将军', 'provider': 'doubao', 'speaker': 'ICL_uranus_male_zh_shaonianjiangjun_tob_v3'},
    'doubao-wumeiyujie': {'name': '妩媚御姐', 'provider': 'doubao', 'speaker': 'ICL_uranus_zh_female_wumeiyujie_tob', 'model': 'doubao-seed-tts-2.0'},
}


def default_voice():
    value = os.getenv('TTS_DEFAULT_VOICE', 'edge-xiaoxiao')
    return value if value in VOICES else 'edge-xiaoxiao'


def resolve_voice(voice_id=None):
    voice_id = voice_id or default_voice()
    if voice_id not in VOICES:
        raise HTTPException(422, '未找到这个朗读音色，请重新选择。')
    voice = {'id': voice_id, **VOICES[voice_id]}
    if voice['provider'] == 'doubao':
        if not os.getenv('DOUBAO_TTS_API_KEY', '').strip():
            raise HTTPException(503, '豆包语音尚未配置 API Key，请在后端配置后重启。')
        variable = 'DOUBAO_TTS_' + voice_id.removeprefix('doubao-').replace('-', '_').upper() + '_SPEAKER'
        voice['speaker'] = os.getenv(variable, voice['speaker'])
        voice.setdefault('model', 'doubao-seed-tts-3.0')
    return voice


def voice_catalog(edge_ready):
    return {
        'default_voice': default_voice(),
        'voices': [
            {'id': key, 'name': value['name'], 'provider': value['provider'],
             'model': value.get('model', 'doubao-seed-tts-3.0') if value['provider'] == 'doubao' else None,
             'available': edge_ready if value['provider'] == 'edge' else bool(os.getenv('DOUBAO_TTS_API_KEY', '').strip())}
            for key, value in VOICES.items()
        ],
    }


def provider_error(code, request_id, *, http_status=None):
    code = str(code)
    if not code.replace('_', '').isalnum() or len(code) > 80: code = 'invalid_response'
    if http_status == 401:
        reason = '豆包语音鉴权失败，请检查 API Key。'
    elif http_status == 403:
        reason = '豆包语音未获授权，请检查当前项目的服务开通、音色权限和额度。'
    elif http_status == 429 or code in {'45000001', '45000002'}:
        reason = '豆包语音请求过于频繁，请稍后重试。'
    else:
        reason = '豆包语音合成失败，请检查音色 ID、模型版本和当前项目的服务权限或额度。'
    return HTTPException(429 if http_status == 429 else 502,
                         f'{reason} 错误码：{code}；请求编号：{request_id}。')


def doubao_synthesize(text, voice, *, with_timestamps=False):
    request_id = str(uuid4())
    legacy = voice['model'] == 'doubao-seed-tts-2.0'
    body = {'text': text, 'model_id': voice['model'],
            'output_format': {'format': 'mp3', 'sample_rate': 24000}}
    if with_timestamps: body['enable_subtitle'] = True
    url = DOUBAO_URL + '/' + quote(voice['speaker'], safe='') + '/streaming'
    headers = {
        'Content-Type': 'application/json', 'X-Api-Key': os.environ['DOUBAO_TTS_API_KEY'].strip(),
        'X-Request-Id': request_id,
    }
    if legacy:
        url = DOUBAO_V2_URL
        body = {'user': {'uid': 'aiteacher-local'}, 'req_params': {
            'text': text, 'speaker': voice['speaker'],
            'audio_params': {'format': 'mp3', 'sample_rate': 24000},
        }}
        headers.update({'X-Api-Resource-Id': 'seed-tts-2.0', 'X-Api-Request-Id': request_id})
        if with_timestamps: body['req_params']['audio_params']['enable_subtitle'] = True
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers)
    audio = bytearray()
    words = []
    finished = False
    deadline = time.monotonic() + 45
    try:
        with urlopen(request, timeout=45) as response:
            for line in response:
                if time.monotonic() > deadline:
                    raise TimeoutError()
                if not line.strip():
                    continue
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError('Invalid provider frame')
                alignment = item.get('sentence') if legacy else item if item.get('event') == 'alignment' else None
                if with_timestamps and isinstance(alignment, dict):
                    for word in alignment.get('words', []):
                        if not isinstance(word, dict): continue
                        start, end = word.get('startTime'), word.get('endTime')
                        if (isinstance(start, (int, float)) and isinstance(end, (int, float))
                                and math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                            words.append({'text': str(word.get('word', '')), 'start': start, 'end': end})
                if legacy:
                    code = item.get('code')
                    if code not in (0, 20000000):
                        raise provider_error(code, request_id)
                    encoded = item.get('data')
                    finished = code == 20000000
                else:
                    event = item.get('event')
                    if event == 'error':
                        error = item.get('error') or {}
                        raise provider_error(error.get('code'), request_id)
                    encoded = item.get('audio') if event == 'audio' else None
                    if event == 'final':
                        finished = item.get('is_final') is True and item.get('reason') == 'TTS_STREAM_FINAL_REASON_CLOSED'
                        if not finished: raise ValueError('Interrupted provider stream')
                if encoded:
                    audio.extend(base64.b64decode(encoded, validate=True))
                if len(audio) > 8 * 1024 * 1024:
                    raise ValueError('Audio response too large')
                if finished: break
        if not finished or len(audio) < 100:
            raise HTTPException(502, f'豆包语音没有返回完整音频，请重试。请求编号：{request_id}。')
        if with_timestamps:
            return {'audio': bytes(audio), 'words': sorted(words, key=lambda word: word['start'])}
        return bytes(audio)
    except HTTPError as exc:
        code = exc.code
        try:
            payload = json.loads(exc.read(8192))
            if isinstance(payload, dict):
                error = payload.get('error') or {}
                code = error.get('code', payload.get('code', code))
        except (ValueError, OSError):
            pass
        finally:
            exc.close()
        raise provider_error(code, request_id, http_status=exc.code) from None
    except (TimeoutError, socket.timeout):
        raise HTTPException(504, f'豆包语音生成超时，可以重听。请求编号：{request_id}。') from None
    except (URLError, OSError):
        raise HTTPException(502, f'暂时无法连接豆包语音，请检查网络后重试。请求编号：{request_id}。') from None
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error):
        raise HTTPException(502, f'豆包语音返回的数据格式异常，请重试。请求编号：{request_id}。') from None
