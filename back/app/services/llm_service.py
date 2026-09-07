import base64
from typing import List
from app.services.audio_service import generate_audio_bytes

# Max number of history entries kept in memory.
# Each entry is one user-turn or one assistant-turn.
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

    def _append_to_debug_log(self, entry: dict):
        import os
        if os.environ.get("ENABLE_FILE_LOGGING", "true").lower() != "true":
            return
        try:
            from app.core.config import BASE_DIR
            log_path = os.path.join(BASE_DIR, "history_debug.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{entry['role'].upper()}] {entry['content']}\n")
        except Exception as e:
            print(f"Error writing to history debug log: {e}")

    def clear(self):
        """Clear the history and transcripts when the session ends."""
        self.history = []
        self.transcript_log = []

    def add_entry(self, speaker: str, text: str):
        self.transcript_log.append({"speaker": speaker, "text": text})
        entry = {"role": "user", "content": f"{speaker} said: {text}"}
        self.history.append(entry)
        self._append_to_debug_log(entry)
        self._trim()

    def add_turn(self, transcripts: List[dict]):
        if not transcripts:
            return
        for t in transcripts:
            self.transcript_log.append(t)
        combined_text = "\n".join([f"{t['speaker']} said: {t['text']}" for t in transcripts])
        entry = {"role": "user", "content": combined_text}
        self.history.append(entry)
        self._append_to_debug_log(entry)
        self._trim()

    def add_ai_response(self, action: str, text: str):
        if action == "NO_ACTION" or text == "(remains silent)":
            content = f"ACTION: {action}\nTEXT:"
        else:
            content = f"ACTION: {action}\nTEXT: {text}"
            
        entry = {"role": "assistant", "content": content}
        self.history.append(entry)
        self._append_to_debug_log(entry)
        self._trim()

    def add_lite_ai_response(self, text: str):
        """Store a plain-text assistant response for Lite Mode (no ACTION/TEXT format)."""
        entry = {"role": "assistant", "content": text}
        self.history.append(entry)
        self._append_to_debug_log(entry)
        self._trim()

    def get_facilitation_prompt(self, metadata: str = None, force_encourage_target: str = None, force_summarize: bool = False) -> List[dict]:
        """
        Build the facilitation prompt.

        Simple pipeline: user speaks → silence → this runs → AI speaks or skips.
        NO_ACTION is always available so the AI won't awkwardly interrupt.
        """
        if force_summarize:
            system_content = (
                "You are Yacine, an AI meeting facilitator. "
                "The users have requested a summary of the meeting.\n\n"
                "You MUST choose the SUMMARIZE action.\n"
                "Briefly recap the key points discussed so far and propose a next step.\n"
                "One sentence, under 50 words.\n\n"
                "Reply ONLY in this exact format:\n"
                "ACTION: SUMMARIZE\n"
                "TEXT: <your spoken sentence>"
            )
        elif force_encourage_target:
            system_content = (
                "You are Yacine, an AI meeting facilitator. "
                f"{force_encourage_target} has been unusually quiet and needs to be brought into the conversation.\n\n"
                "You MUST choose the ENCOURAGE action.\n"
                f"Ask {force_encourage_target} a direct question to bring them into the conversation.\n"
                "One sentence, under 15 words.\n\n"
                "Reply ONLY in this exact format:\n"
                "ACTION: ENCOURAGE\n"
                "TEXT: <your spoken sentence>"
            )
        else:
            action_menu = (
                "- NO_ACTION: The default choice. Use this if the conversation is flowing, users are answering each other, or if a user just gave a simple agreement (e.g., 'yeah', 'ok').\n"
                "- DEEPEN: Use this ONLY if the conversation has stalled, an answer was extremely vague, and you need to push the idea further with a focused follow-up."
            )

            system_content = (
                "You are Yacine, an AI meeting facilitator. "
                "After each user turn, decide whether to speak or stay quiet.\n\n"
                f"Choose ONE action:\n{action_menu}\n\n"
                "Decision guide and Examples:\n"
                "- User A asks User B a question -> NO_ACTION\n"
                "- User says 'Yeah I agree.' -> NO_ACTION\n"
                "- User explains a complex idea in depth -> NO_ACTION\n"
                "- User says 'I don't know what to do next.' and silence follows -> DEEPEN\n"
                "- User gives a vague 3-word answer that stalls the meeting -> DEEPEN\n\n"
                "One sentence, under 15 words. Never repeat a question you already asked.\n\n"
                "Reply ONLY in this exact format:\n"
                "ACTION: <ACTION>\n"
                "TEXT: <your spoken sentence>"
            )

            if metadata:
                system_content += f"\n\n{metadata}"

        messages = [{"role": "system", "content": system_content}] + self.history[-14:]
        return messages

    def get_lite_prompt(self) -> List[dict]:
        """
        Build a simple, free-form facilitation prompt for Lite Mode.
        No action structure — the LLM speaks naturally every turn.
        Strips any ACTION:/TEXT: formatting from history so the LLM
        doesn't mimic the Full Mode format.
        """
        system_content = (
            "You are Yacine, an AI meeting facilitator. "
            "Your job is to keep the conversation flowing naturally and productively. "
            "Listen to what the participants say and respond with a short, helpful facilitation comment. "
            "Be concise — one or two sentences at most. "
            "Speak in a warm, encouraging tone. "
            "Do NOT use any special formatting or labels. Just speak naturally."
        )

        # Clean assistant history entries: strip Full Mode ACTION:/TEXT: formatting
        clean_history = []
        for entry in self.history[-14:]:
            if entry["role"] == "assistant":
                content = entry["content"]
                # Remove "ACTION: SOMETHING\nTEXT: " prefix if present
                import re
                content = re.sub(r"(?i)ACTION:\s*\S+\s*\n?TEXT:\s*", "", content).strip()
                # Skip if the assistant chose NO_ACTION (empty after stripping)
                if not content:
                    continue
                clean_history.append({"role": "assistant", "content": content})
            else:
                clean_history.append(entry)

        return [{"role": "system", "content": system_content}] + clean_history


shared_conv = ConversationManager()


async def process_message(i: int, message: dict) -> dict:
    print(f"[llm_service] process_message {i} start")
    print(f"[llm_service] generating audio for message {i}...")
    audio_bytes = await generate_audio_bytes(message["text"])
    message["audio"] = base64.b64encode(audio_bytes).decode("utf-8")
    print(f"[llm_service] process_message {i} done")
    return message
