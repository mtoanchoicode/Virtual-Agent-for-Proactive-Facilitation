import os
import asyncio
import json
import base64
import subprocess
import shutil
import wave as wave_mod
import io
from typing import List, Dict

import aiofiles
import numpy as np
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "-")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"

# We force the use of the OpenAI API (large-v2) because the local CPU model (base.en) is struggling with accuracy.
# If you want to use the local model again, uncomment the code below:
# try:
#     from faster_whisper import WhisperModel
#     print("[services] Loading faster-whisper model...")
#     whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
#     print("[services] faster-whisper model loaded.")
# except ImportError:
#     print("[services] faster-whisper not found. Falling back to OpenAI STT.")
whisper_model = None


SAMPLE_RATE = 16000
INT16_MAX = 32767
NOISE_FLOOR_RMS = 0.008
MIN_AUDIO_SECONDS = 0.4

# ---------------------------------------------------------------------------
# Speaker Identification
# ---------------------------------------------------------------------------

class SpeakerManager:
    def __init__(self, profiles_dir="profiles"):
        self.profiles_dir = profiles_dir
        self.fingerprints: Dict[str, np.ndarray] = {}
        if os.path.isdir(profiles_dir):
            self.load_profiles()

    def load_profiles(self):
        for filename in os.listdir(self.profiles_dir):
            if filename.endswith(".wav"):
                name = filename.replace(".wav", "")
                path = os.path.join(self.profiles_dir, filename)
                with wave_mod.open(path, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                    fft_vals = np.abs(np.fft.rfft(audio))
                    self.fingerprints[name] = fft_vals / np.max(fft_vals)
        print(f"Loaded speaker profiles: {list(self.fingerprints.keys())}")

    def identify_speaker(self, pcm_bytes: bytes) -> str:
        if not self.fingerprints:
            return "Unknown"
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        if len(audio) == 0:
            return "Unknown"
        incoming_fft = np.abs(np.fft.rfft(audio))
        incoming_fft = incoming_fft / (np.max(incoming_fft) + 1e-9)
        best_match, min_dist = "Unknown", float("inf")
        for name, profile_fft in self.fingerprints.items():
            target_len = min(len(incoming_fft), len(profile_fft))
            dist = np.linalg.norm(incoming_fft[:target_len] - profile_fft[:target_len])
            if dist < min_dist:
                min_dist, best_match = dist, name
        return best_match


speaker_manager = SpeakerManager()


# ---------------------------------------------------------------------------
# Conversation Manager
# ---------------------------------------------------------------------------

class ConversationManager:
    def __init__(self):
        self.history: List[dict] = []
        self.transcript_log: List[dict] = []

    def add_entry(self, speaker: str, text: str):
        self.transcript_log.append({"speaker": speaker, "text": text})
        self.history.append({"role": "user", "content": f"{speaker} said: {text}"})

    def add_turn(self, transcripts: List[dict]):
        if not transcripts:
            return
        
        for t in transcripts:
            self.transcript_log.append(t)
            
        combined_text = "\n".join([f"{t['speaker']} said: {t['text']}" for t in transcripts])
        self.history.append({"role": "user", "content": combined_text})

    def add_ai_response(self, action: str, text: str):
        self.history.append({"role": "assistant", "content": f"[Action taken: {action}] Yacine said: {text}"})

    def get_facilitation_prompt(self, ongoing_text: str = None) -> List[dict]:
        system_content = """
You are Yacine, an AI meeting facilitator. 
FIRST, think silently about the conversation state using these questions:
- Who has been speaking most? Is anyone left out?
- Is the discussion going deep or staying surface-level?
- Is there a conflict, confusion, or unresolved question?
- Does the conversation actually NEED my help right now?

Then decide ONE of these actions:
- NO_ACTION: Stay silent (conversation is flowing well)
- ENCOURAGE: Invite a quiet participant to share
- DEEPEN: Ask a follow-up to go deeper on an idea
- SUMMARIZE: Briefly recap and propose a next step
- MEDIATE: Acknowledge tension and redirect constructively

Reply ONLY with a JSON object like:
{
  "action": "DEEPEN",  // or NO_ACTION, ENCOURAGE, SUMMARIZE, MEDIATE
  "messages": [        // EMPTY array if action is NO_ACTION
    { "text": "...", "facialExpression": "smile", "animation": "Talking_1" }
  ]
}

Expressions: smile, sad, angry, surprised, funnyFace, default.
Animations: Talking_0, Talking_1, Talking_2, Crying, Laughing, Rumba, Idle, Terrified, Angry.
"""
        messages = [{"role": "system", "content": system_content.strip()}] + self.history[-10:]
        if ongoing_text:
            messages.append({"role": "user", "content": f"[ONGOING TURN] {ongoing_text}"})
        return messages


shared_conv = ConversationManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def exec_command(command: str):
    print(f"[services] executing command: {command}")
    loop = asyncio.get_event_loop()

    def run_sync():
        return subprocess.run(command, shell=True, capture_output=True, text=True)

    result = await loop.run_in_executor(None, run_sync)
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise Exception(f"Command failed with code {result.returncode}: {error_msg}")
    return result.stdout


async def process_message(i: int, message: dict) -> dict:
    print(f"[services] process_message {i} start")
    audio_path = f"audios/message_{i}.mp3"
    print(f"[services] generating audio for message {i}...")
    await generate_audio(message["text"], audio_path)
    message["audio"] = await audio_file_to_base64(audio_path)
    print(f"[services] process_message {i} done")
    return message


async def audio_file_to_base64(file_path: str) -> str:
    async with aiofiles.open(file_path, mode="rb") as f:
        data = await f.read()
        return base64.b64encode(data).decode("utf-8")


async def generate_audio(text: str, file_path: str):
    try:
        import edge_tts
        print(f"[services] Requesting Edge TTS... (text: {text[:30]}...)")
        voice = "en-US-GuyNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(file_path)
        print(f"[services] Saved audio to {file_path}")
    except ImportError:
        print(f"[services] edge-tts not found. Requesting OpenAI TTS... (text: {text[:30]}...)")
        try:
            response = await client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3",
                timeout=15.0
            )
            print("[services] OpenAI TTS response received, reading content...")
            audio_content = response.read()
            async with aiofiles.open(file_path, mode="wb") as f:
                await f.write(audio_content)
            print(f"[services] Saved audio to {file_path}")
        except Exception as e:
            print(f"[services] Error in generate_audio: {e}")
            raise e


def is_speech_present(pcm_bytes: bytes) -> bool:
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / INT16_MAX
    if len(audio) == 0:
        return False
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return rms > NOISE_FLOOR_RMS
