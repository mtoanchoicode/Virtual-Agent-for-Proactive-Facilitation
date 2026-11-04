"""Speech synthesis and a real-time virtual microphone.

The backend expects what the browser sends: 16 kHz mono Int16 PCM in 4096-sample chunks every
~256 ms, continuously (silence included). Its VAD, STT chunking and interruption logic only work
if audio keeps arriving, so the mic streams silence whenever the agent is not talking.
"""
import asyncio
import time
from typing import Awaitable, Callable, Optional, Tuple

import edge_tts
import miniaudio

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 4096
CHUNK_BYTES = CHUNK_SAMPLES * 2
CHUNK_SEC = CHUNK_SAMPLES / SAMPLE_RATE


async def synthesize(text: str, voice: str, rate: str = "+0%") -> bytes:
    """Text -> 16 kHz mono Int16 PCM bytes."""
    mp3 = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate).stream():
        if chunk["type"] == "audio":
            mp3.extend(chunk["data"])
    if not mp3:
        return b""
    decoded = miniaudio.decode(bytes(mp3), output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=SAMPLE_RATE)
    return decoded.samples.tobytes()


def mp3_duration(data: bytes) -> float:
    """Playback length of an MP3 (the facilitator's TTS stream)."""
    try:
        decoded = miniaudio.decode(data, nchannels=1)
        return decoded.num_frames / decoded.sample_rate
    except Exception:
        return 0.0


def pcm_duration(pcm: bytes) -> float:
    return len(pcm) / 2 / SAMPLE_RATE


class Mic:
    """Streams PCM to the backend at real-time rate; silence unless `say()` is playing."""

    def __init__(self, send: Callable[[bytes], Awaitable[None]]):
        self._send = send
        self._buf: Optional[bytes] = None
        self._pos = 0
        self._first_sent: Optional[asyncio.Future] = None
        self._last_sent: Optional[asyncio.Future] = None
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        silence = bytes(CHUNK_BYTES)
        next_t = time.monotonic()
        while True:
            if self._buf is not None:
                chunk = self._buf[self._pos:self._pos + CHUNK_BYTES]
                if self._pos == 0 and self._first_sent and not self._first_sent.done():
                    self._first_sent.set_result(time.time())
                self._pos += len(chunk)
                if len(chunk) < CHUNK_BYTES:
                    chunk += bytes(CHUNK_BYTES - len(chunk))
                if self._pos >= len(self._buf):
                    self._buf = None
                    if self._last_sent and not self._last_sent.done():
                        self._last_sent.set_result(time.time())
            else:
                chunk = silence
            try:
                await self._send(chunk)
            except Exception:
                return
            next_t += CHUNK_SEC
            await asyncio.sleep(max(0.0, next_t - time.monotonic()))

    async def say(self, pcm: bytes) -> Tuple[float, float]:
        """Play `pcm` into the stream. Returns (start, end) wall-clock times of the speech."""
        loop = asyncio.get_running_loop()
        self._first_sent = loop.create_future()
        self._last_sent = loop.create_future()
        self._pos = 0
        self._buf = pcm
        start = await self._first_sent
        await self._last_sent
        end = start + pcm_duration(pcm)
        await asyncio.sleep(max(0.0, end - time.time()))
        return start, end
