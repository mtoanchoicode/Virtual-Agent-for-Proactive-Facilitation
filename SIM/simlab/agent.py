"""Simulated participant: a LangGraph decision graph plus pre-task ranking and post-task survey.

Decision graph (run every time something new is said):
    perceive   -> builds the prompt from what this participant can see and hear
    deliberate -> LLM picks speak/wait, the utterance, card moves, agree
    act        -> validates moves, applies the persona's pause model, synthesizes speech
"""
import difflib
import math
import random
import re
import time
from typing import List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from simlab import roles
from simlab.audio import synthesize
from simlab.llm import LLM, obj
from simlab.scoring import LABELS

DECISION_SCHEMA = obj(
    inner_thought={"type": "string", "description": "Private one-sentence reasoning; never spoken."},
    speak={"type": "boolean"},
    utterance={"type": "string", "description": "Exact words spoken aloud; empty if speak is false."},
    hesitation_sec={"type": "number", "description": "Seconds you pause before speaking, or stay silent before reconsidering."},
    board_moves={"type": "array", "items": obj(item={"type": "string"}, rank={"type": "integer"})},
    press_agree={"type": "boolean"},
)

RANKING_SCHEMA = obj(
    reasoning={"type": "string"},
    ranking={"type": "array", "items": {"type": "string"}},
)

LIKERT = {"type": "integer", "enum": [1, 2, 3, 4, 5]}
SURVEY_ITEMS = {
    "Q1": "I felt that both participants had an equal opportunity to express their views.",
    "Q3": "I felt that the discussion moved forward without unnecessary delays or long periods of silence.",
    "Q4": "The facilitator helped us move the discussion forward when we were having difficulty.",
    "Q5": "The facilitator helped us consider the important trade-offs between different items.",
    "Q7": "Overall, I found the facilitator helpful during the task.",
    "Q8": "The facilitator spoke too often during our discussion.",
    "Q9": "The facilitator interrupted the discussion unnecessarily.",
    "Q11": "I was satisfied with the way the discussion went.",
    "Q13": "I would use a facilitator like this for a similar collaborative task in the future.",
}
INTERVIEW_ITEMS = {
    "I1": "Can you briefly describe how you and your partner made decisions during the task? Was there any "
          "disagreement that was particularly difficult to resolve?",
    "I2": "Overall, how did the facilitator affect your discussion? Please describe one specific moment when it "
          "was helpful, unhelpful, distracting, or when you felt it should have behaved differently.",
}
SURVEY_SCHEMA = obj(
    likert=obj(**{q: LIKERT for q in SURVEY_ITEMS}),
    interview=obj(**{q: {"type": "string"} for q in INTERVIEW_ITEMS}),
)


def match_label(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    for label in LABELS:
        if t == label.lower():
            return label
    hits = difflib.get_close_matches(t, [l.lower() for l in LABELS], n=1, cutoff=0.5)
    if hits:
        return next(l for l in LABELS if l.lower() == hits[0])
    sub = next((l for l in LABELS if t and (t in l.lower() or l.lower() in t)), None)
    if sub:
        return sub
    # word overlap, e.g. "oil petrol" -> "10 liter can of oil/petrol mixture"
    words = set(re.findall(r"[a-z]{3,}", t)) - {"the", "and", "can", "box", "boxes", "bottle", "one"}
    best = max(LABELS, key=lambda l: len(words & set(re.findall(r"[a-z]{3,}", l.lower()))))
    return best if words & set(re.findall(r"[a-z]{3,}", best.lower())) else None


def complete_ranking(labels: List[str]) -> List[str]:
    """Dedupe/clean an LLM ranking and append any missing items, so it is a full permutation."""
    out: List[str] = []
    for raw in labels:
        m = match_label(raw)
        if m and m not in out:
            out.append(m)
    return out + [l for l in LABELS if l not in out]


class DecisionState(TypedDict, total=False):
    context: dict
    user_prompt: str
    raw: dict
    decision: dict


class ParticipantAgent:
    def __init__(self, role: str, persona: dict, partner_name: str, llm: LLM,
                 rng: random.Random, minutes: int):
        self.role = role
        self.persona = persona
        self.name = persona["name"]
        self.partner_name = partner_name
        self.llm = llm
        self.rng = rng
        self.minutes = minutes
        self.private_ranking: List[str] = []
        self.max_words = roles.max_words(persona)
        self.system = self._system_prompt()

        g = StateGraph(DecisionState)
        g.add_node("perceive", self._perceive)
        g.add_node("deliberate", self._deliberate)
        g.add_node("act", self._act)
        g.add_edge(START, "perceive")
        g.add_edge("perceive", "deliberate")
        g.add_edge("deliberate", "act")
        g.add_edge("act", END)
        self.graph = g.compile()

    # ------------------------------------------------------------------ prompts
    def _system_prompt(self) -> str:
        return (
            f"You are {self.name}, a university student in a recorded pilot study. You are on a video call with "
            f"your partner {self.partner_name}. An AI facilitator called Yacine may also speak in the call.\n\n"
            f"THE TASK:\n{roles.task_brief(self.minutes)}\n\n"
            f"YOUR PRIVATE ROLE CARD (never read it out or show it):\n{roles.ROLE_CARDS[self.role]}\n\n"
            f"YOUR PERSONALITY:\n{roles.persona_description(self.persona)}\n\n"
            "HOW TO BEHAVE:\n"
            f"- You speak out loud in casual spoken English. One turn is what you say before letting someone else "
            f"talk: at most {self.max_words} words. No stage directions, emojis or lists; only the words you say.\n"
            "- Argue from your role card and everyday reasoning. You do not know any official or expert answer; "
            "never mention the Coast Guard, experts or an answer key.\n"
            "- React to what was actually just said. If Yacine speaks to you, react as a real participant would.\n"
            "- You may stay silent (speak=false) to think or to let your partner talk; pauses of a few seconds "
            "are normal in a real conversation.\n"
            "- Board moves: only place a card at a rank you and your partner agreed on out loud (or that you "
            "announce in the same turn). Use exact item names. Moves are applied in order.\n"
            "- Set press_agree=true only when you accept the WHOLE board ranking as final."
        )

    def _perceive(self, state: DecisionState) -> DecisionState:
        c = state["context"]
        board = "\n".join(f"{i + 1}. {label}" for i, label in enumerate(c["board"]))
        lines = "\n".join(c["transcript"][-120:]) or "(nobody has spoken yet)"
        phase = (
            "TIME IS UP. Finish placing the cards and press agree if you accept the board; speak only if needed."
            if c["phase"] == "final" else
            f"{c['elapsed']} elapsed, {c['remaining']} remaining (the timer is visible on screen)."
        )
        prompt = (
            f"TIME: {phase}\n\n"
            f"SHARED BOARD (current order){' - your partner has pressed agree' if c['partner_agreed'] else ''}:\n{board}\n\n"
            f"YOUR OWN RANKING BEFORE THE DISCUSSION (private notes):\n"
            + ", ".join(f"{i + 1}. {l}" for i, l in enumerate(self.private_ranking))
            + f"\n\nCONVERSATION SO FAR:\n{lines}\n\n"
            f"RIGHT NOW: {c['situation']}\n\nDecide what you do next."
        )
        return {"user_prompt": prompt}

    async def _deliberate(self, state: DecisionState) -> DecisionState:
        raw = await self.llm.json(self.system, state["user_prompt"], "decision", DECISION_SCHEMA)
        return {"raw": raw}

    async def _act(self, state: DecisionState) -> DecisionState:
        raw = state["raw"]
        utterance = " ".join((raw.get("utterance") or "").split())
        speak = bool(raw.get("speak")) and bool(utterance)
        if speak:
            words = utterance.split()
            if len(words) > self.max_words + 10:
                utterance = " ".join(words[: self.max_words + 10])
        moves = []
        for m in raw.get("board_moves") or []:
            label = match_label(m.get("item", ""))
            rank = m.get("rank")
            if label and isinstance(rank, int) and 1 <= rank <= len(LABELS):
                moves.append({"item": label, "rank": rank})
        hes = max(0.0, min(float(raw.get("hesitation_sec") or 0.0), 20.0))
        # Skip TTS for a decision that is already stale (it will be discarded): wasted edge-tts calls
        # get throttled and slow down whichever agent is unlucky, which then never gets the floor.
        is_current = state["context"].get("is_current")
        tts = speak and (is_current is None or is_current())
        decision = {
            "speak": speak,
            "utterance": utterance if speak else "",
            "inner_thought": raw.get("inner_thought", ""),
            "board_moves": moves,
            "press_agree": bool(raw.get("press_agree")),
            "llm_hesitation": hes,
            "pause": self._pause(hes) if speak else 0.0,
            "wait": max(2.0, hes) if not speak else 0.0,
            "pcm": b"",
            "tts_sec": 0.0,
        }
        if tts:
            t = time.time()
            decision["pcm"] = await synthesize(utterance, self.persona["voice"], self.persona.get("tts_rate", "+0%"))
            decision["tts_sec"] = round(time.time() - t, 2)
        return {"decision": decision}

    def _pause(self, llm_hesitation: float) -> float:
        """Persona pause model: lognormal reaction time, the LLM's own hesitation, and an occasional
        long hesitation (the source of natural deadlocks)."""
        p = self.persona
        pause = self.rng.lognormvariate(math.log(max(0.1, p.get("reaction_sec", 1.0))), 0.4)
        pause += 0.5 * min(llm_hesitation, 4.0)
        if self.rng.random() < p.get("stuck_prob", 0.05):
            pause += self.rng.uniform(4.0, 10.0)
        return min(pause, 15.0)

    # ------------------------------------------------------------------ public API
    async def decide(self, context: dict) -> dict:
        out = await self.graph.ainvoke({"context": context})
        return out["decision"]

    async def rank_privately(self) -> dict:
        res = await self.llm.json(
            self.system,
            "Before the discussion starts, privately write down your own ranking of all 6 items "
            "(1 = most important). Base it on your role card and your own reasoning. List every item exactly once, "
            "using the exact item names.",
            "individual_ranking", RANKING_SCHEMA,
        )
        self.private_ranking = complete_ranking(res.get("ranking", []))
        return {"ranking": self.private_ranking, "reasoning": res.get("reasoning", "")}

    async def answer_survey(self, transcript: List[str], facilitator_visual: str) -> dict:
        items = "\n".join(f"{q}. {t}" for q, t in SURVEY_ITEMS.items())
        interview = "\n".join(f"{q}. {t}" for q, t in INTERVIEW_ITEMS.items())
        user = (
            "The discussion has ended. Here is what was said during the session:\n"
            + ("\n".join(transcript) or "(nothing)")
            + f"\n\nThe facilitator, Yacine, appeared in the call as: {facilitator_visual}.\n\n"
            "Now fill in the post-session questionnaire honestly, as yourself, based on how YOU experienced the "
            "session. Scale: 1 = Strongly Disagree, 2 = Disagree, 3 = Neither, 4 = Agree, 5 = Strongly Agree.\n"
            f"{items}\n\nThen answer the interview questions in two to four spoken-style sentences each:\n{interview}"
        )
        return await self.llm.json(self.system, user, "survey", SURVEY_SCHEMA, temperature=0.7)
