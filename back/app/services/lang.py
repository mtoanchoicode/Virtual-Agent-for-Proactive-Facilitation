"""Room-wide language setting ("en" or "vi").

English is the default and every English code path is unchanged. When set to "vi" the
facilitator speaks Vietnamese, speech-to-text is told to expect Vietnamese, and TTS uses a
Vietnamese voice.
"""

SUPPORTED = ("en", "vi")

_current = "en"

TTS_VOICES = {
    "en": "en-US-GuyNeural",
    "vi": "vi-VN-NamMinhNeural",
}

# Extra keywords (besides the English ones) that force a SUMMARIZE turn in Vietnamese.
SUMMARY_TRIGGERS_VI = ["tóm tắt", "tổng kết", "tóm lại", "tổng hợp lại"]

# Appended to the facilitator's system prompt in Vietnamese. The ACTION/TEXT labels and action
# names must stay English because the backend parses them.
VI_DIRECTIVE = (
    "LANGUAGE: The participants speak Vietnamese. Think and speak in Vietnamese. Write every spoken "
    "sentence (the TEXT: part, or the whole reply when no format is required) in natural, friendly "
    "spoken Vietnamese, addressing people by their names. Keep the labels 'ACTION:' and 'TEXT:' and the "
    "action names (NO_ACTION, DEEPEN, RESOLVE, NEXT_ITEM, CLARIFY, REDIRECT, ENCOURAGE, SUMMARIZE) in English "
    "exactly as specified. If a required fixed sentence is given in English, say its meaning in Vietnamese. "
    "Transcripts are Vietnamese speech-to-text and may contain errors; infer the intended item names."
)


def get() -> str:
    return _current


def set_lang(value: str) -> bool:
    global _current
    if value not in SUPPORTED:
        return False
    _current = value
    return True


def is_vi() -> bool:
    return _current == "vi"


def tts_voice() -> str:
    return TTS_VOICES[_current]
