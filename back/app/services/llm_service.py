from typing import List
from app.services.audio_service import generate_audio
from app.utils.helpers import audio_file_to_base64

# Max number of history entries kept in memory.
# Each entry is one user-turn or one assistant-turn.
# 50 entries ≈ the last ~10 minutes of a typical meeting.
MAX_HISTORY_LEN = 50
MAX_TRANSCRIPT_LOG_LEN = 200

class ConversationManager:
    def __init__(self):
        self.history: List[dict] = []
        self.transcript_log: List[dict] = []

    def _trim(self):
        """Keep history and transcript_log within their size limits."""
        if len(self.history) > MAX_HISTORY_LEN:
            self.history = self.history[-MAX_HISTORY_LEN:]
        if len(self.transcript_log) > MAX_TRANSCRIPT_LOG_LEN:
            self.transcript_log = self.transcript_log[-MAX_TRANSCRIPT_LOG_LEN:]

    def add_entry(self, speaker: str, text: str):
        self.transcript_log.append({"speaker": speaker, "text": text})
        self.history.append({"role": "user", "content": f"{speaker} said: {text}"})
        self._trim()

    def add_turn(self, transcripts: List[dict]):
        if not transcripts:
            return
        
        for t in transcripts:
            self.transcript_log.append(t)
            
        combined_text = "\n".join([f"{t['speaker']} said: {t['text']}" for t in transcripts])
        self.history.append({"role": "user", "content": combined_text})
        self._trim()

    def add_ai_response(self, action: str, text: str):
        self.history.append({"role": "assistant", "content": f"[Action taken: {action}] Yacine said: {text}"})
        self._trim()

    def get_lightweight_polling_prompt(self, ongoing_text: str = None, metadata: str = None) -> List[dict]:
        system_content = """
You are Yacine, a lightweight AI meeting monitor.
Your ONLY job is to decide if the main AI facilitator should intervene right now.
Look at the ongoing transcript and the metadata.
If the conversation is flowing well, or someone is actively speaking their mind, reply NO.
If there is an awkward silence (e.g., users are stuck thinking and no one has spoken for over 8-10 seconds), an unresolved question, or someone is completely dominating while others are left out, reply YES.

Reply ONLY with the word YES or NO.
"""
        if metadata:
            system_content += f"\n\n{metadata}\n"

        # Use the last 10 entries — history is already trimmed globally,
        # and 10 entries give the lightweight model enough context.
        recent_history = self.history[-10:]

        messages = [{"role": "system", "content": system_content.strip()}] + recent_history
        if ongoing_text:
            messages.append({"role": "user", "content": f"[ONGOING TURN] {ongoing_text}"})
        return messages

    def get_facilitation_prompt(self, ongoing_text: str = None, metadata: str = None) -> List[dict]:
        system_content = """
You are Yacine, an AI meeting facilitator. 
Your core philosophy is "less is more". People dislike being interrupted by AI, so you MUST NOT interrupt a conversation that is flowing naturally. ONLY intervene if there is a glaring silence, a direct conflict, or someone is completely dominating.

FIRST, think silently about the conversation state using these questions:
- Is the conversation naturally flowing? (If yes, prefer NO_ACTION)
- Is someone dominating the conversation while others are left out for a long time?
- Is there a conflict, confusion, or unresolved question?
- Is the discussion staying surface-level and needs a push?

Then decide ONE of these actions. Your default and preferred choice should ALWAYS be NO_ACTION unless an intervention is strictly necessary:
- NO_ACTION: (DEFAULT) The conversation is flowing well and no intervention is needed.
- ENCOURAGE: Invite a quiet participant to share.
- DEEPEN: Ask a follow-up to go deeper on an idea.
- SUMMARIZE: Briefly recap and propose a next step.
- MEDIATE: Acknowledge tension and redirect constructively.

If you choose NO_ACTION, reply with:
ACTION: NO_ACTION
TEXT: 

Otherwise, facilitate using EXTREMELY CONCISE, punchy sentences. You MUST keep it to 1 sentence maximum and under 15 words. Speak naturally but get straight to the point. Do not repeat yourself.

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
