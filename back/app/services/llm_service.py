from typing import List
from app.services.audio_service import generate_audio
from app.utils.helpers import audio_file_to_base64

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

    def get_lightweight_polling_prompt(self, ongoing_text: str = None, metadata: str = None) -> List[dict]:
        system_content = """
You are Yacine, a lightweight AI meeting monitor.
Your ONLY job is to decide if the main AI facilitator should intervene right now.
Look at the ongoing transcript and the metadata.
If the conversation is flowing well, or someone is actively speaking their mind, reply NO.
If there is an awkward silence (e.g., users are stuck thinking), an unresolved question, or someone is completely dominating while others are left out, reply YES.

Reply ONLY with the word YES or NO.
"""
        if metadata:
            system_content += f"\n\n{metadata}\n"

        start_idx = 0
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i]["role"] == "assistant":
                start_idx = i
                break
        
        recent_history = self.history[start_idx:]
        if len(recent_history) > 10:
            recent_history = recent_history[-10:]

        messages = [{"role": "system", "content": system_content.strip()}] + recent_history
        if ongoing_text:
            messages.append({"role": "user", "content": f"[ONGOING TURN] {ongoing_text}"})
        return messages

    def get_facilitation_prompt(self, ongoing_text: str = None, metadata: str = None) -> List[dict]:
        system_content = """
You are Yacine, an AI meeting facilitator. 
FIRST, think silently about the conversation state using these questions:
- Who has been speaking most? Is anyone left out?
- Is the discussion going deep or staying surface-level?
- Is there a conflict, confusion, or unresolved question?

Then decide ONE of these actions:
- ENCOURAGE: Invite a quiet participant to share
- DEEPEN: Ask a follow-up to go deeper on an idea
- SUMMARIZE: Briefly recap and propose a next step
- MEDIATE: Acknowledge tension and redirect constructively

Facilitate in short for me only (yacine) no need to talk for too long

Reply ONLY with a plain text string exactly in this format:
ACTION: <ACTION>
TEXT: <your exact spoken message>
"""
        if metadata:
            system_content += f"\n\n{metadata}\n"

        messages = [{"role": "system", "content": system_content.strip()}] + self.history[-10:]
        if ongoing_text:
            messages.append({"role": "user", "content": f"[ONGOING TURN] {ongoing_text}"})
        return messages

shared_conv = ConversationManager()

async def process_message(i: int, message: dict) -> dict:
    print(f"[llm_service] process_message {i} start")
    audio_path = f"audios/message_{i}.mp3"
    print(f"[llm_service] generating audio for message {i}...")
    await generate_audio(message["text"], audio_path)
    message["audio"] = await audio_file_to_base64(audio_path)
    print(f"[llm_service] process_message {i} done")
    return message
