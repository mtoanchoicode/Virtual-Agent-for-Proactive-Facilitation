"""WebSocket participant client, HTTP helpers and a model of the facilitator's audio playback."""
import asyncio
import base64
import json
import time
from typing import Awaitable, Callable, Dict, List, Optional

import httpx
from websockets.asyncio.client import connect

from simlab.audio import mp3_duration


async def http_get(base_url: str, path: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(base_url + path)
        r.raise_for_status()
        return r.json()


async def http_post(base_url: str, path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(base_url + path, json=body)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"POST {path}: {data['error']}")
        return data


class RoomClient:
    """One simulated participant's connection to /ws/voice."""

    def __init__(self, base_url: str, name: str, on_event: Callable[["RoomClient", dict], Awaitable[None]]):
        self.ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws/voice"
        self.name = name
        self.on_event = on_event
        self.session_id: Optional[str] = None
        self.ws = None
        self._rx: Optional[asyncio.Task] = None
        self._joined: Optional[asyncio.Future] = None

    async def connect(self) -> None:
        self.ws = await connect(self.ws_url, max_size=None)
        self._rx = asyncio.create_task(self._recv())

    async def _recv(self) -> None:
        try:
            async for msg in self.ws:
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                if data.get("type") == "joined" and self._joined and not self._joined.done():
                    self.session_id = data["sessionId"]
                    self._joined.set_result(data)
                elif data.get("type") == "error" and self._joined and not self._joined.done():
                    self._joined.set_exception(RuntimeError(f"{self.name}: {data.get('detail')}"))
                await self.on_event(self, data)
        except Exception:
            pass

    async def send_json(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload))

    async def send_audio(self, pcm: bytes) -> None:
        await self.ws.send(pcm)

    async def join(self) -> dict:
        self._joined = asyncio.get_running_loop().create_future()
        await self.send_json({"type": "join", "name": self.name})
        return await asyncio.wait_for(self._joined, 10)

    async def board_move(self, item_id: str, to_index: int) -> None:
        await self.send_json({"type": "board_drag_start", "itemId": item_id})
        await self.send_json({"type": "board_move", "itemId": item_id, "toIndex": to_index})

    async def board_agree(self, agreed: bool = True) -> None:
        await self.send_json({"type": "board_agree", "agreed": agreed})

    async def close(self) -> None:
        try:
            await self.send_json({"type": "leave"})
            await asyncio.sleep(0.3)
            await self.ws.close()
        except Exception:
            pass
        if self._rx:
            self._rx.cancel()


class FacilitatorChannel:
    """Models what participants hear from the facilitator.

    The front end queues each TTS message (audio_stream_start/chunk/end) and plays them one
    after another; turn_interrupted stops playback. We do the same, so we know when the
    facilitator is audible, without a browser.
    """

    def __init__(self):
        self.utterances: List[dict] = []
        self._open: Dict[str, dict] = {}
        self._play_end = 0.0
        self.last_action: str = ""

    def on_start(self, msg_id: str, text: str, now: float) -> dict:
        u = {"msgId": msg_id, "text": text, "action": self.last_action, "arrived": now,
             "start": None, "end": None, "interrupted": False, "_mp3": bytearray()}
        self._open[msg_id] = u
        self.utterances.append(u)
        return u

    def on_chunk(self, msg_id: str, b64: str, now: float) -> None:
        u = self._open.get(msg_id)
        if u is None:
            return
        if u["start"] is None:
            u["start"] = max(now, self._play_end)
        u["_mp3"].extend(base64.b64decode(b64))

    def on_end(self, msg_id: str, now: float) -> None:
        u = self._open.pop(msg_id, None)
        if u is None:
            return
        if u["start"] is None:
            u["start"] = max(now, self._play_end)
        u["end"] = u["start"] + mp3_duration(bytes(u["_mp3"]))
        u["_mp3"] = bytearray()
        self._play_end = max(self._play_end, u["end"])

    def on_interrupt(self, now: float) -> None:
        for u in self._open.values():
            u["start"] = u["start"] or now
            u["end"] = now
            u["interrupted"] = True
        self._open.clear()
        for u in self.utterances:
            if u["end"] is not None and u["end"] > now:
                u["end"] = max(u["start"], now)
                u["interrupted"] = True
        self._play_end = now

    def speaking(self, now: float) -> bool:
        if self._open:
            return True
        return now < self._play_end

    def records(self) -> List[dict]:
        return [{k: v for k, v in u.items() if k != "_mp3"} for u in self.utterances if u["start"] is not None]
