"""Real-time discussion loop: floor control between the two agents, facilitator listening, board, timeline.

Agents decide ahead of time: whenever something new is said, both agents start a fresh decision
(LLM + TTS) while the current speech is still playing, so LLM latency does not show up as silence.
When the floor is free, the agent whose decided pause runs out first speaks. Any time the floor is
free while a decision is still being generated is logged as `gen_wait` (a simulation artifact that
metrics can flag).
"""
import asyncio
import time
from typing import Dict, List, Optional

from simlab.agent import ParticipantAgent
from simlab.audio import Mic
from simlab.room import FacilitatorChannel, RoomClient
from simlab.scoring import ID_BY_LABEL, LABEL_BY_ID, LABELS

TICK = 0.05


def _mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


class Discussion:
    def __init__(self, agents: Dict[str, ParticipantAgent], limit_sec: int, grace_sec: int):
        self.agents = agents                      # "P1"/"P2" -> agent
        self.limit_sec = limit_sec
        self.grace_sec = grace_sec
        self.clients: Dict[str, RoomClient] = {}
        self.mics: Dict[str, Mic] = {}
        self.fac = FacilitatorChannel()

        self.t0: Optional[float] = None
        self.events: List[dict] = []              # raw backend broadcasts (audio data stripped)
        self.transcript: List[dict] = []          # what participants heard: {t, who, role, text}
        self.version = 0                          # bumped whenever something new is said
        self.utterances: List[dict] = []          # participant ground truth: {role, name, start, end, text}
        self.decision_log: List[dict] = []
        self.gen_wait: List[List[float]] = []
        self.board_order: List[str] = [it for it in LABELS]
        self.agreed_sessions: List[str] = []
        self.all_agreed_at: Optional[float] = None
        self.server_items: List[dict] = []

        self.speaking_role: Optional[str] = None
        self.floor_free_since: Optional[float] = None
        self.phase = "discussion"
        self._started = asyncio.Event()

    # ------------------------------------------------------------------ backend events
    async def on_event(self, client: RoomClient, data: dict) -> None:
        now = time.time()
        kind = data.get("type")
        primary = client is self.clients.get("P1")
        if kind == "voice_session_started" and self.t0 is None:
            self.t0 = now
            self._started.set()
        if not primary:
            return  # both clients receive the same broadcasts; record once
        if kind == "audio_stream_chunk":
            self.fac.on_chunk(data["msgId"], data["data"], now)
            return
        self.events.append({"t": now, **{k: v for k, v in data.items() if k != "data"}})
        if kind == "audio_stream_start":
            self.fac.on_start(data["msgId"], data.get("text", ""), now)
            self._hear(now, "Yacine (AI facilitator)", "AI", data.get("text", ""))
        elif kind == "audio_stream_end":
            self.fac.on_end(data["msgId"], now)
        elif kind == "facilitator_action":
            self.fac.last_action = data.get("action", "")
        elif kind == "turn_interrupted":
            self.fac.on_interrupt(now)
        elif kind == "board_state":
            self.server_items = data.get("items", self.server_items)
            self.board_order = [LABEL_BY_ID.get(i, i) for i in data.get("order", [])] or self.board_order
            self.agreed_sessions = data.get("agreed", [])
            if data.get("allAgreed") and self.all_agreed_at is None:
                self.all_agreed_at = now
            elif not data.get("allAgreed"):
                self.all_agreed_at = None

    def _hear(self, now: float, who: str, role: str, text: str) -> None:
        if not text:
            return
        self.transcript.append({"t": now, "who": who, "role": role, "text": text})
        self.version += 1

    def transcript_lines(self) -> List[str]:
        t0 = self.t0 or 0
        return [f"[{_mmss(x['t'] - t0)}] {x['who']}: {x['text']}" for x in self.transcript]

    # ------------------------------------------------------------------ context for one agent
    def _context(self, role: str) -> dict:
        now = time.time()
        agent = self.agents[role]
        partner_role = "P2" if role == "P1" else "P1"
        partner_sid = self.clients[partner_role].session_id
        elapsed = now - (self.t0 or now)
        if self.speaking_role == role:
            situation = "You are still saying your last line above; decide what you do once you finish."
        elif self.speaking_role == partner_role:
            situation = f"{agent.partner_name} is saying the last line above right now; decide how you respond once they finish."
        elif self.fac.speaking(now):
            situation = "Yacine is speaking the last line above right now."
        else:
            silence = now - self.floor_free_since if self.floor_free_since else 0.0
            situation = f"Nobody is speaking. It has been silent for {silence:.0f} seconds."
        lines = [f"[{_mmss(x['t'] - (self.t0 or 0))}] "
                 f"{'You' if x['role'] == role else x['who']}: {x['text']}" for x in self.transcript]
        return {
            "board": list(self.board_order),
            "partner_agreed": partner_sid in self.agreed_sessions,
            "transcript": lines,
            "elapsed": _mmss(elapsed),
            "remaining": _mmss(self.limit_sec - elapsed),
            "phase": self.phase,
            "situation": situation,
        }

    # ------------------------------------------------------------------ actions
    async def _apply_board(self, role: str, decision: dict) -> None:
        client = self.clients[role]
        for m in decision["board_moves"]:
            await client.board_move(ID_BY_LABEL[m["item"]], m["rank"] - 1)
            await asyncio.sleep(0.15)
        if decision["press_agree"] and client.session_id not in self.agreed_sessions:
            await asyncio.sleep(0.3)
            await client.board_agree(True)

    async def _speak(self, role: str, decision: dict) -> None:
        agent = self.agents[role]
        self.speaking_role = role
        self._hear(time.time(), agent.name, role, decision["utterance"])
        try:
            start, end = await self.mics[role].say(decision["pcm"])
            self.utterances.append({"role": role, "name": agent.name, "start": start, "end": end,
                                    "text": decision["utterance"]})
        finally:
            self.speaking_role = None
        await self._apply_board(role, decision)

    # ------------------------------------------------------------------ main loop
    async def run(self) -> None:
        await asyncio.wait_for(self._started.wait(), 15)
        for m in self.mics.values():
            m.start()
        end_task = self.t0 + self.limit_sec
        hard_end = end_task + self.grace_sec
        decisions: Dict[str, Optional[dict]] = {r: None for r in self.agents}
        tasks: Dict[str, Optional[asyncio.Task]] = {r: None for r in self.agents}
        speak_task: Optional[asyncio.Task] = None
        gen_wait_open: Optional[float] = None

        async def decide(role: str, version: int) -> None:
            try:
                ctx = self._context(role)
                ctx["is_current"] = lambda: version == self.version
                d = await self.agents[role].decide(ctx)
            except Exception as e:
                self.decision_log.append({"t": time.time(), "role": role, "version": version, "error": repr(e)})
                print(f"[sim] {role} decision failed: {e!r}")
                await asyncio.sleep(2.0)  # back off before the loop retries
                return
            d.update(version=version, made_at=time.time(), recheck_at=None)
            self.decision_log.append({"t": d["made_at"], "role": role, "version": version,
                                      **{k: v for k, v in d.items() if k != "pcm"}})
            if version != self.version:
                return  # something new was said meanwhile; a fresh decision is already queued
            decisions[role] = d
            if not d["speak"] and (d["board_moves"] or d["press_agree"]):
                asyncio.create_task(self._apply_board(role, d))

        try:
            while True:
                now = time.time()
                if now >= hard_end:
                    break
                if self.all_agreed_at and now - self.all_agreed_at > 2.0:
                    break
                if self.phase == "discussion" and now >= end_task:
                    self.phase = "final"
                    self.version += 1  # re-decide with the time-up instruction

                busy = self.speaking_role is not None or self.fac.speaking(now)
                if busy:
                    self.floor_free_since = None
                elif self.floor_free_since is None:
                    self.floor_free_since = now

                # keep each agent's decision fresh
                for role in self.agents:
                    d = decisions[role]
                    stale = d is None or d["version"] != self.version
                    if d and not stale and not d["speak"] and self.floor_free_since:
                        if d["recheck_at"] is None:
                            d["recheck_at"] = max(d["made_at"], self.floor_free_since) + d["wait"]
                        stale = now >= d["recheck_at"]
                    if stale:
                        decisions[role] = None
                        if tasks[role] is None or tasks[role].done():
                            tasks[role] = asyncio.create_task(decide(role, self.version))

                # take the floor
                if not busy and (speak_task is None or speak_task.done()):
                    ready = [(max(self.floor_free_since + d["pause"], d["made_at"]), r)
                             for r, d in decisions.items() if d and d["speak"] and d["version"] == self.version]
                    pending = any(t and not t.done() for t in tasks.values())
                    if not ready and pending and gen_wait_open is None:
                        gen_wait_open = now
                    if (ready or not pending) and gen_wait_open is not None:
                        self.gen_wait.append([gen_wait_open, now])
                        gen_wait_open = None
                    if ready:
                        at, role = min(ready)
                        if now >= at:
                            d = decisions[role]
                            decisions[role] = None
                            speak_task = asyncio.create_task(self._speak(role, d))
                            await asyncio.sleep(0)  # let _speak mark the floor taken
                            continue
                elif gen_wait_open is not None:
                    self.gen_wait.append([gen_wait_open, now])
                    gen_wait_open = None
                await asyncio.sleep(TICK)
        finally:
            if gen_wait_open is not None:
                self.gen_wait.append([gen_wait_open, time.time()])
            for t in tasks.values():
                if t and not t.done():
                    t.cancel()
            if speak_task and not speak_task.done():
                try:
                    await asyncio.wait_for(speak_task, 30)
                except Exception:
                    pass
            for m in self.mics.values():
                await m.stop()
