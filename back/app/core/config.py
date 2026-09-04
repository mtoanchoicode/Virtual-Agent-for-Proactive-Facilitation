import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "-")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_RATE = 16000
INT16_MAX = 32767
NOISE_FLOOR_RMS = 0.008
MIN_AUDIO_SECONDS = 0.4
ROOM_SILENCE_THRESHOLD_MS = 1500  # was 5000 — reduced for faster response
IMBALANCE_WORD_THRESHOLD = 50
SUMMARY_TRIGGERS = ["summarize", "summarise", "wrap up", "recap"]
