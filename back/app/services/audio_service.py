import os
import wave as wave_mod
import numpy as np

from app.core.config import client, INT16_MAX, NOISE_FLOOR_RMS, SILERO_VAD_THRESHOLD

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

# Attempt to import silero-vad for advanced AI-based voice activity detection
try:
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps
    vad_model = load_silero_vad()
    has_silero_vad = True
    print("[audio_service] Silero VAD successfully loaded.")
except ImportError:
    vad_model = None
    has_silero_vad = False
    print("[audio_service] Silero VAD not found. Falling back to simple RMS threshold. Please run 'pip install silero-vad torch'.")

def is_speech_present(pcm_bytes: bytes) -> bool:
    if len(pcm_bytes) == 0:
        return False
        
    if has_silero_vad:
        try:
            # Convert PCM bytes to normalized float32 tensor
            audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / INT16_MAX
            audio_tensor = torch.from_numpy(audio)
            
            # get_speech_timestamps returns a list of dicts like {'start': 123, 'end': 456}
            speech_timestamps = get_speech_timestamps(audio_tensor, vad_model, sampling_rate=16000, threshold=SILERO_VAD_THRESHOLD)
            
            return len(speech_timestamps) > 0
        except Exception:
            pass # Ignore errors and fall through
            
        return False
    else:
        # Fallback to the old basic Energy-based VAD
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / INT16_MAX
        rms = float(np.sqrt(np.mean(audio ** 2)))
        return rms > NOISE_FLOOR_RMS

async def generate_audio_bytes(text: str) -> bytes:
    """Generate TTS audio and return raw MP3 bytes in memory (no disk I/O)."""
    try:
        import edge_tts
        print(f"[audio_service] Edge TTS streaming... (text: {text[:30]}...)")
        voice = "en-US-GuyNeural"
        communicate = edge_tts.Communicate(text, voice)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        audio_bytes = b"".join(chunks)
        print(f"[audio_service] Edge TTS done ({len(audio_bytes):,} bytes)")
        return audio_bytes
    except ImportError:
        print(f"[audio_service] edge-tts not found. Falling back to OpenAI TTS... (text: {text[:30]}...)")
        try:
            response = await client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3",
                timeout=15.0,
            )
            audio_bytes = response.read()
            print(f"[audio_service] OpenAI TTS done ({len(audio_bytes):,} bytes)")
            return audio_bytes
        except Exception as e:
            print(f"[audio_service] Error in generate_audio_bytes: {e}")
            raise


async def stream_audio_chunks(text: str):
    """Async generator: yield each MP3 chunk as it arrives from edge-tts.
    First chunk is typically ready in 200–400 ms, allowing the frontend to
    start playback via MediaSource long before the full audio is available.
    Falls back to yielding a single OpenAI TTS response if edge-tts is absent.
    """
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
        chunk_n = 0
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunk_n += 1
                yield chunk["data"]
        print(f"[audio_service] TTS stream done ({chunk_n} chunks, text: {text[:30]}...)")
    except ImportError:
        print("[audio_service] edge-tts not found — falling back to OpenAI TTS (single chunk)")
        try:
            response = await client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3",
                timeout=15.0,
            )
            yield response.read()
        except Exception as e:
            print(f"[audio_service] Error in stream_audio_chunks: {e}")
            raise
