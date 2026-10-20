import base64
from typing import List
from app.services.audio_service import generate_audio_bytes
from app.services import scenario

# Max number of history entries kept in memory.
# Each entry is one user-turn or one assistant-turn.
# The scenario needs the whole session (which items are ranked), so keep far more.
MAX_HISTORY_LEN = 300 if scenario.ENABLED else 50
# How many recent entries are sent to the LLM.
PROMPT_HISTORY_LEN = 300 if scenario.ENABLED else 14

SCENARIO_ACTION_MENU = (
    "- NO_ACTION: The default. Use it when the pair is exchanging ideas, giving reasons, answering each other, "
    "or making a quick agreement.\n"
    "- DEEPEN: Someone named a ranking or opinion without any reasoning, or gave a vague answer. "
    "Ask for the reason behind it.\n"
    "- RESOLVE: They disagree on an item and are repeating positions, or are stuck. Ask each one what "
    "survival need their pick serves, or propose a way to compare, without choosing for them.\n"
    "- NEXT_ITEM: An item has been agreed, or they have dwelled on one item too long while others are unranked. "
    "Name one or two items not yet ranked and invite them to move on.\n"
    "- CLARIFY: A transcript looks garbled or mishears an item name (e.g. 'sex tent' for sextant). "
    "Confirm which of the 15 items they mean.\n"
    "- REDIRECT: They ask you for the answer, or drift off task. Say you don't have the answer and "
    "bring them back to the ranking."
)


def _scenario_context() -> str:
    return scenario.SCENARIO_BRIEF if scenario.ENABLED else ""
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
        elif scenario.ENABLED:
            system_content = (
                "You are Yacine, an AI meeting facilitator.\n\n"
                f"{scenario.SCENARIO_BRIEF}\n\n"
                "Track from the conversation which items have an AGREED rank (both said yes) and which are still open. "
                "Use the [PROGRESS] metadata for the clock.\n\n"
                "After each user turn, decide whether to speak or stay quiet. Speak only when it clearly helps; "
                "silence is better than interrupting a productive exchange.\n\n"
                f"Choose ONE action:\n{SCENARIO_ACTION_MENU}\n\n"
                "Decision guide:\n"
                "- Partner asks partner a question -> NO_ACTION\n"
                "- 'Yeah, agree, water first.' -> NO_ACTION\n"
                "- 'Maybe the radio?' 'Hmm, I guess.' -> DEEPEN\n"
                "- 'Mirror is number one!' 'No, water is number one!' -> RESOLVE\n"
                "- 'Ok cushion is nine.' 'Fine.' with many items unranked -> NEXT_ITEM\n"
                "- 'Just tell us the right order.' -> REDIRECT\n\n"
                "Rules: one sentence, under 20 words, one question at a time, never repeat a question you already asked, "
                "never state which item matters more, never mention rankings you were not told.\n\n"
                "Reply ONLY in this exact format:\n"
                "ACTION: <ACTION>\n"
                "TEXT: <your spoken sentence>"
            )
            if metadata:
                system_content += f"\n\n{metadata}"
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

        if scenario.ENABLED and (force_summarize or force_encourage_target):
            system_content = f"{scenario.SCENARIO_BRIEF}\n\n{system_content}"

        messages = [{"role": "system", "content": system_content}] + self.history[-PROMPT_HISTORY_LEN:]
        return messages

    def get_proactive_prompt(self, kind: str, elapsed_sec: float) -> List[dict]:
        """Prompt for facilitator-initiated speech that is not triggered by a user turn.

        kind: OPEN (kickoff), NUDGE (both quiet), TIME_CHECK, WRAP_UP.
        """
        remaining_min = max(1, round((scenario.TIME_LIMIT_SEC - elapsed_sec) / 60))
        instructions = {
            "OPEN": (
                "The session is starting. Warmly welcome both participants, say in one or two short sentences that "
                f"they have {scenario.TIME_LIMIT_SEC // 60} minutes to agree together on one ranking of the 15 items, "
                "and invite them to start with whichever item feels most important."
            ),
            "NUDGE": (
                "Both participants have gone quiet. Gently break the silence with exactly ONE short, easy question "
                "(not two) that gets them talking, such as asking either of them to say which item they feel is "
                "next and why. Do not suggest what is important and do not repeat a question you already asked."
            ),
            "TIME_CHECK": (
                f"Give a time check. Start your sentence with 'About {remaining_min} minutes left.' Then, from the "
                "conversation, say how many of the 15 items still have no agreed rank and encourage a steady pace. "
                "Do not ask a question."
            ),
            "WRAP_UP": (
                "Time is up. Start with 'Time is up.' Then say you will read back what they agreed, list the ranks "
                "agreed so far in order from the conversation, name the items still unranked, and ask them to settle "
                "those right now. Do not add new opinions."
            ),
        }[kind]
        system_content = (
            "You are Yacine, an AI meeting facilitator.\n\n"
            f"{_scenario_context()}\n\n"
            f"{instructions}\n"
            "Speak naturally in at most two short sentences (under 35 words). Reply with the spoken text only."
        )
        return [{"role": "system", "content": system_content}] + self.history[-PROMPT_HISTORY_LEN:]

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
