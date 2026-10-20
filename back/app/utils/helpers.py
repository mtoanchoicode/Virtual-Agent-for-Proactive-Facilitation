import asyncio
import re
import subprocess
import base64
import aiofiles

# ---------------------------------------------------------------------------
# Transcript cleanup
# ---------------------------------------------------------------------------
# Speech-to-text sometimes hallucinates on noise or silence, or loops on a word
# ("and and and and"). This cleaner removes those artefacts but deliberately KEEPS short
# real answers such as "yes", "okay" or "yeah" - they are agreements the facilitator needs.

# Phrases STT commonly invents from silence/noise. Dropped only when they are the whole transcript.
_HALLUCINATIONS = {
    "thanks for watching", "thank you for watching", "please subscribe",
    "subtitles by the amara.org community", "bye", "bye bye",
}

def clean_transcript(text: str) -> str:
    """Collapse looping repeated words and drop known whole-transcript hallucinations."""
    if not text:
        return text

    # Collapse runs of the SAME word repeated 3+ times (case-insensitive) into one copy.
    # "and and and and" -> "and". Two repeats ("very very", "had had") are kept as real speech.
    text = re.sub(
        r'\b(\w+)(?:\s+\1){2,}\b',
        r'\1',
        text,
        flags=re.IGNORECASE,
    )

    cleaned = " ".join(text.split()).strip()
    if cleaned.lower().strip(" .,!?") in _HALLUCINATIONS:
        return ""
    return cleaned

async def exec_command(command: str):
    print(f"[helpers] executing command: {command}")
    loop = asyncio.get_event_loop()

    def run_sync():
        return subprocess.run(command, shell=True, capture_output=True, text=True)

    result = await loop.run_in_executor(None, run_sync)
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise Exception(f"Command failed with code {result.returncode}: {error_msg}")
    return result.stdout

async def audio_file_to_base64(file_path: str) -> str:
    async with aiofiles.open(file_path, mode="rb") as f:
        data = await f.read()
        return base64.b64encode(data).decode("utf-8")
