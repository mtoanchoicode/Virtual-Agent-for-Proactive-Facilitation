import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "-")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_RATE = 16000
INT16_MAX = 32767

# Primary AI VAD (Silero) Threshold: Confidence level for speech detection.
# Higher = Stricter against noise (e.g. 0.5). Lower = catches quieter speech (e.g. 0.2).
SILERO_VAD_THRESHOLD = 0.2

# Fallback Energy-Based VAD Threshold: Used ONLY if Silero VAD is not installed.
# Audio chunks with RMS volume below this level are ignored as silence/noise.
NOISE_FLOOR_RMS = 0.008

MIN_AUDIO_SECONDS = 0.4
ROOM_SILENCE_THRESHOLD_MS = 1500  # was 5000 — reduced for faster response
IMBALANCE_WORD_THRESHOLD = 50
SUMMARY_TRIGGERS = ["summarize", "summarise", "wrap up", "recap"]
