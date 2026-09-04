import os
import base64
import asyncio
import io
import json
import time
import re
import wave as wave_mod
from datetime import datetime
from typing import List, Optional, Dict, Set

from fastapi import WebSocket

from app.core.config import client, SAMPLE_RATE, ROOM_SILENCE_THRESHOLD_MS, IMBALANCE_WORD_THRESHOLD, SUMMARY_TRIGGERS
from app.services.llm_service import shared_conv
from app.services.audio_service import is_speech_present, whisper_model, stream_audio_chunks
from app.utils.helpers import clean_transcript

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


# ---------------------------------------------------------------------------
# Per-turn timing log
# ---------------------------------------------------------------------------
_TIMING_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "timing_log.txt",
)

def _write_timing_log(timing: dict) -> None:
    """Append a structured per-step timing breakdown for one facilitator turn to timing_log.txt."""
    t0 = timing["t_silence"]

    def rel(key: str) -> str:
        v = timing.get(key)
        return f"{v - t0:7.3f}s" if v is not None else "    N/A "

    def gap(key_a: str, key_b: str) -> str:
        a, b = timing.get(key_a), timing.get(key_b)
        return f"({b - a:+.3f}s)" if a is not None and b is not None else "        "

    lines = [
        "",
        "=" * 65,
        f"  Turn #{timing['turn_n']:03d}  ·  {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"  Action : {timing['action']}",
        f"  Text   : \"{timing['text_snippet']}\"",
        "=" * 65,
        f"  {'Checkpoint':<28} {'From silence':>12}   {'Step delta':>12}",
        f"  {'-' * 55}",
        f"  {'Silence detected':<28} {'  0.000s':>12}",
        f"  {'Processing start':<28} {rel('t_process_start'):>12}   {gap('t_silence', 't_process_start'):>12}",
        f"  {'STT tasks done':<28} {rel('t_stt_done'):>12}   {gap('t_process_start', 't_stt_done'):>12}",
        f"  {'LLM first token':<28} {rel('t_llm_first_token'):>12}   {gap('t_stt_done', 't_llm_first_token'):>12}",
        f"  {'LLM action parsed':<28} {rel('t_action_found'):>12}   {gap('t_llm_first_token', 't_action_found'):>12}",
        f"  {'LLM stream done':<28} {rel('t_llm_stream_done'):>12}   {gap('t_action_found', 't_llm_stream_done'):>12}",
        f"  {'TTS start  (chunk 0)':<28} {rel('t_tts_start'):>12}   {gap('t_llm_stream_done', 't_tts_start'):>12}",
        f"  {'TTS first chunk sent':<28} {rel('t_tts_first_chunk'):>12}   {gap('t_tts_start', 't_tts_first_chunk'):>12}",
        f"  {'TTS stream done':<28} {rel('t_tts_done'):>12}   {gap('t_tts_first_chunk', 't_tts_done'):>12}",
        f"  {'-' * 55}",
        f"  {'TOTAL  silence → first audio':<28} {rel('t_tts_first_chunk'):>12}",
        "=" * 65,
        "",
    ]
    try:
        with open(_TIMING_LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as exc:
        print(f"[timing] Failed to write timing_log.txt: {exc}")


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
        self.word_count: int = 0
        self.pending_tasks: Set[asyncio.Task] = set()
        self.last_speech_time: float = 0.0
        self.interruption_start_time: float = 0.0

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
        self._turn_lock = asyncio.Lock()  # Serialises entry into _on_room_silence
        self._processing: bool = False  # True while a turn is being processed
        self._interrupted: bool = False
        self._current_turn_task: Optional[asyncio.Task] = None
        self._tts_tasks: Set[asyncio.Task] = set()
        self._turn_count: int = 0
        self.mode: str = "full"  # "full" or "lite"

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

    async def broadcast_log(self, message: str, level: str = "info") -> None:
        """Print to terminal AND stream to all connected frontends."""
        print(message)
        await self.broadcast({
            "type": "facilitator_log",
            "message": message,
            "level": level,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

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
        await self.broadcast({
            "type": "voice_session_started",
            "participants": self.participant_list(),
        })
        await self.broadcast_log("[room] Voice session started", "success")

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
            p.word_count = 0
        await self.broadcast({
            "type": "voice_session_ended",
            "participants": self.participant_list(),
        })
        await self.broadcast_log("[room] Voice session ended", "info")

    async def ingest_audio(self, session_id: str, pcm_bytes: bytes) -> None:
        p = self.get(session_id)
        if p is None or not p.mic_active:
            return

        now = time.time()
        speaking = is_speech_present(pcm_bytes)

        if speaking:
            p.last_speech_time = now

        if self._processing:
            # Smooth the speaking signal: if they spoke within the last 500ms, consider it a continuous burst
            if (now - p.last_speech_time) < 0.3:
                if p.interruption_start_time == 0.0:
                    p.interruption_start_time = now
                    print(f"[room] Interruption timer started for {p.name}")
                
                p.audio_chunks.extend(pcm_bytes)
                
                if now - p.interruption_start_time >= 0.6:  # 600ms threshold
                    print(f"[room] Interruption threshold met for {p.name}! Cancelling turn.")
                    p.interruption_start_time = 0.0
                    if not self._interrupted:
                        self._interrupted = True
                        if self._current_turn_task and not self._current_turn_task.done():
                            self._current_turn_task.cancel()
                        
                        for tts_task in list(self._tts_tasks):
                            if not tts_task.done():
                                tts_task.cancel()
                        self._tts_tasks.clear()
                        
                        self._processing = False
                        self._turn_active = True
                        
                        await self.broadcast({
                            "type": "turn_interrupted",
                            "participants": self.participant_list(),
                        })
                        await self.broadcast_log(f"[room] Thinking interrupted by {p.name}", "warning")
                        self._reset_silence_timer()
            else:
                p.interruption_start_time = 0.0
            return

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
                await self.broadcast_log(f"[room] Turn started — {p.name} speaking", "info")

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
        """Triggered by the silence timer after the user stops talking.
        Runs transcription + AI facilitation for the current turn.
        Immediately ready for the next turn when done — no cooldown.
        """
        t_silence = time.time()  # Exact moment silence was detected — used as T=0 for latency
        async with self._turn_lock:
            if self._processing:
                return
            if not self._turn_active:
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

        self._interrupted = False
        await self.broadcast({"type": "turn_processing"})
        await self.broadcast_log("[room] Turn ended — processing AI response…", "info")

        try:
            self._current_turn_task = asyncio.create_task(self._process_turn(t_silence))
            await self._current_turn_task
        except asyncio.CancelledError:
            print("[room] _process_turn was cancelled due to interruption.")
        finally:
            self._current_turn_task = None
            if not self._interrupted:
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
                    # beam_size=1 (greedy) is 3-5x faster than beam_size=5 with minimal accuracy loss
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
                
            text = clean_transcript(text)
            await self.broadcast_log(f"[transcript] {p.name}: \"{text}\"", "info")
            if text:
                p.transcripts[chunk_idx] = text
        except Exception as e:
            print(f"[room] background transcription error for {p.name}: {e}")


    async def _process_and_broadcast(self, idx: int, text: str, timing: dict) -> None:
        """Stream TTS audio chunks to all clients as edge-tts yields them.
        Runs as a background task so sentence N+1 can stream while N plays."""
        try:
            if idx == 0:
                timing["t_tts_start"] = time.time()

            msg_id = f"{timing['turn_n']}_{idx}"

            # Signal frontend to create MediaSource + Audio element immediately
            await self.broadcast({
                "type": "audio_stream_start",
                "msgId": msg_id,
                "text": text,
                "idx": idx,
            })

            chunk_count = 0
            async for audio_chunk in stream_audio_chunks(text):
                encoded = base64.b64encode(audio_chunk).decode("utf-8")
                await self.broadcast({
                    "type": "audio_stream_chunk",
                    "msgId": msg_id,
                    "data": encoded,
                })
                if chunk_count == 0 and idx == 0:
                    # Record when first bytes hit the wire — this is TTFA
                    timing["t_tts_first_chunk"] = time.time()
                chunk_count += 1

            await self.broadcast({
                "type": "audio_stream_end",
                "msgId": msg_id,
            })

            if idx == 0:
                timing["t_tts_done"] = time.time()
                first = timing.get("t_tts_first_chunk") or timing["t_tts_done"]
                total = first - timing["t_silence"]
                print(f"[LATENCY] Turn #{timing['turn_n']:03d}  silence→first audio: {total:.2f}s")
                _write_timing_log(timing)
        except asyncio.CancelledError:
            print(f"[room] TTS stream {idx} was cancelled due to interruption.")
            raise
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"[room] ERROR in _process_and_broadcast chunk {idx}: {e}")

    async def _process_turn(self, silence_at: float) -> None:
        """Route to full or lite processing based on room.mode."""
        if self.mode == "lite":
            await self._process_turn_lite(silence_at)
        else:
            await self._process_turn_full(silence_at)

    async def _process_turn_lite(self, silence_at: float) -> None:
        """Lite Mode: simple LLM prompt, always speaks, no action parsing."""
        await self.broadcast_log("[room][lite] Processing turn…", "info")
        t_process_start = time.time()
        self._turn_count += 1
        timing: dict = {
            "turn_n":              self._turn_count,
            "t_silence":           silence_at,
            "t_process_start":     t_process_start,
            "t_stt_done":          None,
            "t_llm_first_token":   None,
            "t_action_found":      None,
            "t_llm_stream_done":   None,
            "t_tts_start":         None,
            "t_tts_first_chunk":   None,
            "t_tts_done":          None,
            "action":              "LITE",
            "text_snippet":        "",
        }
        transcripts: List[dict] = []

        # Finalize remaining audio
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

        # Wait for background transcriptions
        all_tasks = []
        for p in self._participants.values():
            all_tasks.extend(list(p.pending_tasks))
        if all_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=1.5,
                )
            except asyncio.TimeoutError:
                print("[room][lite] STT tasks timed out after 1.5s")

        timing["t_stt_done"] = time.time()

        # Collect transcripts
        for p in self._participants.values():
            sorted_texts = [p.transcripts[k] for k in sorted(p.transcripts.keys())]
            text = " ".join(sorted_texts).strip()
            if text:
                transcripts.append({"speaker": p.name, "text": text})
            p.transcripts.clear()
            p.chunk_index = 0
            p.pending_tasks.clear()

        if not transcripts:
            print("[room][lite] no transcribable audio — skipping")
            await self.broadcast({"type": "turn_skipped"})
            return

        shared_conv.add_turn(transcripts)
        await self.broadcast({"type": "turn_transcripts", "transcripts": transcripts})
        await self.broadcast_log(f"[room][lite] Transcripts collected ({len(transcripts)} speaker(s))", "info")

        try:
            prompt = shared_conv.get_lite_prompt()
            await self.broadcast_log("[room][lite] Generating AI response…", "info")
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=prompt,
                max_tokens=150,
                stream=True,
            )

            full_text = ""
            current_sentence = ""
            msg_index = 0

            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""

                if timing["t_llm_first_token"] is None and delta:
                    timing["t_llm_first_token"] = time.time()

                full_text += delta
                current_sentence += delta

                # Stream sentences to TTS as they complete
                match = re.search(r'([.?!]+)["\')]*\s+$', current_sentence)
                if match:
                    text_to_process = current_sentence.strip()
                    if text_to_process:
                        if msg_index == 0:
                            timing["text_snippet"] = text_to_process[:60]
                        task = asyncio.create_task(
                            self._process_and_broadcast(msg_index, text_to_process, timing)
                        )
                        self._tts_tasks.add(task)
                        task.add_done_callback(self._tts_tasks.discard)
                        msg_index += 1
                    current_sentence = ""

            timing["t_llm_stream_done"] = time.time()

            # Flush remainder
            if current_sentence.strip():
                text_to_process = current_sentence.strip()
                if msg_index == 0:
                    timing["text_snippet"] = text_to_process[:60]
                task = asyncio.create_task(
                    self._process_and_broadcast(msg_index, text_to_process, timing)
                )
                self._tts_tasks.add(task)
                task.add_done_callback(self._tts_tasks.discard)

            if not full_text.strip():
                await self.broadcast({"type": "turn_skipped"})
            else:
                timing["action"] = "LITE"
                shared_conv.add_lite_ai_response(full_text.strip())
                await self.broadcast({"type": "facilitator_action", "action": "LITE"})
                await self.broadcast_log("[room][lite] AI spoke — ready for next turn", "success")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.broadcast({"type": "error", "detail": str(e)})

    async def _process_turn_full(self, silence_at: float) -> None:

        await self.broadcast_log("[room] Processing turn…", "info")
        t_process_start = time.time()
        self._turn_count += 1
        timing: dict = {
            "turn_n":              self._turn_count,
            "t_silence":           silence_at,
            "t_process_start":     t_process_start,
            "t_stt_done":          None,
            "t_llm_first_token":   None,
            "t_action_found":      None,
            "t_llm_stream_done":   None,
            "t_tts_start":         None,
            "t_tts_first_chunk":   None,   # when first audio bytes hit the wire (= TTFA)
            "t_tts_done":          None,
            "action":              "NO_ACTION",
            "text_snippet":        "",
        }
        transcripts: List[dict] = []

        # Finalize any remaining audio chunks into transcription tasks
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

        # Wait for all background transcription tasks
        all_tasks = []
        for p in self._participants.values():
            all_tasks.extend(list(p.pending_tasks))
            
        if all_tasks:
            print(f"[room] waiting for {len(all_tasks)} background transcription tasks to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=1.5,  # reduced from 3s — proceed with available transcripts sooner
                )
                print("[room] all background tasks completed")
            except asyncio.TimeoutError:
                print("[room] STT tasks timed out after 1.5s — proceeding with available transcripts")

        timing["t_stt_done"] = time.time()

        # Collect transcripts and update word counts
        for p in self._participants.values():
            sorted_texts = [p.transcripts[k] for k in sorted(p.transcripts.keys())]
            text = " ".join(sorted_texts).strip()
            if text:
                transcripts.append({"speaker": p.name, "text": text})
                # Add word count (split by spaces)
                p.word_count += len(text.split())
            p.transcripts.clear()
            p.chunk_index = 0
            p.pending_tasks.clear()

        has_transcripts = len(transcripts) > 0

        # Skip if there's nothing to work with
        if not has_transcripts:
            print("[room] no transcribable audio — skipping")
            await self.broadcast({"type": "turn_skipped"})
            return

        await self.broadcast_log(f"[room] Transcripts collected ({len(transcripts)} speaker(s))", "info")

        # Add user transcripts to conversation history
        if has_transcripts:
            shared_conv.add_turn(transcripts)

        await self.broadcast({
            "type": "turn_transcripts",
            "transcripts": transcripts,
        })

        try:
            # Build metadata for the LLM
            metadata_parts = []
            now = time.time()
            for p in self._participants.values():
                time_since_speech = now - p.last_speech_time if p.last_speech_time > 0 else 0
                metadata_parts.append(f"User '{p.name}' last spoke {time_since_speech:.1f} seconds ago.")
            metadata = "[METADATA]\n" + "\n".join(metadata_parts)

            # Detect imbalance
            quiet_target = None
            active_participants = self.active_participants
            if len(active_participants) == 2:
                p1, p2 = active_participants
                if p1.word_count - p2.word_count >= IMBALANCE_WORD_THRESHOLD:
                    quiet_target = p2.name
                elif p2.word_count - p1.word_count >= IMBALANCE_WORD_THRESHOLD:
                    quiet_target = p1.name
            
            # Detect summary keywords in current turn
            force_summarize = False
            for t in transcripts:
                text_lower = t["text"].lower()
                if any(trigger in text_lower for trigger in SUMMARY_TRIGGERS):
                    force_summarize = True
                    break

            if force_summarize:
                await self.broadcast_log("[room] Keyword trigger detected. Forcing SUMMARIZE.", "warning")
            elif quiet_target:
                await self.broadcast_log(f"[room] Imbalance detected. Forcing ENCOURAGE for {quiet_target}", "warning")

            await self.broadcast_log("[room] Generating AI response…", "info")
            prompt = shared_conv.get_facilitation_prompt(
                metadata, 
                force_encourage_target=quiet_target,
                force_summarize=force_summarize
            )
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=prompt,
                max_tokens=300,
                stream=True,
            )
            
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

                # Record time of very first LLM token
                if timing["t_llm_first_token"] is None and delta:
                    timing["t_llm_first_token"] = time.time()
                
                if not action_found:
                    buffer += delta
                    match = re.search(r"(?i)(?:TEXT|MESSAGE):\s*", buffer)
                    if match:
                        action_match = re.search(r"(?i)ACTION:\s*([a-zA-Z_]+)", buffer)
                        action = action_match.group(1).upper() if action_match else "UNKNOWN"
                        timing["t_action_found"] = time.time()
                        await self.broadcast_log(f"[room] AI action decided: {action}", "success" if action != "NO_ACTION" else "info")
                        await self.broadcast({"type": "facilitator_action", "action": action})
                        action_found = True
                        current_sentence = buffer[match.end():]
                        buffer = ""
                else:
                    current_sentence += delta
                
                # Only process text chunks if the AI decided to take an action
                if action_found and action != "NO_ACTION":
                    match = re.search(r'([.?!]+)["\')]*\s+$', current_sentence)
                    if match:
                        text_to_process = current_sentence.strip()
                        if text_to_process:
                            if msg_index == 0:
                                timing["text_snippet"] = text_to_process[:60]
                            ai_text_parts.append(text_to_process)
                            # Fire TTS as a background task — don't block the LLM stream
                            task = asyncio.create_task(
                                self._process_and_broadcast(msg_index, text_to_process, timing)
                            )
                            self._tts_tasks.add(task)
                            task.add_done_callback(self._tts_tasks.discard)
                            msg_index += 1
                        current_sentence = ""

            timing["t_llm_stream_done"] = time.time()

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

            # If LLM chose NO_ACTION, don't process remaining text
            if action == "NO_ACTION":
                await self.broadcast_log("[room] AI chose NO_ACTION — silent", "info")
                shared_conv.add_ai_response(action, "(remains silent)")
                await self.broadcast({"type": "turn_skipped"})
                return

            if current_sentence.strip():
                text_to_process = current_sentence.strip()
                if msg_index == 0:
                    timing["text_snippet"] = text_to_process[:60]
                ai_text_parts.append(text_to_process)
                # Fire TTS as a background task — don't block the LLM stream flush
                task = asyncio.create_task(
                    self._process_and_broadcast(msg_index, text_to_process, timing)
                )
                self._tts_tasks.add(task)
                task.add_done_callback(self._tts_tasks.discard)

            if not ai_text_parts:
                print("[room] AI returned empty text, broadcasting turn_skipped")
                await self.broadcast({"type": "turn_skipped"})
            else:
                ai_text = " ".join(ai_text_parts).strip()
                timing["action"] = action
                shared_conv.add_ai_response(action, ai_text)
                await self.broadcast_log("[room] AI spoke — ready for next turn", "success")

            # Reset word counts if action was ENCOURAGE
            if action == "ENCOURAGE":
                for p in self._participants.values():
                    p.word_count = 0
                await self.broadcast_log("[room] Reset all word counts to 0 after ENCOURAGE", "info")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await self.broadcast({"type": "error", "detail": str(e)})

room = Room()
