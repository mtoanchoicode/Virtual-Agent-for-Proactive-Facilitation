"""Lost at Sea items and the US Coast Guard key.

The key lives ONLY here. It is never put into an agent prompt and never sent to the backend;
it is used after the session to score rankings.
"""
from typing import Dict, List

# Same ids and labels as back/app/services/scenario.py BOARD_ITEMS (checked at runtime against
# the board the server sends).
ITEMS: List[Dict[str, str]] = [
    {"id": "item-5", "label": "Case of army rations"},
    {"id": "item-1", "label": "Sextant"},
    {"id": "item-8", "label": "10 liter can of oil/petrol mixture"},
    {"id": "item-4", "label": "25 liter container of water"},
    {"id": "item-10", "label": "20 sq. ft. of opaque plastic sheeting"},
    {"id": "item-2", "label": "Shaving mirror"},
]
LABELS = [it["label"] for it in ITEMS]
ID_BY_LABEL = {it["label"]: it["id"] for it in ITEMS}
LABEL_BY_ID = {it["id"]: it["label"] for it in ITEMS}

# Reduced 6-item task: the Coast Guard ranks of these items, re-ranked 1..6 within the subset
# (original ranks: mirror 1, oil 2, water 3, rations 4, plastic 5, sextant 15).
EXPERT_RANK: Dict[str, int] = {
    "Shaving mirror": 1,
    "10 liter can of oil/petrol mixture": 2,
    "25 liter container of water": 3,
    "Case of army rations": 4,
    "20 sq. ft. of opaque plastic sheeting": 5,
    "Sextant": 6,
}
MAX_SCORE = 18  # fully reversed ranking of 6 items

# The original 15-item bands (25/32/45/55/70) do not apply. Rescaled to the 0-18 range.
BANDS = [
    (2, "Excellent"),
    (6, "Good"),
    (10, "Average"),
    (14, "Fair"),
]


def deviation(ranking: List[str]) -> int:
    """Sum over items of |rank in `ranking` - expert rank|. `ranking` lists labels, best first."""
    return sum(abs(i + 1 - EXPERT_RANK[label]) for i, label in enumerate(ranking))


def band(score: float) -> str:
    for upper, name in BANDS:
        if score <= upper:
            return name
    return "Poor"
