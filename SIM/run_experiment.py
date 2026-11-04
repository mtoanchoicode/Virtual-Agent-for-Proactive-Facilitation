"""Run a batch of simulated sessions defined in a YAML config.

    ..\\.venv\\Scripts\\python run_experiment.py --config config/smoke.yaml

Sessions are spread over the backends in `backend_urls` (one session at a time per backend,
because each backend process holds a single room).
"""
import argparse
import asyncio
import json
import os
import shutil
import sys
import time
import traceback

import yaml
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
load_dotenv(os.path.join(HERE, ".env"))
load_dotenv(os.path.join(HERE, "..", "back", ".env"))  # reuse the backend's OPENAI_API_KEY

from simlab.export import export  # noqa: E402
from simlab.session import run_session  # noqa: E402


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(os.path.join(os.path.dirname(path), cfg.get("personas_file", "personas.yaml")), encoding="utf-8") as f:
        cfg["_personas"] = yaml.safe_load(f)
    return cfg


def build_jobs(cfg: dict, run_id: str, out_dir: str) -> list:
    personas, pairs = cfg["_personas"]["personas"], cfg["_personas"]["pairs"]
    jobs = []
    for seed in cfg.get("seeds", [1]):
        for pair_id in cfg["pairs"]:
            pair = pairs[pair_id]
            for condition in cfg["conditions"]:
                jobs.append({
                    "run_id": run_id,
                    "session_id": f"{pair_id}__{condition}__s{seed}",
                    "pair_id": pair_id, "condition": condition, "seed": seed,
                    "familiarity": pair.get("familiarity", "Not at all"),
                    "personas": {
                        "P1": {"id": pair["p1"], **personas[pair["p1"]]},
                        "P2": {"id": pair["p2"], **personas[pair["p2"]]},
                    },
                    "agent_model": cfg.get("agent_model", "gpt-4o"),
                    "temperature": cfg.get("temperature", 0.8),
                    "time_limit_min": cfg.get("time_limit_min", 12),
                    "grace_sec": cfg.get("grace_sec", 30),
                    "out_dir": out_dir,
                })
    return jobs


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config", "experiment.yaml"))
    ap.add_argument("--backend", action="append", help="override backend_urls (repeatable)")
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.backend:
        cfg["backend_urls"] = args.backend

    run_id = time.strftime("%Y%m%d-%H%M%S") + "_" + cfg.get("name", "run")
    out_dir = os.path.join(HERE, cfg.get("output_dir", "out"), run_id)
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy(args.config, os.path.join(out_dir, "experiment.yaml"))
    with open(os.path.join(out_dir, "personas.json"), "w", encoding="utf-8") as f:
        json.dump(cfg["_personas"], f, indent=1)

    jobs = build_jobs(cfg, run_id, out_dir)
    print(f"[sim] run {run_id}: {len(jobs)} session(s) -> {out_dir}")
    queue: asyncio.Queue = asyncio.Queue()
    for j in jobs:
        queue.put_nowait(j)
    done, failed = [], []

    async def worker(url: str) -> None:
        while not queue.empty():
            job = queue.get_nowait()
            job["backend_url"] = url.rstrip("/")
            try:
                done.append(await run_session(job))
                export(out_dir, done)
            except Exception as e:
                traceback.print_exc()
                failed.append({"session_id": job["session_id"], "error": repr(e)})
                await asyncio.sleep(3)

    await asyncio.gather(*(worker(u) for u in cfg.get("backend_urls", ["http://127.0.0.1:3000"])))
    if failed:
        with open(os.path.join(out_dir, "failed.json"), "w", encoding="utf-8") as f:
            json.dump(failed, f, indent=1)
    print(f"[sim] finished: {len(done)} ok, {len(failed)} failed. Results in {out_dir}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
