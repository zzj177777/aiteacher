"""Invoked only by the optional adapter, using the isolated VTuber Python."""
import asyncio
import sys
import edge_tts


async def main():
    text = sys.stdin.buffer.read(16384).decode('utf-8')
    if not text.strip() or len(text) > 240:
        raise ValueError('Invalid speech chunk')
    audio = bytearray()
    async for item in edge_tts.Communicate(text, 'zh-CN-XiaoxiaoNeural').stream():
        if item['type'] == 'audio': audio.extend(item['data'])
    sys.stdout.buffer.write(audio)


if __name__ == '__main__':
    asyncio.run(main())
