import asyncio
import re
import subprocess
import base64
import aiofiles

# ---------------------------------------------------------------------------
# Transcript cleanup
# ---------------------------------------------------------------------------
# Whisper sometimes hallucinates when a non-native speaker reads English aloud.
# Common artefacts: repeated words ("and and and and"), filler runs ("yeah yeah yeah"),
# and garbled endings ("bye bye bye nice work nice work").
# This cleaner makes the transcript readable before it is sent to the LLM.

_FILLER_WORDS = {
    "yeah", "yes", "okay", "ok", "um", "uh", "hmm", "ah",
    "bye", "hi", "hello", "thanks", "nice", "work",
}

def clean_transcript(text: str) -> str:
    """Remove consecutive duplicate words and collapse filler-word runs."""
    if not text:
        return text

    # Step 1: collapse runs of the SAME word (case-insensitive), keep one copy.
    # e.g. "and and and" → "and", "bye bye bye" → "bye"
    text = re.sub(
        r'\b(\w+)(?:\s+\1)+\b',
        r'\1',
        text,
        flags=re.IGNORECASE,
    )

    # Step 2: remove isolated filler words that appear at the end of the sentence
    # after the main content, e.g. "…original. nice work nice work" → "…original."
    words = text.split()
    # Walk from the end and strip trailing filler runs
    while words and words[-1].lower().rstrip('.,!?') in _FILLER_WORDS:
        words.pop()

    # Step 3: strip leftover ellipsis / dots artefacts
    cleaned = " ".join(words).strip(" .,")
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
