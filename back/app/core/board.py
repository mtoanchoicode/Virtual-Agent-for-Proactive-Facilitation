"""Shared ranking board for the "Lost at Sea" exercise.

The server is the single source of truth for the card order. Clients send moves; the server applies
them in arrival order and broadcasts the full state.

The facilitator (LLM) deliberately never sees this data: nothing here is imported by llm_service
or included in any prompt. Moves are written to board_log.jsonl for later analysis only.
"""
import json
import os
import time
from typing import Dict, List, Optional, Set

from app.core.config import BASE_DIR
from app.services import scenario

_LOG_PATH = os.path.join(BASE_DIR, "board_log.jsonl")

# The simulator is a single-person test stand-in; it counts as agreeing whenever a real person agrees.
_AUTO_AGREE_NAMES = {"Simulator"}


class Board:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.items: List[dict] = list(scenario.BOARD_ITEMS)
        self.order: List[str] = [it["id"] for it in self.items]
        self.version: int = 0
        self.agreed: Set[str] = set()            # session ids that pressed "I agree"
        self.moving: Dict[str, str] = {}         # item id -> session id currently dragging it
        self._started_at: float = 0.0

    # ------------------------------------------------------------------ helpers
    def _label(self, item_id: str) -> str:
        return next((it["label"] for it in self.items if it["id"] == item_id), item_id)

    def _log(self, event: str, who: str, **data) -> None:
        if os.environ.get("ENABLE_FILE_LOGGING", "true").lower() != "true":
            return
        now = time.time()
        if not self._started_at:
            self._started_at = now
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + "Z",
            "t": round(now - self._started_at, 1),  # seconds since the first board event
            "event": event,
            "by": who,
            "version": self.version,
            **data,
        }
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[board] failed to write board_log.jsonl: {e}")

    def _ranking(self) -> List[dict]:
        return [{"rank": i + 1, "item": self._label(iid)} for i, iid in enumerate(self.order)]

    def _all_agreed(self, participants: Dict[str, "object"]) -> bool:
        if len(participants) < 2:
            return False
        real = [sid for sid, p in participants.items() if p.name not in _AUTO_AGREE_NAMES]
        if not real:
            return False
        return all(sid in self.agreed for sid in real)

    # ------------------------------------------------------------------ state
    def snapshot(self, participants: Dict[str, "object"]) -> dict:
        names = {sid: p.name for sid, p in participants.items()}
        return {
            "items": self.items,
            "order": self.order,
            "version": self.version,
            "agreed": [sid for sid in self.agreed if sid in names],
            "moving": {
                iid: {"sessionId": sid, "name": names.get(sid, "")}
                for iid, sid in self.moving.items() if sid in names
            },
            "allAgreed": self._all_agreed(participants),
        }

    # ------------------------------------------------------------------ actions
    def start_drag(self, session_id: str, who: str, item_id: str) -> bool:
        if item_id not in self.order:
            return False
        holder = self.moving.get(item_id)
        if holder and holder != session_id:
            return False  # someone else is already dragging this card
        self.moving[item_id] = session_id
        return True

    def end_drag(self, session_id: str, item_id: str) -> None:
        if self.moving.get(item_id) == session_id:
            del self.moving[item_id]

    def move(self, session_id: str, who: str, item_id: str, to_index: int,
             participants: Dict[str, "object"]) -> bool:
        if item_id not in self.order:
            return False
        holder = self.moving.get(item_id)
        if holder and holder != session_id:
            return False
        from_index = self.order.index(item_id)
        to_index = max(0, min(len(self.order) - 1, int(to_index)))
        self.moving.pop(item_id, None)
        if from_index == to_index:
            return True  # no change, but the lock is released
        self.order.pop(from_index)
        self.order.insert(to_index, item_id)
        self.version += 1
        self.agreed.clear()  # any change invalidates earlier agreement
        self._log("move", who, item=self._label(item_id), fromRank=from_index + 1, toRank=to_index + 1,
                  ranking=[r["item"] for r in self._ranking()])
        return True

    def set_agreed(self, session_id: str, who: str, agreed: bool,
                   participants: Dict[str, "object"]) -> None:
        if agreed:
            self.agreed.add(session_id)
        else:
            self.agreed.discard(session_id)
        self._log("agree" if agreed else "unagree", who)
        if agreed and self._all_agreed(participants):
            self._log("final", "all", ranking=self._ranking())

    def drop_session(self, session_id: str) -> None:
        """A participant left: release their drags and agreement."""
        self.agreed.discard(session_id)
        for iid in [i for i, s in self.moving.items() if s == session_id]:
            del self.moving[iid]
