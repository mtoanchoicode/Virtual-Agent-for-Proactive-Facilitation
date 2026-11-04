# SIM: simulated user trials

Two LLM agents (LangGraph) join the real facilitator backend over `/ws/voice` exactly like two browsers.
They speak with TTS audio streamed in real time, so the backend's VAD, speech-to-text, turn
detection, interruptions, nudges and time checks all run for real. After the task they fill in the
Appendix B survey; the run is scored and exported as CSV.

```
prepare_room -> individual_rankings -> discussion -> survey -> score -> persist     (simlab/session.py)
participant decision: perceive -> deliberate -> act                                   (simlab/agent.py)
```

## Run

1. `back/.env` needs `OPENAI_API_KEY` and `SCENARIO=lost_at_sea`.
2. Start a backend: `start-http.bat` (port 3000), or `SIM\run_backends.bat 3` for ports 3001-3003.
   Close any browser tab connected to that backend; the room must be empty.
3. From `SIM/`:
   ```
   ..\.venv\Scripts\python -m pip install -r requirements.txt
   ..\.venv\Scripts\python run_experiment.py --config config/smoke.yaml
   ..\.venv\Scripts\python analyze.py out/<run_id>
   ```
   `--backend http://127.0.0.1:3001` (repeatable) overrides `backend_urls`.

Sessions run in real time: total wall time is about sessions x (time_limit + 1.5 min) / number of backends.

## Configure

- `config/experiment.yaml`: conditions (`full` = A, `lite` = B), pairs, seeds, time limit, agent model, backends.
- `config/personas.yaml`: personas (talkativeness, verbosity, assertiveness, pause model, voice) and pairs.
  P1 always gets the Signaling card, P2 the Sustenance card (`simlab/roles.py`).
- The Coast Guard key is only in `simlab/scoring.py` and never reaches an agent or the backend.

## Output (`out/<run_id>/`)

| File | One row per |
|---|---|
| `sessions.csv` | session: all H1-H4 metrics, facilitator behaviour, pair-mean survey scales |
| `participants.csv` | participant: words, speaking time, individual score, Likert items, scales, interview answers |
| `utterances.csv` | utterance (participants and facilitator) with start/end seconds |
| `interventions.csv` | facilitator action event |
| `raw/<session>/` | `session.json` (every event), `transcript.txt`, `metrics.json` |
| `summary_by_condition.csv`, `paired_tests.csv` | written by `analyze.py` |

## Metric definitions

- `balance_D_words` = |W1 - W2| / (W1 + W2) from the words the agents actually said;
  `balance_D_words_stt` uses the backend's transcripts (what the human study would measure).
  Same formula for `balance_speaking_time` and `balance_turns`.
- `deadlocks`: silences of 4 s or more with neither participant speaking (protocol definition; time
  the facilitator is talking counts as silence). `deadlocks_nobody_speaking` also treats facilitator
  speech as breaking the silence. `deadlock_resolution_latency_sec` = gap end - (gap start + 4 s).
- `final_score` = sum of |pair rank - expert rank|; `collaborative_improvement` = mean individual score - final score.
- Survey: `helpfulness` = mean(Q4, Q5, Q7); `intrusiveness` = mean(Q8, Q9) on the raw scale (higher = more
  intrusive); `acceptance` = mean(Q4, Q5, Q7, 6-Q8, 6-Q9).
- Analysis window: from session start to the time limit, or to the moment both pressed agree if earlier.

## Simulation caveats

- `sim_generation_wait_sec` / `deadlocks_with_sim_artifact`: time the floor was free only because an
  agent's LLM call had not returned. Exclude or report these deadlocks.
- Survey answers from LLM agents test the pipeline; they are not evidence for H3.
- LLMs may know the published Lost at Sea answers; agents are told to reason only from their role card.
  Check `individual_score_*` for suspiciously low scores.
- Agents never talk over each other (one floor at a time); they can talk over the facilitator.
