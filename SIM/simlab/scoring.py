"""Lost at Sea items and the US Coast Guard key.

The key lives ONLY here. It is never put into an agent prompt and never sent to the backend;
it is used after the session to score rankings.
"""
from typing import Dict, List

# Same ids and labels as back/app/services/scenario.py BOARD_ITEMS (checked at runtime against
# the board the server sends).
ITEMS: List[Dict[str, str]] = [
    {"id": "item-1", "label": "Sextant"},
    {"id": "item-2", "label": "Shaving mirror"},
    {"id": "item-3", "label": "Mosquito netting"},
    {"id": "item-4", "label": "25 liter container of water"},
    {"id": "item-5", "label": "Case of army rations"},
    {"id": "item-6", "label": "Maps of the Pacific Ocean"},
    {"id": "item-7", "label": "Floating seat cushion"},
    {"id": "item-8", "label": "10 liter can of oil/petrol mixture"},
    {"id": "item-9", "label": "Small transistor radio"},
    {"id": "item-10", "label": "20 sq. ft. of opaque plastic sheeting"},
    {"id": "item-11", "label": "Can of shark repellent"},
    {"id": "item-12", "label": "One bottle of rubbing alcohol"},
    {"id": "item-13", "label": "15 ft. of nylon rope"},
    {"id": "item-14", "label": "2 boxes of chocolate bars"},
    {"id": "item-15", "label": "Ocean fishing kit and pole"},
]
LABELS = [it["label"] for it in ITEMS]
ID_BY_LABEL = {it["label"]: it["id"] for it in ITEMS}
LABEL_BY_ID = {it["id"]: it["label"] for it in ITEMS}

EXPERT_RANK: Dict[str, int] = {
    "Sextant": 15,
    "Shaving mirror": 1,
    "Mosquito netting": 14,
    "25 liter container of water": 3,
    "Case of army rations": 4,
    "Maps of the Pacific Ocean": 13,
    "Floating seat cushion": 9,
    "10 liter can of oil/petrol mixture": 2,
    "Small transistor radio": 12,
    "20 sq. ft. of opaque plastic sheeting": 5,
    "Can of shark repellent": 10,
    "One bottle of rubbing alcohol": 11,
    "15 ft. of nylon rope": 8,
    "2 boxes of chocolate bars": 6,
    "Ocean fishing kit and pole": 7,
}

BANDS = [
    (25, "Excellent"),
    (32, "Good"),
    (45, "Average"),
    (55, "Fair"),
    (70, "Poor"),
]


def deviation(ranking: List[str]) -> int:
    """Sum over items of |rank in `ranking` - expert rank|. `ranking` lists labels, best first."""
    return sum(abs(i + 1 - EXPERT_RANK[label]) for i, label in enumerate(ranking))


def band(score: float) -> str:
    for upper, name in BANDS:
        if score <= upper:
            return name
    return "Very Poor"
