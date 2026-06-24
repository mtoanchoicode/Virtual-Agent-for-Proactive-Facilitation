import asyncio
import io
import json
import time
import re
import wave as wave_mod
from datetime import datetime
from typing import List, Optional, Dict, Set

from fastapi import WebSocket

from app.core.config import client, SAMPLE_RATE, ROOM_SILENCE_THRESHOLD_MS
from app.services.llm_service import shared_conv, process_message
from app.services.audio_service import is_speech_present, whisper_model

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

class Participant:
    def __init__(self, session_id: str, name: str, websocket: WebSocket):
        self.session_id = session_id
        self.name = name
        self.mic_active = True
        self.websocket = websocket
        self.joined_at = datetime.utcnow().isoformat() + "Z"

        self.audio_chunks: bytearray = bytearray()
        self.is_speaking: bool = False
        self.entropy: int = 0
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

class Room:
    def __init__(self):
        self._participants: Dict[str, Participant] = {}
        self._lock = asyncio.Lock()
        self.voice_session_active: bool = False
        self._turn_active: bool = False
        self._silence_timer: Optional[asyncio.TimerHandle] = None
        self._processing: bool = False
        self._intervention_needed: bool = False
        self._monitor_task: Optional[asyncio.Task] = None

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

    async def activate_voice_session(self) -> None:
        if self.voice_session_active:
            return
        self.voice_session_active = True
        self._monitor_task = asyncio.create_task(self._proactive_monitor_loop())
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
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
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
                
                if len(chunk_data) > 3200:
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
        if not has_audio and not self._intervention_needed:
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
        except Exception as e:
            print(f"[room] background transcription error for {p.name}: {e}")

    async def _proactive_monitor_loop(self) -> None:
        while self.voice_session_active:
            await asyncio.sleep(3.0)
            if self._processing:
                continue

            ongoing_texts = []
            metadata_parts = []
            now = time.time()
            for p in self._participants.values():
                sorted_texts = [p.transcripts[k] for k in sorted(p.transcripts.keys())]
                text = " ".join(sorted_texts).strip()
                if text:
                    ongoing_texts.append(f"{p.name} said: {text}")
                
                time_since_speech = now - p.last_speech_time if p.last_speech_time > 0 else 0
                metadata_parts.append(f"User '{p.name}' last spoke {time_since_speech:.1f} seconds ago.")

            combined_ongoing = "\n".join(ongoing_texts)
            metadata = "[METADATA]\n" + "\n".join(metadata_parts)
            
            try:
                prompt = shared_conv.get_lightweight_polling_prompt(combined_ongoing, metadata)
                res = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=prompt,
                    max_tokens=10,
                )
                answer = res.choices[0].message.content.strip().upper()
                print(f"[room] Lightweight Model polling... answer={answer}")
                if "YES" in answer:
                    self._intervention_needed = True
                    if not self._turn_active:
                        print("[room] Lightweight Model said YES during silence. Triggering main LLM immediately.")
                        self._turn_active = True
                        asyncio.create_task(self._on_room_silence())
                else:
                    self._intervention_needed = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[room] Proactive monitor error: {e}")

    async def _process_turn(self) -> None:
        print("[room] _process_turn started")
        start_time = time.time()
        transcripts: List[dict] = []

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

        if not transcripts and not self._intervention_needed:
            print("[room] no transcribable audio and no intervention needed — skipping AI response")
            await self.broadcast({"type": "turn_skipped"})
            return

        print(f"[room] Transcripts collected: {transcripts}")

        if transcripts:
            shared_conv.add_turn(transcripts)

        await self.broadcast({
            "type": "turn_transcripts",
            "transcripts": transcripts,
        })

        try:
            if not self._intervention_needed:
                print("[room] AI decision action: NO_ACTION (intervention not needed)")
                await self.broadcast({"type": "turn_skipped"})
                self._intervention_needed = False
            else:
                ongoing_texts = []
                metadata_parts = []
                now = time.time()
                for p in self._participants.values():
                    time_since_speech = now - p.last_speech_time if p.last_speech_time > 0 else 0
                    metadata_parts.append(f"User '{p.name}' last spoke {time_since_speech:.1f} seconds ago.")
                metadata = "[METADATA]\n" + "\n".join(metadata_parts)
                combined_ongoing = "\n".join(ongoing_texts)

                print("[room] Generating main AI response (streaming)...")
                prompt = shared_conv.get_facilitation_prompt(combined_ongoing, metadata)
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=prompt,
                    max_tokens=300,
                    stream=True,
                )
                
                self._intervention_needed = False
                action = "NO_ACTION"
                action_found = False
                buffer = ""
                current_sentence = ""
                ai_text_parts = []
                msg_index = 0

                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    
                    if not action_found:
                        buffer += delta
                        match = re.search(r"(?i)(?:TEXT|MESSAGE):\s*", buffer)
                        if match:
                            action_match = re.search(r"(?i)ACTION:\s*([a-zA-Z_]+)", buffer)
                            action = action_match.group(1).upper() if action_match else "UNKNOWN"
                            print(f"[room] AI decision action (streamed): {action}")
                            action_found = True
                            current_sentence = buffer[match.end():]
                            buffer = ""
                    else:
                        current_sentence += delta
                    
                    if action_found:
                        match = re.search(r'([.?!]+)["\'\)]*\s+$', current_sentence)
                        if match:
                            text_to_process = current_sentence.strip()
                            if text_to_process:
                                ai_text_parts.append(text_to_process)
                                print(f"[room] processing chunk {msg_index}...")
                                try:
                                    res_msg = await asyncio.wait_for(process_message(msg_index, {"text": text_to_process}), timeout=30.0)
                                    print(f"[room] chunk {msg_index} processed, broadcasting...")
                                    await self.broadcast({
                                        "type": "messages",
                                        "messages": [res_msg],
                                    })
                                    if msg_index == 0:
                                        elapsed = time.time() - start_time
                                        print(f"[room] Time to first response sent to frontend: {elapsed:.2f}s")
                                except asyncio.TimeoutError:
                                    print(f"[room] TIMEOUT processing chunk {msg_index}, skipping.")
                                except Exception as e:
                                    print(f"[room] ERROR processing chunk {msg_index}: {e}")
                                msg_index += 1
                            current_sentence = ""

                # Flush remainder
                if not action_found:
                    text_to_process = buffer
                    action_match = re.search(r"(?i)ACTION:\s*([a-zA-Z_]+)", text_to_process)
                    if action_match:
                        action = action_match.group(1).upper()
                    text_to_process = re.sub(r"(?i)ACTION:\s*[a-zA-Z_]+\s*", "", text_to_process)
                    text_to_process = re.sub(r"(?i)(?:TEXT|MESSAGE):\s*", "", text_to_process)
                    text_to_process = re.sub(r"(?i)\[Action taken:.*?\]\s*(?:Yacine said:\s*)?", "", text_to_process)
                    current_sentence = text_to_process.strip()

                if current_sentence.strip():
                    text_to_process = current_sentence.strip()
                    ai_text_parts.append(text_to_process)
                    print(f"[room] processing chunk {msg_index}...")
                    try:
                        res_msg = await asyncio.wait_for(process_message(msg_index, {"text": text_to_process}), timeout=30.0)
                        await self.broadcast({
                            "type": "messages",
                            "messages": [res_msg],
                        })
                        if msg_index == 0:
                            elapsed = time.time() - start_time
                            print(f"[room] Time to first response sent to frontend: {elapsed:.2f}s")
                    except Exception as e:
                        print(f"[room] ERROR processing chunk {msg_index}: {e}")

                if not ai_text_parts:
                    print("[room] AI chose NO_ACTION or returned empty messages, broadcasting turn_skipped")
                    await self.broadcast({"type": "turn_skipped"})
                else:
                    if action == "NO_ACTION":
                        action = "UNKNOWN"
                    ai_text = " ".join(ai_text_parts).strip()
                    shared_conv.add_ai_response(action, ai_text)

                    now = time.time()
                    self._last_ai_speech_time = now
                    for p in self._participants.values():
                        p.last_speech_time = 0.0

            total_elapsed = time.time() - start_time
            print(f"[room] Total turn processing time: {total_elapsed:.2f}s")
        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.broadcast({"type": "error", "detail": str(e)})

room = Room()
