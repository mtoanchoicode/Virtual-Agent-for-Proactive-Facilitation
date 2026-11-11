"""Generate the fixed facilitator welcome clips (run from back/):  ../.venv/Scripts/python scripts/generate_welcome.py
Edit WELCOME below and re-run to change what the facilitator says when a voice session starts."""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import edge_tts
from app.services import lang

WELCOME = {
    "en": "Hello everyone, welcome! I'm Yacine, and I'll be facilitating your session. "
          "Work together to agree on one ranking of the six items. Start with whichever feels most important to you.",
    "vi": "Xin chào mọi người, chào mừng các bạn! Mình là Yacine, người điều phối buổi thảo luận hôm nay. "
          "Hãy cùng nhau thống nhất một bảng xếp hạng cho sáu món đồ. Các bạn có thể bắt đầu với món nào quan trọng nhất.",
}
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "audios")


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for code, text in WELCOME.items():
        path = os.path.join(OUT_DIR, f"welcome_{code}.mp3")
        # One request per sentence (a single long request intermittently returns no audio for Vietnamese);
        # MP3 frames concatenate cleanly.
        data = b""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            async for chunk in edge_tts.Communicate(sentence, lang.TTS_VOICES[code]).stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
        with open(path, "wb") as f:
            f.write(data)
        print("wrote", os.path.normpath(path))


asyncio.run(main())
