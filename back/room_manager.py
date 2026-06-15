import asyncio
import io
import json
import time
import wave as wave_mod
from datetime import datetime
from typing import List, Optional, Dict, Set

from fastapi import WebSocket

from services import (
    client,
    shared_conv,
    process_message,
    is_speech_present,
    SAMPLE_RATE,
    whisper_model,
)

# ── Stream Parsing Helper ────────────────────────────────────────────────────
def extract_messages_from_json(json_string: str) -> List[dict]:
    messages = []
    brace_level = 0
    in_string = False
    escape = False
    obj_start = -1
    
    for i, char in enumerate(json_string):
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
            
        if not in_string:
            if char == '{':
                brace_level += 1
                if brace_level == 2:
                    obj_start = i
            elif char == '}':
                if brace_level == 2 and obj_start != -1:
                    obj_str = json_string[obj_start:i+1]
                    try:
                        parsed = json.loads(obj_str)
                        if "text" in parsed:
                            messages.append(parsed)
                    except json.JSONDecodeError:
                        pass
                brace_level -= 1
    return messages

# ── Room-level silence detection ──────────────────────────────────────────────
# How long the ENTIRE ROOM must be silent before the AI processes the turn.
ROOM_SILENCE_THRESHOLD_MS = 5000

# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------

class Participant:
    def __init__(self, session_id: str, name: str, websocket: WebSocket):
        self.session_id = session_id
        self.name = name
        self.mic_active = True
        self.websocket = websocket
        self.joined_at = datetime.utcnow().isoformat() + "Z"

        # Per-participant audio accumulation for the current shared turn.
        # Keyed by: list of raw PCM bytearray chunks received this turn.
        self.audio_chunks: bytearray = bytearray()

        # Whether this participant is currently speaking (above noise floor).
        self.is_speaking: bool = False

        # Participation entropy (0-100)
        self.entropy: int = 0

        # Continuous transcription state
        self.transcripts: Dict[int, str] = {}
        self.chunk_index: int = 0
        self.pending_tasks: Set[asyncio.Task] = set()
        self.last_speech_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "sessionId": self.session_id,
            "name": self.name,
            "micActive": self.mic_active,
            "isSpeaking": self.is_speaking,
            "entropy": self.entropy,
            "joinedAt": self.joined_at,
        }


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

class Room:
    """
    Single-room with room-level silence-based turn detection.
    """

    def __init__(self):
        self._participants: Dict[str, Participant] = {}
        self._lock = asyncio.Lock()

        # Voice session state
        self.voice_session_active: bool = False   # at least one mic is live

        # Turn state
        self._turn_active: bool = False           # a turn is in progress
        self._silence_timer: Optional[asyncio.TimerHandle] = None
        self._processing: bool = False            # AI is generating a response
        self._latest_reasoning_task: Optional[asyncio.Task] = None
        self._latest_llm_result: Optional[dict] = None

    # -- Participant management -----------------------------------------------

    async def add(self, participant: Participant) -> None:
        async with self._lock:
            self._participants[participant.session_id] = participant

    async def remove(self, session_id: str) -> Optional[Participant]:
        async with self._lock:
            p = self._participants.pop(session_id, None)
            return p

    def get(self, session_id: str) -> Optional[Participant]:
        return self._participants.get(session_id)

    def participant_list(self) -> List[dict]:
        return [p.to_dict() for p in self._participants.values()]

    @property
    def active_participants(self) -> List[Participant]:
        return [p for p in self._participants.values() if p.mic_active]

    # -- Broadcasting ---------------------------------------------------------

    async def broadcast(self, payload: dict, exclude: Optional[str] = None) -> None:
        dead: List[str] = []
        for sid, p in list(self._participants.items()):
            if sid == exclude:
                continue
            try:
                await p.websocket.send_json(payload)
            except Exception:
                dead.append(sid)
        for sid in dead:
            await self.remove(sid)

    async def send_to(self, session_id: str, payload: dict) -> None:
        p = self.get(session_id)
        if p:
            try:
                await p.websocket.send_json(payload)
            except Exception:
                await self.remove(session_id)

    # -- Voice session --------------------------------------------------------

    async def activate_voice_session(self) -> None:
        if self.voice_session_active:
            return
        self.voice_session_active = True
        await self.broadcast({
            "type": "voice_session_started",
            "participants": self.participant_list(),
        })
        print("[room] voice session started")

    async def deactivate_voice_session(self) -> None:
        if not self.voice_session_active:
            return
        self.voice_session_active = False
        self._cancel_silence_timer()
        self._turn_active = False
        for p in self._participants.values():
            p.audio_chunks.clear()
            p.is_speaking = False
            for task in list(p.pending_tasks):
                task.cancel()
            p.pending_tasks.clear()
            p.transcripts.clear()
            p.chunk_index = 0
        await self.broadcast({
            "type": "voice_session_ended",
            "participants": self.participant_list(),
        })
        print("[room] voice session ended")

    # -- Audio ingestion & turn coordination ----------------------------------

    async def ingest_audio(self, session_id: str, pcm_bytes: bytes) -> None:
        if self._processing:
            return

        p = self.get(session_id)
        if p is None or not p.mic_active:
            return

        now = time.time()
        speaking = is_speech_present(pcm_bytes)

        if speaking:
            p.last_speech_time = now

        if speaking != p.is_speaking:
            p.is_speaking = speaking
            await self.broadcast({
                "type": "participant_speaking_changed",
                "sessionId": session_id,
                "name": p.name,
                "isSpeaking": speaking,
                "participants": self.participant_list(),
            })

        if speaking or len(p.audio_chunks) > 0:
            p.audio_chunks.extend(pcm_bytes)

            if not self._turn_active and speaking:
                self._turn_active = True
                await self.broadcast({
                    "type": "turn_started",
                    "participants": self.participant_list(),
                })
                print("[room] turn started")

            if self._turn_active and speaking:
                self._reset_silence_timer()

            chunk_length_sec = len(p.audio_chunks) / (SAMPLE_RATE * 2)
            time_since_speech = now - p.last_speech_time

            if (time_since_speech > 0.5 and chunk_length_sec > 0.2) or chunk_length_sec > 15.0:
                chunk_data = bytes(p.audio_chunks)
                p.audio_chunks.clear()
                
                if len(chunk_data) > 3200:  # Ignore chunks < 0.1s
                    idx = p.chunk_index
                    p.chunk_index += 1
                    task = asyncio.create_task(self._transcribe_bg(p, chunk_data, idx))
                    p.pending_tasks.add(task)
                    task.add_done_callback(p.pending_tasks.discard)

    def _reset_silence_timer(self) -> None:
        self._cancel_silence_timer()
        loop = asyncio.get_event_loop()
        self._silence_timer = loop.call_later(
            ROOM_SILENCE_THRESHOLD_MS / 1000.0,
            lambda: asyncio.ensure_future(self._on_room_silence()),
        )

    def _cancel_silence_timer(self) -> None:
        if self._silence_timer:
            self._silence_timer.cancel()
            self._silence_timer = None

    async def _on_room_silence(self) -> None:
        if not self._turn_active or self._processing:
            return

        has_audio = any(
            len(p.audio_chunks) > 0 or len(p.transcripts) > 0 or len(p.pending_tasks) > 0
            for p in self._participants.values()
        )
        if not has_audio:
            self._turn_active = False
            return

        self._turn_active = False
        self._processing = True

        await self.broadcast({"type": "turn_processing"})
        print("[room] turn ended — processing AI response")

        try:
            await self._process_turn()
        finally:
            self._processing = False
            for p in self._participants.values():
                p.audio_chunks.clear()
                p.is_speaking = False
                p.transcripts.clear()
                p.chunk_index = 0
                p.pending_tasks.clear()

    async def _transcribe_bg(self, p: Participant, chunk_data: bytes, chunk_idx: int) -> None:
        print(f"[room][{p.name}] starting bg transcription for chunk {chunk_idx} (size {len(chunk_data)})")
        if not is_speech_present(chunk_data):
            return

        buf = io.BytesIO()
        with wave_mod.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(chunk_data)
        buf.seek(0)
        buf.name = "audio.wav"

        try:
            if whisper_model:
                loop = asyncio.get_running_loop()
                def do_transcribe():
                    buf.seek(0)
                    segments, info = whisper_model.transcribe(buf, beam_size=5, language="en")
                    return " ".join([segment.text for segment in segments])
                text = await loop.run_in_executor(None, do_transcribe)
                text = text.strip()
            else:
                res = await client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=buf,
                    language="en",
                )
                text = res.text.strip()
                
            print(f"[room][{p.name}] bg transcription {chunk_idx} done: '{text}'")
            if text:
                p.transcripts[chunk_idx] = text
                self._trigger_parallel_reasoning()
        except Exception as e:
            print(f"[room] background transcription error for {p.name}: {e}")

    def _trigger_parallel_reasoning(self) -> None:
        if self._latest_reasoning_task and not self._latest_reasoning_task.done():
            self._latest_reasoning_task.cancel()
            
        ongoing_texts = []
        for p in self._participants.values():
            sorted_texts = [p.transcripts[k] for k in sorted(p.transcripts.keys())]
            text = " ".join(sorted_texts).strip()
            if text:
                ongoing_texts.append(f"{p.name} said: {text}")
                
        if not ongoing_texts:
            return
            
        combined_ongoing = "\n".join(ongoing_texts)
        
        async def _run_llm():
            try:
                prompt = shared_conv.get_facilitation_prompt(combined_ongoing)
                res = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=prompt,
                    max_tokens=300,
                    response_format={ "type": "json_object" },
                )
                raw_json = res.choices[0].message.content
                parsed = json.loads(raw_json)
                self._latest_llm_result = parsed
                print(f"[room] Parallel reasoning completed: action={parsed.get('action')}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[room] Parallel reasoning error: {e}")

        self._latest_reasoning_task = asyncio.create_task(_run_llm())

    async def _process_turn(self) -> None:
        print("[room] _process_turn started")
        start_time = time.time()
        transcripts: List[dict] = []

        # Flush remaining chunks
        for p in self._participants.values():
            if len(p.audio_chunks) > 0:
                chunk_data = bytes(p.audio_chunks)
                p.audio_chunks.clear()
                if len(chunk_data) > 3200:
                    idx = p.chunk_index
                    p.chunk_index += 1
                    task = asyncio.create_task(self._transcribe_bg(p, chunk_data, idx))
                    p.pending_tasks.add(task)
                    task.add_done_callback(p.pending_tasks.discard)

        # Wait for all background tasks
        all_tasks = []
        for p in self._participants.values():
            all_tasks.extend(list(p.pending_tasks))
            
        if all_tasks:
            print(f"[room] waiting for {len(all_tasks)} background transcription tasks to complete...")
            await asyncio.gather(*all_tasks, return_exceptions=True)
            print("[room] all background tasks completed")

        for p in self._participants.values():
            sorted_texts = [p.transcripts[k] for k in sorted(p.transcripts.keys())]
            text = " ".join(sorted_texts).strip()
            if text:
                transcripts.append({"speaker": p.name, "text": text})
            p.transcripts.clear()
            p.chunk_index = 0
            p.pending_tasks.clear()



        if not transcripts:
            print("[room] no transcribable audio — skipping AI response")
            await self.broadcast({"type": "turn_skipped"})
            return

        print(f"[room] Transcripts collected: {transcripts}")

        # FUSE transcripts here
        shared_conv.add_turn(transcripts)

        await self.broadcast({
            "type": "turn_transcripts",
            "transcripts": transcripts,
        })

        try:
            if self._latest_reasoning_task and not self._latest_reasoning_task.done():
                print("[room] Waiting for parallel reasoning to finish...")
                try:
                    await self._latest_reasoning_task
                except Exception:
                    pass

            result = self._latest_llm_result or {}
            action = result.get("action", "NO_ACTION")
            messages = result.get("messages", [])

            self._latest_reasoning_task = None
            self._latest_llm_result = None

            print(f"[room] AI decision action (cached): {action}")

            if action == "NO_ACTION" or not messages:
                print("[room] AI chose NO_ACTION or returned empty messages, broadcasting turn_skipped")
                await self.broadcast({"type": "turn_skipped"})
            else:
                ai_text_parts = []
                for i, msg in enumerate(messages):
                    print(f"[room] processing message {i}...")
                    try:
                        res = await asyncio.wait_for(process_message(i, msg), timeout=30.0)
                        print(f"[room] message {i} processed, broadcasting...")
                        await self.broadcast({
                            "type": "messages",
                            "messages": [res],
                        })
                        if i == 0:
                            elapsed = time.time() - start_time
                            print(f"[room] Time to first response sent to frontend: {elapsed:.2f}s")
                        ai_text_parts.append(msg.get("text", ""))
                    except asyncio.TimeoutError:
                        print(f"[room] TIMEOUT processing message {i}, skipping to next.")
                    except Exception as e:
                        print(f"[room] ERROR processing message {i}: {e}")
                
                ai_text = " ".join(ai_text_parts).strip()
                shared_conv.add_ai_response(action, ai_text)

            total_elapsed = time.time() - start_time
            print(f"[room] Total turn processing time: {total_elapsed:.2f}s")
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.broadcast({"type": "error", "detail": str(e)})


# Single global room
room = Room()
