"""Scenario configuration for the "Lost at Sea" ranking exercise.

Enabled with SCENARIO=lost_at_sea. When unset, the generic facilitator is used.
NOTE: the facilitator is deliberately NOT given the expert (Coast Guard) ranking.
"""
import os

SCENARIO = os.getenv("SCENARIO", "").strip().lower()
ENABLED = SCENARIO == "lost_at_sea"

TIME_LIMIT_SEC = int(os.getenv("SCENARIO_TIME_LIMIT_SEC", "300"))  # 5 minutes by default; adjustable at runtime
MIN_TIME_LIMIT_SEC = 60
MAX_TIME_LIMIT_SEC = 20 * 60
SILENCE_NUDGE_SEC = float(os.getenv("SCENARIO_SILENCE_NUDGE_SEC", "20"))

# Time checks are given at these fractions of the time limit.
CHECKPOINT_FRACTIONS = (0.5, 0.75, 0.92)


def checkpoints() -> list:
    """[(fraction, seconds_into_session)] for the current limit. A checkpoint closer than 10 s to the
    end is dropped (it would collide with the wrap-up in very short sessions)."""
    out = []
    for f in CHECKPOINT_FRACTIONS:
        sec = int(TIME_LIMIT_SEC * f)
        if TIME_LIMIT_SEC - sec >= 10:
            out.append((f, sec))
    return out


def nudge_sec() -> float:
    """Silence before a nudge. Shorter sessions get a quicker nudge (never above the configured value)."""
    return min(SILENCE_NUDGE_SEC, max(8.0, TIME_LIMIT_SEC / 6))

# Reduced 6-item version of Lost at Sea (the 5 top-ranked Coast Guard items + the sextant as a
# "navigation" trap). Ids are the ORIGINAL 15-item ids so the front end (emoji / Vietnamese labels) and
# SIM/simlab/scoring.py stay in sync. Order here = fixed starting order of the board (deliberately not
# the expert order).
_SUBSET = [
    ("item-5", "Case of army rations"),
    ("item-1", "Sextant"),
    ("item-8", "10 liter can of oil/petrol mixture"),
    ("item-4", "25 liter container of water"),
    ("item-10", "20 sq. ft. of opaque plastic sheeting"),
    ("item-2", "Shaving mirror"),
]
N_ITEMS = len(_SUBSET)
ITEMS = [label for _, label in _SUBSET]

# Cards for the shared ranking board: [{"id": "...", "label": "..."}], in the fixed starting order.
BOARD_ITEMS = [{"id": i, "label": label} for i, label in _SUBSET]

# Vocabulary hint for speech-to-text (helps with words like "sextant").
STT_HINT = (
    "Two crew members in a life raft in the South Pacific ranking survival items. Items: sextant "
    "(navigation instrument), shaving mirror, 25 liter container of water, "
    "case of army rations, oil petrol mixture, opaque plastic sheeting. Ranking numbers one to six."
)

def minutes_text() -> str:
    m = TIME_LIMIT_SEC // 60
    return f"{m} minute" if m == 1 else f"{m} minutes"


def task_brief() -> str:
    """Scenario and task only, with no facilitation guidance (used by Lite Mode)."""
    return (
    "SCENARIO: 'Lost at Sea'. Two participants are crew of a yacht that caught fire and is sinking in the "
    "South Pacific, about 1,000 miles from the nearest land. They are in a rubber life raft with oars. "
    f"Their pockets hold cigarettes, matches and five one-dollar bills. These {N_ITEMS} items survived:\n"
    + "; ".join(ITEMS)
    + ".\n"
    f"TASK: within {minutes_text()}, discuss and agree on ONE shared ranking of all {N_ITEMS} items, "
    f"1 = most important to survival, {N_ITEMS} = least important. Both must agree on every rank."
    )


def _build_brief() -> str:
    return (
    task_brief() + "\n"
    "YOUR ROLE: you are a neutral facilitator. You do NOT know the correct ranking and must never claim, "
    "imply or hint at one. If asked for the answer, say you don't have it and that it is up to them. "
    "Never rank items for them and never say whether an item is more or less important. Help the PAIR "
    "reason better: ask about priorities (what threatens survival first, and over what time span), "
    "surface disagreements, ask for the reasoning behind a pick, and keep them moving through all 6 items."
    )


SCENARIO_BRIEF = _build_brief()


def set_time_limit(sec: int) -> int:
    """Change the session length (clamped to 1-20 minutes) and rebuild everything derived from it."""
    global TIME_LIMIT_SEC, SCENARIO_BRIEF
    TIME_LIMIT_SEC = max(MIN_TIME_LIMIT_SEC, min(MAX_TIME_LIMIT_SEC, int(sec)))
    SCENARIO_BRIEF = _build_brief()
    return TIME_LIMIT_SEC


# ---------------------------------------------------------------------------------------------
# Vietnamese (used only when the room language is "vi"; the English values above are untouched)
# ---------------------------------------------------------------------------------------------
ITEMS_VI = [
    "Một thùng lương khô quân đội",
    "Kính lục phân (sextant)",
    "Can hỗn hợp dầu/xăng 10 lít",
    "Thùng nước 25 lít",
    "Tấm nhựa đục 20 feet vuông",
    "Gương cạo râu",
]

STT_HINT_VI = (
    "Hai thuyền viên trên bè cứu sinh ở Nam Thái Bình Dương đang xếp hạng các vật dụng sinh tồn: "
    "kính lục phân, gương cạo râu, thùng nước 25 lít, lương khô quân đội, "
    "hỗn hợp dầu xăng, tấm nhựa đục. Xếp hạng từ một đến sáu."
)

SCENARIO_BRIEF_VI = (
    "KỊCH BẢN (tiếng Việt): 'Lạc giữa biển'. Hai người tham gia là thuyền viên của một du thuyền bị cháy và đang chìm "
    "ở Nam Thái Bình Dương. Họ đang ở trên một chiếc bè cứu sinh cao su có mái chèo. Danh sách 6 vật dụng còn lại:\n"
    + "; ".join(ITEMS_VI)
    + ". Khi nói chuyện hãy dùng tên tiếng Việt của các vật dụng này."
)
