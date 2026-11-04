"""Write the tidy CSVs for statistical analysis (rewritten after every session, so partial runs are usable)."""
import csv
import os
from typing import List


def _write(path: str, rows: List[dict]) -> None:
    if not rows:
        return
    cols: List[str] = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def export(out_dir: str, states: List[dict]) -> None:
    sessions, participants, utterances, interventions = [], [], [], []
    for st in states:
        rec = st["record"]
        t0 = rec["t0"]
        sessions.append(st["session_row"])
        participants += st["participant_rows"]
        base = {"session_id": rec["session_id"], "condition": rec["condition"], "pair_id": rec["pair_id"],
                "seed": rec["seed"]}
        for u in rec["utterances"]:
            utterances.append({**base, "speaker_role": u["role"], "speaker": u["name"],
                               "start_sec": round(u["start"] - t0, 2), "end_sec": round(u["end"] - t0, 2),
                               "words": len(u["text"].split()), "text": u["text"]})
        for u in rec["facilitator_utterances"]:
            utterances.append({**base, "speaker_role": "AI", "speaker": "Yacine",
                               "start_sec": round(u["start"] - t0, 2),
                               "end_sec": round(u["end"] - t0, 2) if u.get("end") else None,
                               "words": len(u["text"].split()), "text": u["text"],
                               "action": u.get("action"), "interrupted": u.get("interrupted")})
        for ev in rec["events"]:
            if ev.get("type") == "facilitator_action":
                interventions.append({**base, "t_sec": round(ev["t"] - t0, 2), "action": ev.get("action")})
    utterances.sort(key=lambda r: (r["session_id"], r["start_sec"]))
    _write(os.path.join(out_dir, "sessions.csv"), sessions)
    _write(os.path.join(out_dir, "participants.csv"), participants)
    _write(os.path.join(out_dir, "utterances.csv"), utterances)
    _write(os.path.join(out_dir, "interventions.csv"), interventions)
