"""Scenario configuration for the "Lost at Sea" ranking exercise.

Enabled with SCENARIO=lost_at_sea. When unset, the generic facilitator is used.
NOTE: the facilitator is deliberately NOT given the expert (Coast Guard) ranking.
"""
import os

SCENARIO = os.getenv("SCENARIO", "").strip().lower()
ENABLED = SCENARIO == "lost_at_sea"

TIME_LIMIT_SEC = int(os.getenv("SCENARIO_TIME_LIMIT_SEC", "720"))  # 12 minutes
# Seconds into the session at which the facilitator gives a time check.
TIME_CHECKPOINTS_SEC = [int(TIME_LIMIT_SEC * f) for f in (0.5, 0.75, 0.92)]
SILENCE_NUDGE_SEC = float(os.getenv("SCENARIO_SILENCE_NUDGE_SEC", "20"))

ITEMS = [
    "Sextant",
    "Shaving mirror",
    "Mosquito netting",
    "25 liter container of water",
    "Case of army rations",
    "Maps of the Pacific Ocean",
    "Floating seat cushion",
    "10 liter can of oil/petrol mixture",
    "Small transistor radio",
    "20 sq. ft. of opaque plastic sheeting",
    "Can of shark repellent",
    "One bottle of rubbing alcohol",
    "15 ft. of nylon rope",
    "2 boxes of chocolate bars",
    "Ocean fishing kit and pole",
]

# Vocabulary hint for speech-to-text (helps with words like "sextant").
STT_HINT = (
    "Lost at Sea ranking. Items: sextant, shaving mirror, mosquito netting, water container, "
    "army rations, maps of the Pacific, floating seat cushion, oil petrol mixture, transistor radio, "
    "plastic sheeting, shark repellent, rubbing alcohol, nylon rope, chocolate bars, fishing kit."
)

SCENARIO_BRIEF = (
    "SCENARIO: 'Lost at Sea'. Two participants are crew of a yacht that caught fire and is sinking in the "
    "South Pacific, about 1,000 miles from the nearest land. They are in a rubber life raft with oars. "
    "Their pockets hold cigarettes, matches and five one-dollar bills. These 15 items survived:\n"
    + "; ".join(ITEMS)
    + ".\n"
    f"TASK: within {TIME_LIMIT_SEC // 60} minutes, discuss and agree on ONE shared ranking of all 15 items, "
    "1 = most important to survival, 15 = least important. Both must agree on every rank.\n"
    "YOUR ROLE: you are a neutral facilitator. You do NOT know the correct ranking and must never claim, "
    "imply or hint at one. If asked for the answer, say you don't have it and that it is up to them. "
    "Never rank items for them and never say whether an item is more or less important. Help the PAIR "
    "reason better: ask about priorities (what threatens survival first, and over what time span), "
    "surface disagreements, ask for the reasoning behind a pick, and keep them moving through all 15 items."
)
