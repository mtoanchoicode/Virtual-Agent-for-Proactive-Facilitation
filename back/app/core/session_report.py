"""Per-session recorder + end-of-session report (summary stats, research metrics, full timestamped transcript).

Nothing here is imported by llm_service or used in any prompt: the facilitator never sees the expert ranking.
Times are kept as epoch seconds while recording and reported as seconds since the session started ("t")
plus an ISO-8601 UTC timestamp ("ts").
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

DEADLOCK_SEC = 4.0          # a deadlock = at least this long with neither participant speaking
MERGE_GAP_SEC = 0.3         # speech instants closer than this are merged into one interval
MP3_BYTES_PER_SEC = 6000.0  # edge-tts output is 48 kbps MP3 -> used to estimate facilitator speaking time

# Coast Guard reference ranks of the 6 board items, keyed by card id (1 = most important to survival).
# Same values as SIM/simlab/scoring.py EXPERT_RANK.
EXPERT_RANK: Dict[str, int] = {
    "item-2": 1,   # Shaving mirror
    "item-8": 2,   # 10 liter can of oil/petrol mixture
    "item-4": 3,   # 25 liter container of water
    "item-5": 4,   # Case of army rations
    "item-10": 5,  # 20 sq. ft. of opaque plastic sheeting
    "item-1": 6,   # Sextant
}
MAX_SCORE = 18  # fully reversed ranking of 6 items


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def estimate_audio_sec(mp3_bytes: int) -> float:
    return mp3_bytes / MP3_BYTES_PER_SEC


def _merge(intervals: List[Tuple[float, float]], join: float = 0.0) -> List[Tuple[float, float]]:
    out: List[List[float]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1] + join:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def find_gaps(intervals: List[Tuple[float, float]], w0: float, w1: float, min_len: float) -> List[Tuple[float, float]]:
    """Silent gaps >= min_len inside [w0, w1], given the (possibly overlapping) activity intervals."""
    gaps: List[Tuple[float, float]] = []
    cursor = w0
    for s, e in _merge([(max(s, w0), min(e, w1)) for s, e in intervals if e > w0 and s < w1]):
        if s - cursor >= min_len:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if w1 - cursor >= min_len:
        gaps.append((cursor, w1))
    return gaps


class SessionRecorder:
    def __init__(self) -> None:
        self.active = False
        self._reset()

    def _reset(self) -> None:
        self.session_id = ""
        self.started_at = 0.0
        self.task_start = 0.0                       # when the participants' task begins (after the welcome clip)
        self.mode = "full"
        self.language = "en"
        self.time_limit_sec = 0
        self.turn_count_at_start = 0
        self.utterances: List[dict] = []            # transcript entries (participants + facilitator)
        self.speech: Dict[str, List[List[float]]] = {}   # participant -> [[start, end], ...] voice activity
        self.facilitator_intervals: List[Tuple[float, float]] = []
        self._facilitator_until = 0.0
        self.agent_busy: List[List[float]] = []     # [start, end] spans where the agent was working on a reply
        self.interruptions = 0
        self.silent_turns = 0                       # turns where the facilitator chose to stay silent

    # ------------------------------------------------------------------ recording
    def start(self, mode: str, language: str, time_limit_sec: int, turn_count: int) -> None:
        self._reset()
        self.active = True
        self.session_id = uuid.uuid4().hex[:12]
        self.started_at = self.task_start = time.time()
        self.mode, self.language, self.time_limit_sec = mode, language, time_limit_sec
        self.turn_count_at_start = turn_count

    def set_task_start(self, epoch: float) -> None:
        if self.active:
            self.task_start = max(self.task_start, epoch)

    def add_speech(self, name: str, now: float, dur: float) -> None:
        """One chunk of detected speech from `name` ending at `now`."""
        if not self.active:
            return
        segs = self.speech.setdefault(name, [])
        start = now - dur
        if segs and start <= segs[-1][1] + MERGE_GAP_SEC:
            segs[-1][1] = max(segs[-1][1], now)
        else:
            segs.append([start, now])

    def add_participant_utterance(self, name: str, text: str, t_start: float, t_end: float) -> None:
        if not self.active or not text:
            return
        self.utterances.append({
            "role": "participant", "speaker": name, "text": text,
            "_start": t_start, "_end": max(t_start, t_end), "words": len(text.split()),
        })

    def add_facilitator_utterance(self, text: str, action: Optional[str], turn_n: Optional[int],
                                  audio_bytes: int, interrupted: bool = False) -> None:
        if not self.active or not text:
            return
        now = time.time()
        dur = estimate_audio_sec(audio_bytes)
        start = max(now, self._facilitator_until)   # clips queue up on the client
        self._facilitator_until = start + dur
        self.facilitator_intervals.append((start, start + dur))
        self.utterances.append({
            "role": "facilitator", "speaker": "Yacine", "text": text, "action": action, "turn": turn_n,
            "_start": start, "_end": start + dur, "words": len(text.split()), "interrupted": interrupted,
        })

    def busy_start(self, t: float) -> None:
        """The agent started working on a reply (participants are waiting for it)."""
        if self.active and not (self.agent_busy and len(self.agent_busy[-1]) == 1):
            self.agent_busy.append([t])

    def busy_end(self, t: Optional[float] = None) -> None:
        if self.agent_busy and len(self.agent_busy[-1]) == 1:
            self.agent_busy[-1].append(t if t is not None else time.time())

    @property
    def facilitator_until(self) -> float:
        return self._facilitator_until

    # ------------------------------------------------------------------ report
    def build(self, end_reason: str, participants: List[str], board_data: Optional[dict],
              turn_count: int, board_events: List[dict]) -> dict:
        ended_at = time.time()
        t0 = self.started_at
        rel = lambda x: round(x - t0, 1)

        transcript = []
        for u in sorted(self.utterances, key=lambda u: u["_start"]):
            row = {
                "t": rel(u["_start"]), "ts": _iso(u["_start"]), "endT": rel(u["_end"]),
                "role": u["role"], "speaker": u["speaker"], "text": u["text"], "words": u["words"],
            }
            if u["role"] == "facilitator":
                row["action"] = u.get("action")
                row["interrupted"] = u.get("interrupted", False)
                row["estDurationSec"] = round(u["_end"] - u["_start"], 1)
            transcript.append(row)

        speakers = list(dict.fromkeys(
            [n for n in participants] + [u["speaker"] for u in self.utterances if u["role"] == "participant"]
        ))
        words = {n: sum(u["words"] for u in self.utterances if u["role"] == "participant" and u["speaker"] == n)
                 for n in speakers}
        utterances = {n: sum(1 for u in self.utterances if u["role"] == "participant" and u["speaker"] == n)
                      for n in speakers}
        speaking_sec = {n: round(sum(e - s for s, e in self.speech.get(n, [])), 1) for n in speakers}

        # --- Conversational Balance Deviation: D = |W1 - W2| / (W1 + W2)
        balance = {"words": words, "D": None, "note": "Needs exactly two participants who spoke."}
        pair = [n for n in speakers if words.get(n, 0) > 0] if len(speakers) != 2 else speakers
        if len(pair) == 2 and (words[pair[0]] + words[pair[1]]) > 0:
            w1, w2 = words[pair[0]], words[pair[1]]
            balance["D"] = round(abs(w1 - w2) / (w1 + w2), 3)
            balance["note"] = "D = |W1 - W2| / (W1 + W2); 0 = perfectly balanced, 1 = one person did all the talking."

        # --- Deadlocks: the WHOLE room silent for >= 4 s, from the end of the welcome to the end.
        # "Room silent" = neither participant speaking AND the agent neither speaking nor working on a reply
        # (waiting for Yacine to answer is not a deadlock).
        w0 = min(self.task_start, ended_at)
        participant_activity = [(s, e) for segs in self.speech.values() for s, e in segs]
        busy = [(b[0], b[1] if len(b) > 1 else ended_at) for b in self.agent_busy]
        gaps = find_gaps(participant_activity + self.facilitator_intervals + busy, w0, ended_at, DEADLOCK_SEC)
        gaps_participants_only = find_gaps(participant_activity, w0, ended_at, DEADLOCK_SEC)
        deadlocks = {
            "thresholdSec": DEADLOCK_SEC,
            "definition": "Whole room silent >= 4 s: no participant speaking and the agent neither speaking nor preparing a reply.",
            "count": len(gaps),
            "totalSilenceSec": round(sum(e - s for s, e in gaps), 1),
            "countParticipantsSilentOnly": len(gaps_participants_only),   # ignores what the agent is doing
            "windowStartT": rel(w0),
            "items": [{"startT": rel(s), "endT": rel(e), "durationSec": round(e - s, 1)} for s, e in gaps],
        }

        # --- Final ranking deviation vs Coast Guard ranking
        final_ranking = None
        if board_data:
            labels = {it["id"]: it["label"] for it in board_data["items"]}
            rows = []
            for i, iid in enumerate(board_data["order"]):
                exp = EXPERT_RANK.get(iid)
                rows.append({
                    "rank": i + 1, "itemId": iid, "item": labels.get(iid, iid), "expertRank": exp,
                    "deviation": abs(i + 1 - exp) if exp else None,
                })
            final_ranking = {
                "ranking": rows,
                "score": sum(r["deviation"] for r in rows if r["deviation"] is not None),
                "maxScore": MAX_SCORE,
                "bothAgreed": bool(board_data.get("allAgreed")),
                "note": "Score = sum over items of |pair rank - Coast Guard rank|; 0 = identical to the reference.",
            }

        fac = [u for u in self.utterances if u["role"] == "facilitator"]
        actions: Dict[str, int] = {}
        for u in fac:
            actions[u.get("action") or "UNKNOWN"] = actions.get(u.get("action") or "UNKNOWN", 0) + 1
        moves = [e for e in board_events if e.get("event") == "move"]
        moves_by: Dict[str, int] = {}
        for e in moves:
            moves_by[e["by"]] = moves_by.get(e["by"], 0) + 1

        duration = ended_at - t0
        return {
            "meta": {
                "sessionId": self.session_id,
                "startedAt": _iso(t0), "endedAt": _iso(ended_at),
                "durationSec": round(duration, 1),
                "timeLimitSec": self.time_limit_sec,
                "endReason": end_reason,                 # "time_up" | "stopped"
                "mode": self.mode, "language": self.language,
                "participants": speakers,
            },
            "summary": {
                "conversationTurns": max(0, turn_count - self.turn_count_at_start),
                "participantUtterances": utterances,
                "participantWords": words,
                "participantSpeakingSec": speaking_sec,
                "facilitatorUtterances": len(fac),
                "facilitatorWords": sum(u["words"] for u in fac),
                "facilitatorSpeakingSecEstimate": round(sum(e - s for s, e in self.facilitator_intervals), 1),
                "facilitatorActions": actions,
                "facilitatorSilentTurns": self.silent_turns,
                "interruptionsOfFacilitator": self.interruptions,
                "boardMoves": len(moves),
                "boardMovesBy": moves_by,
            },
            "metrics": {
                "conversationalBalance": balance,
                "deadlocks": deadlocks,
                "finalRanking": final_ranking,
            },
            "boardEvents": [
                {**{k: v for k, v in e.items() if k not in ("at", "t")}, "t": rel(e["at"])}
                for e in board_events if "at" in e
            ],
            "transcript": transcript,
        }
