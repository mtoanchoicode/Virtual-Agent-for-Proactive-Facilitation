import os
import wave as wave_mod
import numpy as np
import aiofiles

from app.core.config import client, INT16_MAX, NOISE_FLOOR_RMS

whisper_model = None

class SpeakerManager:
    def __init__(self, profiles_dir="profiles"):
        self.profiles_dir = profiles_dir
        self.fingerprints = {}
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

def is_speech_present(pcm_bytes: bytes) -> bool:
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / INT16_MAX
    if len(audio) == 0:
        return False
    rms = float(np.sqrt(np.mean(audio ** 2)))
    return rms > NOISE_FLOOR_RMS

async def generate_audio(text: str, file_path: str):
    try:
        import edge_tts
        print(f"[audio_service] Requesting Edge TTS... (text: {text[:30]}...)")
        voice = "en-US-GuyNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(file_path)
        print(f"[audio_service] Saved audio to {file_path}")
    except ImportError:
        print(f"[audio_service] edge-tts not found. Requesting OpenAI TTS... (text: {text[:30]}...)")
        try:
            response = await client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3",
                timeout=15.0
            )
            print("[audio_service] OpenAI TTS response received, reading content...")
            audio_content = response.read()
            async with aiofiles.open(file_path, mode="wb") as f:
                await f.write(audio_content)
            print(f"[audio_service] Saved audio to {file_path}")
        except Exception as e:
            print(f"[audio_service] Error in generate_audio: {e}")
            raise e
