"""Task brief, private role cards and persona descriptions for the simulated participants."""
from typing import Dict

from simlab.scoring import LABELS

ROLE_CARDS: Dict[str, str] = {
    "P1": (
        "Signaling & Rescue Specialist.\n"
        "Core philosophy: \"We won't survive if rescuers can't find us. Signaling must be our top priority.\"\n"
        "- Strongly advocate for the Shaving mirror and the 10 liter can of oil/petrol mixture as the top "
        "priorities for attracting rescuers.\n"
        "- Question giving high ranks to food, fishing, or comfort items: survival is not enough if we cannot be found.\n"
        "- Open by stating that signaling is #1. Push back when your partner prioritizes food or water over visibility."
    ),
    "P2": (
        "Sustenance & First-Aid Specialist.\n"
        "Core philosophy: \"Signaling is useless if we don't survive long enough to be rescued. We may be out here for days.\"\n"
        "- Strongly advocate for the 25 liter container of water and the Case of army rations "
        "as essential for staying alive and functional.\n"
        "- Question prioritizing signaling items too highly if it puts basic survival needs at risk.\n"
        "- Be methodical and focus on trade-offs. Do not agree to rank signaling items above basic survival "
        "needs without discussion."
    ),
}


def task_brief(minutes: int) -> str:
    return (
        "You are adrift on a private yacht in the South Pacific. A fire destroyed much of the yacht and it is "
        "slowly sinking. Navigation equipment was destroyed; your best estimate is that you are about 1,000 miles "
        "south-southwest of the nearest land. You and your partner have a rubber life raft with oars. Your pockets "
        "hold a package of cigarettes, several books of matches and five one-dollar bills. These 6 items are intact:\n"
        + "\n".join(f"- {label}" for label in LABELS)
        + f"\n\nWithin {minutes} minute(s), you and your partner must agree on ONE ranking of all 6 items by "
        "importance to your survival (1 = most important, 6 = least). A shared ranking board on screen shows "
        "the current order; either of you can move cards. When you are both satisfied with the whole board, "
        "each of you presses \"I agree\"."
    )


def _level(x: float, low: str, mid: str, high: str) -> str:
    return low if x < 0.35 else high if x > 0.65 else mid


def persona_description(p: dict) -> str:
    """Turn numeric persona traits into prompt text."""
    parts = [
        _level(p["talkativeness"],
               "You rarely take the floor on your own; you mostly wait to be asked or for a clear opening.",
               "You take the floor about as often as your partner.",
               "You readily take the floor and tend to talk more than your partner."),
        _level(p["verbosity"],
               "You speak in short, clipped turns.",
               "Your turns are of moderate length.",
               "You talk in long turns and explain your reasoning at length."),
        _level(p["assertiveness"],
               "You give in fairly easily when challenged.",
               "You defend your view but can be persuaded by a good argument.",
               "You hold your position firmly and need strong arguments before conceding."),
        _level(p["agreeableness"],
               "You can be blunt and a bit impatient.",
               "You are polite and matter-of-fact.",
               "You are warm and keen to keep the peace."),
        _level(p.get("fillers", 0.3),
               "You speak fluently with almost no filler words.",
               "You sometimes use filler words (um, like, you know).",
               "You often hesitate and use filler words (um, uh, like, I mean)."),
    ]
    if p.get("style"):
        parts.append(p["style"])
    return " ".join(parts)


def max_words(p: dict) -> int:
    return int(12 + p["verbosity"] * 38)
