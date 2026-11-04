"""One simulated session as a LangGraph pipeline:

    prepare_room -> individual_rankings -> discussion -> survey -> score -> persist
"""
import asyncio
import json
import os
import random
import time
from typing import Any, Dict, TypedDict

from langgraph.graph import END, START, StateGraph

from simlab import metrics
from simlab.agent import ParticipantAgent
from simlab.audio import Mic
from simlab.discussion import Discussion
from simlab.llm import LLM
from simlab.room import RoomClient, http_get, http_post
from simlab.scoring import LABELS

FACILITATOR_VISUAL = {
    "full": "a 3D animated avatar shown in the call",
    "lite": "an audio-only voice with a simple pulsing visualizer (no avatar)",
}


class SessionState(TypedDict, total=False):
    job: Dict[str, Any]
    agents: Dict[str, ParticipantAgent]
    llm: LLM
    individual: Dict[str, dict]
    discussion: Discussion
    surveys: Dict[str, dict]
    record: dict
    session_row: dict
    participant_rows: list


async def prepare_room(state: SessionState) -> SessionState:
    job = state["job"]
    url = job["backend_url"]
    room = await http_get(url, "/room/participants")
    if room.get("participants"):
        raise RuntimeError(f"Room at {url} is not empty ({len(room['participants'])} participant(s)). "
                           "Close any browser tab connected to this backend.")
    await http_post(url, "/room/mode", {"mode": job["condition"]})
    await http_post(url, "/room/language", {"language": "en"})
    await http_post(url, "/room/time-limit", {"minutes": job["time_limit_min"]})

    llm = LLM(job["agent_model"], job.get("temperature", 0.8))
    p1, p2 = job["personas"]["P1"], job["personas"]["P2"]
    agents = {
        "P1": ParticipantAgent("P1", p1, p2["name"], llm, random.Random(f"{job['seed']}|{job['pair_id']}|P1"),
                               job["time_limit_min"]),
        "P2": ParticipantAgent("P2", p2, p1["name"], llm, random.Random(f"{job['seed']}|{job['pair_id']}|P2"),
                               job["time_limit_min"]),
    }
    return {"agents": agents, "llm": llm}


async def individual_rankings(state: SessionState) -> SessionState:
    a = state["agents"]
    r1, r2 = await asyncio.gather(a["P1"].rank_privately(), a["P2"].rank_privately())
    return {"individual": {"P1": r1, "P2": r2}}


async def discussion(state: SessionState) -> SessionState:
    job, agents = state["job"], state["agents"]
    d = Discussion(agents, job["time_limit_min"] * 60, job["grace_sec"])
    for role in ("P1", "P2"):
        c = RoomClient(job["backend_url"], agents[role].name, d.on_event)
        d.clients[role] = c
        d.mics[role] = Mic(c.send_audio)
    try:
        for role in ("P1", "P2"):
            await d.clients[role].connect()
            await d.clients[role].join()
        for role in ("P1", "P2"):
            await d.clients[role].send_json({"type": "start_voice"})
        print(f"[sim] {job['session_id']}: discussion started ({job['condition']}, {job['time_limit_min']} min)")
        await d.run()
        await asyncio.sleep(1.0)  # let the last board_state arrive
    finally:
        try:
            await d.clients["P1"].send_json({"type": "stop_voice"})
        except Exception:
            pass
        for c in d.clients.values():
            await c.close()
    await asyncio.sleep(2.0)  # give the backend time to reset the room
    return {"discussion": d}


async def survey(state: SessionState) -> SessionState:
    d, agents, job = state["discussion"], state["agents"], state["job"]
    visual = FACILITATOR_VISUAL[job["condition"]]

    async def one(role):
        a = agents[role]
        lines = [line.replace(f"] {a.name}:", "] You:") for line in d.transcript_lines()]
        return await a.answer_survey(lines, visual)

    s1, s2 = await asyncio.gather(one("P1"), one("P2"))
    return {"surveys": {"P1": s1, "P2": s2}}


async def score(state: SessionState) -> SessionState:
    job, d, llm = state["job"], state["discussion"], state["llm"]
    if d.server_items and [it["label"] for it in d.server_items] != LABELS:
        print("[sim] WARNING: server board items differ from SIM/simlab/scoring.py ITEMS")
    participants = {}
    for role in ("P1", "P2"):
        p = job["personas"][role]
        participants[role] = {
            "name": p["name"], "persona_id": p["id"], "demographics": dict(p.get("demographics", {})),
            "individual_ranking": state["individual"][role]["ranking"],
            "individual_reasoning": state["individual"][role]["reasoning"],
            "survey": state["surveys"][role],
        }
        participants[role]["demographics"]["familiarity"] = job.get("familiarity", "Not at all")
    record = {
        "run_id": job["run_id"], "session_id": job["session_id"], "condition": job["condition"],
        "pair_id": job["pair_id"], "seed": job["seed"], "agent_model": job["agent_model"],
        "backend_url": job["backend_url"], "limit_sec": job["time_limit_min"] * 60, "grace_sec": job["grace_sec"],
        "t0": d.t0, "all_agreed_at": d.all_agreed_at, "final_ranking": list(d.board_order),
        "participants": participants,
        "utterances": d.utterances, "facilitator_utterances": d.fac.records(),
        "transcript": d.transcript, "events": d.events, "decisions": d.decision_log, "gen_wait": d.gen_wait,
        "llm_prompt_tokens": llm.prompt_tokens, "llm_completion_tokens": llm.completion_tokens,
    }
    session_row, participant_rows = metrics.compute(record)
    return {"record": record, "session_row": session_row, "participant_rows": participant_rows}


async def persist(state: SessionState) -> SessionState:
    job, rec = state["job"], state["record"]
    out = os.path.join(job["out_dir"], "raw", job["session_id"])
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "session.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(out, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(state["discussion"].transcript_lines()) + "\n")
    with open(os.path.join(out, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"session": state["session_row"], "participants": state["participant_rows"]},
                  f, ensure_ascii=False, indent=1)
    return {}


def build_graph():
    g = StateGraph(SessionState)
    for name, fn in [("prepare_room", prepare_room), ("individual_rankings", individual_rankings),
                     ("discussion", discussion), ("survey", survey), ("score", score), ("persist", persist)]:
        g.add_node(name, fn)
    g.add_edge(START, "prepare_room")
    g.add_edge("prepare_room", "individual_rankings")
    g.add_edge("individual_rankings", "discussion")
    g.add_edge("discussion", "survey")
    g.add_edge("survey", "score")
    g.add_edge("score", "persist")
    g.add_edge("persist", END)
    return g.compile()


SESSION_GRAPH = build_graph()


async def run_session(job: dict) -> SessionState:
    t = time.time()
    state = await SESSION_GRAPH.ainvoke({"job": job})
    print(f"[sim] {job['session_id']}: done in {time.time() - t:.0f}s")
    return state
