"""Shared ranking board for the "Lost at Sea" exercise.

Model: every card starts in a POOL of undecided items. Participants drag a card into one of the fixed
rank SLOTS (1 = most important). Dropping onto an occupied slot swaps the two cards when the dragged
card came from another slot, and sends the occupant back to the pool when the dragged card came from
the pool. A card can be dragged back to the pool at any time. "I agree" only counts once all slots are
filled.

The server is the single source of truth. Clients send actions; the server applies them in arrival order
and broadcasts the full state to everyone, so both participants see every change live.

The facilitator (Full Mode only) receives a short read-only text view of the board via
facilitator_view(): which cards are placed and which are still in the pool. It never receives the
expert ranking (that lives only in session_report.py / SIM scoring). Moves are also written to
board_log.jsonl for later analysis.
"""
import json
import os
import time
from typing import Dict, List, Optional, Set

from app.core.config import BASE_DIR
from app.services import scenario

_LOG_PATH = os.path.join(BASE_DIR, "board_log.jsonl")
BOARD_VERSION = "pool-slots-v2"  # recorded in logs / reports so old (fixed-order) sessions can be told apart

# The simulator is a single-person test stand-in; it counts as agreeing whenever a real person agrees.
_AUTO_AGREE_NAMES = {"Simulator"}


class Board:
    def __init__(self) -> None:
        self.mode: str = "full"  # facilitator mode, recorded with every logged event
        self.reset()

    def reset(self) -> None:
        self.items: List[dict] = list(scenario.BOARD_ITEMS)
        self.slots: List[Optional[str]] = [None] * len(self.items)  # slot i = rank i+1
        self.pool: List[str] = [it["id"] for it in self.items]      # undecided cards, fixed display order
        self.version: int = 0
        self.agreed: Set[str] = set()            # session ids that pressed "I agree"
        self.moving: Dict[str, str] = {}         # item id -> session id currently dragging it
        self._started_at: float = 0.0
        self.events: List[dict] = []             # in-memory copy of the logged events (for the session report)

    # ------------------------------------------------------------------ helpers
    def _label(self, item_id: str) -> str:
        return next((it["label"] for it in self.items if it["id"] == item_id), item_id)

    def _log(self, event: str, who: str, **data) -> None:
        now = time.time()
        if not self._started_at:
            self._started_at = now
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + "Z",
            "t": round(now - self._started_at, 1),  # seconds since the first board event
            "event": event,
            "by": who,
            "version": self.version,
            "mode": self.mode,
            "board": BOARD_VERSION,
            **data,
        }
        self.events.append({**entry, "at": now})
        if os.environ.get("ENABLE_FILE_LOGGING", "true").lower() != "true":
            return
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[board] failed to write board_log.jsonl: {e}")

    def _ranking(self) -> List[dict]:
        return [{"rank": i + 1, "item": self._label(iid) if iid else None} for i, iid in enumerate(self.slots)]

    def _pool_in_display_order(self) -> List[str]:
        """Keep the pool in the original item order so cards don't jump around when they come back."""
        order = [it["id"] for it in self.items]
        return sorted(self.pool, key=order.index)

    def is_complete(self) -> bool:
        return all(self.slots)

    def _all_agreed(self, participants: Dict[str, "object"]) -> bool:
        if len(participants) < 2 or not self.is_complete():
            return False
        real = [sid for sid, p in participants.items() if p.name not in _AUTO_AGREE_NAMES]
        if not real:
            return False
        return all(sid in self.agreed for sid in real)

    def _changed(self) -> None:
        self.version += 1
        self.agreed.clear()  # any change invalidates earlier agreement

    # ------------------------------------------------------------------ state
    def snapshot(self, participants: Dict[str, "object"]) -> dict:
        names = {sid: p.name for sid, p in participants.items()}
        return {
            "items": self.items,
            "slots": list(self.slots),
            "pool": list(self.pool),
            "complete": self.is_complete(),
            "version": self.version,
            "agreed": [sid for sid in self.agreed if sid in names],
            "moving": {
                iid: {"sessionId": sid, "name": names.get(sid, "")}
                for iid, sid in self.moving.items() if sid in names
            },
            "allAgreed": self._all_agreed(participants),
        }

    def facilitator_view(self, participants: Dict[str, "object"]) -> str:
        """Read-only board summary for the facilitator prompt (Full Mode)."""
        placed = [f"{i + 1}. {self._label(iid)}" for i, iid in enumerate(self.slots) if iid]
        empty = [str(i + 1) for i, iid in enumerate(self.slots) if not iid]
        pool = [self._label(iid) for iid in self.pool]
        agreed = [participants[sid].name for sid in self.agreed if sid in participants]
        lines = [
            "[BOARD] Shared ranking board (background awareness only; see the board rules):",
            "- Placed: " + ("; ".join(placed) if placed else "none yet"),
            "- Empty ranks: " + (", ".join(empty) if empty else "none"),
            "- Not placed yet (in the pool): " + (", ".join(pool) if pool else "none, all cards are placed"),
            "- Pressed 'I agree': " + (", ".join(agreed) if agreed else "nobody"),
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ actions
    def start_drag(self, session_id: str, who: str, item_id: str) -> bool:
        if item_id not in self.pool and item_id not in self.slots:
            return False
        holder = self.moving.get(item_id)
        if holder and holder != session_id:
            return False  # someone else is already dragging this card
        self.moving[item_id] = session_id
        return True

    def end_drag(self, session_id: str, item_id: str) -> None:
        if self.moving.get(item_id) == session_id:
            del self.moving[item_id]

    def _can_touch(self, session_id: str, item_id: Optional[str]) -> bool:
        holder = self.moving.get(item_id) if item_id else None
        return not holder or holder == session_id

    def place(self, session_id: str, who: str, item_id: str, slot_index: int) -> bool:
        """Put a card into rank slot `slot_index` (0-based), from the pool or from another slot."""
        in_pool = item_id in self.pool
        if not in_pool and item_id not in self.slots:
            return False
        if not self._can_touch(session_id, item_id):
            return False
        slot_index = max(0, min(len(self.slots) - 1, int(slot_index)))
        occupant = self.slots[slot_index]
        if occupant and occupant != item_id and not self._can_touch(session_id, occupant):
            return False  # the partner is dragging the card that sits in the target slot
        self.moving.pop(item_id, None)

        from_rank = None if in_pool else self.slots.index(item_id) + 1
        if occupant == item_id:
            return True  # dropped where it already was; lock released

        displaced = None
        if in_pool:
            self.pool.remove(item_id)
            if occupant:  # the occupant goes back to the pool
                self.pool.append(occupant)
                self.pool = self._pool_in_display_order()
                displaced = {"item": self._label(occupant), "to": "pool"}
        else:
            self.slots[from_rank - 1] = occupant  # swap (occupant may be None = simple move)
            if occupant:
                displaced = {"item": self._label(occupant), "to": f"rank {from_rank}"}
        self.slots[slot_index] = item_id

        self._changed()
        self._log("place", who, item=self._label(item_id), fromRank=from_rank, toRank=slot_index + 1,
                  displaced=displaced, ranking=[r["item"] for r in self._ranking()])
        return True

    def unplace(self, session_id: str, who: str, item_id: str) -> bool:
        """Send a placed card back to the pool."""
        if item_id not in self.slots or not self._can_touch(session_id, item_id):
            return False
        self.moving.pop(item_id, None)
        from_rank = self.slots.index(item_id) + 1
        self.slots[from_rank - 1] = None
        self.pool.append(item_id)
        self.pool = self._pool_in_display_order()
        self._changed()
        self._log("unplace", who, item=self._label(item_id), fromRank=from_rank,
                  ranking=[r["item"] for r in self._ranking()])
        return True

    def set_agreed(self, session_id: str, who: str, agreed: bool,
                   participants: Dict[str, "object"]) -> None:
        if agreed:
            if not self.is_complete():
                return  # can't agree while cards are still in the pool
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
