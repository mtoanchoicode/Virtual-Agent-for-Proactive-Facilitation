"""Summarize a run by condition, with paired comparisons (same pair + seed in both conditions).

    ..\\.venv\\Scripts\\python analyze.py out/<run_id>

Writes summary_by_condition.csv and paired_tests.csv next to the run's CSVs.
Uses scipy for Wilcoxon signed-rank tests if it is installed; otherwise reports mean differences only.
"""
import csv
import os
import sys
from statistics import mean, stdev

METRICS = [
    ("H1", "balance_D_words"), ("H1", "balance_D_words_stt"), ("H1", "balance_speaking_time"), ("H1", "balance_turns"),
    ("H2", "deadlocks"), ("H2", "deadlock_total_sec"), ("H2", "deadlock_resolution_latency_sec"),
    ("H2", "deadlocks_nobody_speaking"), ("H2", "deadlock_total_sec_nobody_speaking"),
    ("H3", "pair_mean_helpfulness"), ("H3", "pair_mean_intrusiveness"), ("H3", "pair_mean_acceptance"),
    ("H4", "final_score"), ("H4", "collaborative_improvement"),
    ("behaviour", "interventions_per_min"), ("behaviour", "facilitator_utterances"),
    ("artifact", "sim_generation_wait_sec"), ("artifact", "deadlocks_with_sim_artifact"),
]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(run_dir: str) -> None:
    with open(os.path.join(run_dir, "sessions.csv"), encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    conditions = sorted({r["condition"] for r in rows})
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        wilcoxon = None

    summary = []
    for hyp, m in METRICS:
        for c in conditions:
            vals = [x for x in (num(r.get(m)) for r in rows if r["condition"] == c) if x is not None]
            summary.append({"hypothesis": hyp, "metric": m, "condition": c, "n": len(vals),
                            "mean": round(mean(vals), 3) if vals else None,
                            "sd": round(stdev(vals), 3) if len(vals) > 1 else None})

    paired = []
    if len(conditions) == 2:
        a, b = conditions
        key = lambda r: (r["pair_id"], r["seed"])
        by = {c: {key(r): r for r in rows if r["condition"] == c} for c in conditions}
        common = sorted(set(by[a]) & set(by[b]))
        for hyp, m in METRICS:
            diffs = [(num(by[a][k].get(m)), num(by[b][k].get(m))) for k in common]
            diffs = [x - y for x, y in diffs if x is not None and y is not None]
            row = {"hypothesis": hyp, "metric": m, "comparison": f"{a} - {b}", "n_pairs": len(diffs),
                   "mean_diff": round(mean(diffs), 3) if diffs else None, "wilcoxon_p": None}
            if wilcoxon and len(diffs) >= 5 and any(diffs):
                row["wilcoxon_p"] = round(float(wilcoxon(diffs).pvalue), 4)
            paired.append(row)

    for name, data in [("summary_by_condition.csv", summary), ("paired_tests.csv", paired)]:
        if data:
            with open(os.path.join(run_dir, name), "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)

    print(f"{'metric':<38}" + "".join(f"{c:>14}" for c in conditions))
    for hyp, m in METRICS:
        cells = [next((s["mean"] for s in summary if s["metric"] == m and s["condition"] == c), None) for c in conditions]
        print(f"{hyp + ' ' + m:<38}" + "".join(f"{'-' if v is None else v:>14}" for v in cells))
    if not wilcoxon:
        print("\n(scipy not installed: paired_tests.csv has mean differences only)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sorted(
        os.path.join("out", d) for d in os.listdir("out") if os.path.isdir(os.path.join("out", d)))[-1])
