"""Per-session and per-participant metrics, following Section 6 of the pilot protocol."""
from collections import Counter
from statistics import mean
from typing import Dict, List, Optional, Tuple

from simlab import scoring

DEADLOCK_SEC = 4.0
Interval = Tuple[float, float]


def balance(a: float, b: float) -> Optional[float]:
    """|a - b| / (a + b); 0 = perfectly balanced, 1 = one person only."""
    return round(abs(a - b) / (a + b), 4) if a + b > 0 else None


def _clip(intervals: List[Interval], lo: float, hi: float) -> List[Interval]:
    return [(max(s, lo), min(e, hi)) for s, e in intervals if e > lo and s < hi and min(e, hi) > max(s, lo)]


def _merge(intervals: List[Interval]) -> List[Interval]:
    out: List[List[float]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _gaps(speech: List[Interval], lo: float, hi: float) -> List[Interval]:
    gaps, cur = [], lo
    for s, e in _merge(_clip(speech, lo, hi)):
        if s > cur:
            gaps.append((cur, s))
        cur = max(cur, e)
    if hi > cur:
        gaps.append((cur, hi))
    return gaps


def _overlap(a: List[Interval], b: List[Interval]) -> float:
    return sum(max(0.0, min(e1, e2) - max(s1, s2)) for s1, e1 in a for s2, e2 in b)


def deadlocks(speech: List[Interval], lo: float, hi: float, artifacts: List[Interval]) -> dict:
    long_gaps = [(s, e) for s, e in _gaps(speech, lo, hi) if e - s >= DEADLOCK_SEC]
    # Resolution latency: from the moment a silence becomes a deadlock (4 s) to the next speech.
    # A deadlock that runs into the end of the task window is never resolved.
    resolved = [e - (s + DEADLOCK_SEC) for s, e in long_gaps if e < hi]
    contaminated = sum(1 for g in long_gaps if _overlap([g], artifacts) >= 1.0)
    return {
        "count": len(long_gaps),
        "total_sec": round(sum(e - s for s, e in long_gaps), 2),
        "mean_resolution_latency_sec": round(mean(resolved), 2) if resolved else None,
        "count_with_sim_artifact": contaminated,
    }


def compute(rec: dict) -> Tuple[dict, List[dict]]:
    """rec: the raw session record built in session.py. Returns (session_row, participant_rows)."""
    t0 = rec["t0"]
    lo = t0
    task_end = t0 + rec["limit_sec"]
    completed_at = rec.get("all_agreed_at")
    hi = min(task_end, completed_at) if completed_at else task_end
    task_min = (hi - lo) / 60

    utt = rec["utterances"]
    fac = [u for u in rec["facilitator_utterances"] if u.get("end") is not None]
    roles = ["P1", "P2"]
    names = {r: rec["participants"][r]["name"] for r in roles}

    def words(r):
        return sum(len(u["text"].split()) for u in utt if u["role"] == r and u["start"] < hi)

    def seconds(r):
        return sum(e - s for s, e in _clip([(u["start"], u["end"]) for u in utt if u["role"] == r], lo, hi))

    def turns(r):
        # a turn = consecutive utterances by the same speaker
        seq = [u["role"] for u in sorted(utt, key=lambda u: u["start"]) if u["start"] < hi]
        return sum(1 for i, x in enumerate(seq) if x == r and (i == 0 or seq[i - 1] != r))

    # Words as seen by the backend's speech-to-text (what the real study would measure)
    stt_words = Counter()
    for ev in rec["events"]:
        if ev.get("type") == "turn_transcripts" and ev["t"] <= hi + 10:
            for tr in ev.get("transcripts", []):
                stt_words[tr.get("speaker")] += len((tr.get("text") or "").split())

    part_speech = [(u["start"], u["end"]) for u in utt]
    fac_speech = [(u["start"], u["end"]) for u in fac]
    artifacts = [tuple(x) for x in rec["gen_wait"]]
    dl = deadlocks(part_speech, lo, hi, artifacts)
    dl_any = deadlocks(part_speech + fac_speech, lo, hi, artifacts)

    actions = Counter(ev["action"] for ev in rec["events"]
                      if ev.get("type") == "facilitator_action" and ev["t"] <= hi + 5)
    spoken_fac = [u for u in fac if u["start"] < hi]
    overlapped = sum(1 for u in spoken_fac if _overlap([(u["start"], u["end"])], part_speech) > 0.3)
    interruptions = sum(1 for ev in rec["events"] if ev.get("type") == "turn_interrupted" and ev["t"] <= hi)

    final = rec["final_ranking"]
    final_score = scoring.deviation(final)
    indiv = {r: scoring.deviation(rec["participants"][r]["individual_ranking"]) for r in roles}
    mean_indiv = mean(indiv.values())

    surveys = {r: rec["participants"][r].get("survey", {}).get("likert", {}) for r in roles}

    def scales(lk: dict) -> dict:
        if not lk:
            return {}
        return {
            "helpfulness": round(mean([lk["Q4"], lk["Q5"], lk["Q7"]]), 3),
            "intrusiveness": round(mean([lk["Q8"], lk["Q9"]]), 3),
            "acceptance": round(mean([lk["Q4"], lk["Q5"], lk["Q7"], 6 - lk["Q8"], 6 - lk["Q9"]]), 3),
        }

    session = {
        "session_id": rec["session_id"], "run_id": rec["run_id"], "condition": rec["condition"],
        "pair_id": rec["pair_id"], "seed": rec["seed"], "p1_persona": rec["participants"]["P1"]["persona_id"],
        "p2_persona": rec["participants"]["P2"]["persona_id"], "agent_model": rec["agent_model"],
        "time_limit_sec": rec["limit_sec"], "task_minutes_analyzed": round(task_min, 3),
        # H1 equity
        "words_p1": words("P1"), "words_p2": words("P2"),
        "balance_D_words": balance(words("P1"), words("P2")),
        "balance_D_words_stt": balance(stt_words[names["P1"]], stt_words[names["P2"]]),
        "words_p1_stt": stt_words[names["P1"]], "words_p2_stt": stt_words[names["P2"]],
        "balance_speaking_time": balance(seconds("P1"), seconds("P2")),
        "turns_p1": turns("P1"), "turns_p2": turns("P2"),
        "balance_turns": balance(turns("P1"), turns("P2")),
        # H2 flow
        "deadlocks": dl["count"], "deadlock_total_sec": dl["total_sec"],
        "deadlock_resolution_latency_sec": dl["mean_resolution_latency_sec"],
        "deadlocks_nobody_speaking": dl_any["count"],
        "deadlock_total_sec_nobody_speaking": dl_any["total_sec"],
        "deadlocks_with_sim_artifact": dl["count_with_sim_artifact"],
        "sim_generation_wait_sec": round(sum(e - s for s, e in artifacts), 2),
        # H4 decision quality
        "final_score": final_score, "final_band": scoring.band(final_score),
        "individual_score_p1": indiv["P1"], "individual_score_p2": indiv["P2"],
        "mean_individual_score": mean_indiv,
        "collaborative_improvement": round(mean_indiv - final_score, 2),
        "task_completed": bool(completed_at), "completion_time_sec": round(completed_at - t0, 1) if completed_at else None,
        "final_ranking": " | ".join(final),
        # agent behaviour
        "facilitator_utterances": len(spoken_fac),
        "facilitator_overlapping_utterances": overlapped,
        "interruptions_of_facilitator": interruptions,
        **{f"action_{a}": n for a, n in sorted(actions.items())},
        "interventions_per_min": round(sum(n for a, n in actions.items() if a != "NO_ACTION") / task_min, 3) if task_min else None,
        # H3 (pair means)
        **{f"pair_mean_{k}": round(mean(v), 3) for k, v in _pair(surveys, scales).items()},
        "llm_prompt_tokens": rec.get("llm_prompt_tokens"), "llm_completion_tokens": rec.get("llm_completion_tokens"),
    }

    participants = []
    for r in roles:
        p = rec["participants"][r]
        lk = surveys[r]
        participants.append({
            "session_id": rec["session_id"], "condition": rec["condition"], "pair_id": rec["pair_id"],
            "seed": rec["seed"], "role": r, "name": p["name"], "persona_id": p["persona_id"],
            **{f"demo_{k}": v for k, v in p.get("demographics", {}).items()},
            "words": words(r), "words_stt": stt_words[p["name"]], "speaking_sec": round(seconds(r), 2),
            "turns": turns(r), "individual_score": indiv[r],
            "individual_ranking": " | ".join(p["individual_ranking"]),
            **{f"likert_{q}": v for q, v in lk.items()},
            **scales(lk),
            **{f"interview_{q}": v for q, v in p.get("survey", {}).get("interview", {}).items()},
        })
    return session, participants


def _pair(surveys: Dict[str, dict], scales) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for lk in surveys.values():
        for k, v in scales(lk).items():
            out.setdefault(k, []).append(v)
    return out
