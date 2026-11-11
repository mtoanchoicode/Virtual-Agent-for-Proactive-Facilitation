import { useChat } from "../hooks/useChat";
import { useT, useLang, itemLabel, actionLabel } from "../i18n";

const fmtDuration = (sec) => {
  const s = Math.round(sec || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-slate-800 px-3 py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function Metric({ label, hint, value, sub }) {
  return (
    <div className="rounded-lg border border-blue-400/40 bg-slate-800 p-3">
      <div className="text-sm font-semibold text-blue-300">{label}</div>
      <div className="text-3xl font-bold my-1">{value}</div>
      {sub && <div className="text-xs text-slate-300">{sub}</div>}
      <div className="text-xs text-slate-400">{hint}</div>
    </div>
  );
}

function download(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = (report.meta.startedAt || "").replace(/[:.]/g, "-");
  a.href = url;
  a.download = `session_${stamp}_${report.meta.sessionId}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function SessionSummaryModal() {
  const { sessionReport: r, closeSessionReport } = useChat();
  const t = useT();
  const lang = useLang();
  if (!r) return null;

  const { meta, summary: s, metrics: m } = r;
  const names = meta.participants;
  const bal = m.conversationalBalance;
  const dl = m.deadlocks;
  const fr = m.finalRanking;
  const na = t("sum.na", "—");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded-xl bg-slate-900 text-white shadow-2xl p-5 space-y-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold">{t("sum.title", "Session summary")}</h2>
            <p className="text-sm text-slate-400">
              {meta.endReason === "time_up" ? t("sum.timeUp", "Time is up") : t("sum.stopped", "Session stopped")}
              {" · "}{fmtDuration(meta.durationSec)}
            </p>
          </div>
          <button onClick={closeSessionReport} className="text-slate-400 hover:text-white text-2xl leading-none" aria-label="close">×</button>
        </div>

        {/* Metrics */}
        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-2">{t("sum.metrics", "Metrics")}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Metric
              label={t("sum.balance", "Conversational Balance Deviation (D)")}
              value={bal.D == null ? na : bal.D.toFixed(3)}
              sub={names.map((n) => `${n}: ${bal.words[n] ?? 0} ${t("sum.words", "words")}`).join(" · ")}
              hint={t("sum.balanceHint", "Lower = more balanced")}
            />
            <Metric
              label={t("sum.deadlocks", "Deadlock count")}
              value={dl.count}
              sub={`${dl.totalSilenceSec}s total`}
              hint={t("sum.deadlocksHint", "≥ 4 s with nobody speaking")}
            />
            <Metric
              label={t("sum.rankScore", "Final ranking deviation")}
              value={fr ? `${fr.score} / ${fr.maxScore}` : na}
              sub={fr ? (fr.bothAgreed ? t("sum.agreed", "Both agreed") : t("sum.notAgreed", "Not agreed by both")) : null}
              hint={t("sum.rankHint", "Lower = closer to the Coast Guard ranking")}
            />
          </div>
        </section>

        {/* Final ranking vs reference */}
        {fr && (
          <section>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-2">{t("sum.finalRanking", "Final ranking")}</h3>
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-left">
                <tr>
                  <th className="py-1 w-16">{t("sum.pair", "Pair")}</th>
                  <th>Item</th>
                  <th className="w-20">{t("sum.expert", "Expert")}</th>
                  <th className="w-12 text-right">Δ</th>
                </tr>
              </thead>
              <tbody>
                {fr.ranking.map((row) => (
                  <tr key={row.itemId} className="border-t border-slate-700">
                    <td className="py-1">{row.rank}</td>
                    <td>{itemLabel(lang, row.itemId, row.item)}</td>
                    <td>{row.expertRank}</td>
                    <td className={`text-right ${row.deviation ? "text-amber-300" : "text-green-400"}`}>{row.deviation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* Conversation stats */}
        <section className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Stat label={t("sum.duration", "Duration")} value={fmtDuration(meta.durationSec)} />
          <Stat label={t("sum.turns", "Conversation turns")} value={s.conversationTurns} />
          <Stat label={t("sum.facSpoke", "Yacine spoke")} value={`${s.facilitatorUtterances}×`} />
          <Stat label={t("sum.facSilent", "Yacine stayed silent")} value={`${s.facilitatorSilentTurns}×`} />
          <Stat label={t("sum.interruptions", "Interruptions of Yacine")} value={s.interruptionsOfFacilitator} />
          <Stat label={t("sum.boardMoves", "Board moves")} value={s.boardMoves} />
        </section>

        <section>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-2">{t("sum.participants", "Participants")}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {names.map((n) => (
              <div key={n} className="rounded-lg bg-slate-800 px-3 py-2 text-sm">
                <div className="font-semibold">{n}</div>
                <div className="text-slate-300">
                  {s.participantWords[n] ?? 0} {t("sum.words", "words")} · {s.participantUtterances[n] ?? 0} {t("sum.utterances", "utterances")} · {s.participantSpeakingSec[n] ?? 0}s {t("sum.speaking", "speaking")}
                </div>
              </div>
            ))}
          </div>
        </section>

        {Object.keys(s.facilitatorActions).length > 0 && (
          <section>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400 mb-2">{t("sum.facActions", "Facilitator actions")}</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(s.facilitatorActions).map(([a, n]) => (
                <span key={a} className="rounded-full bg-slate-800 px-3 py-1 text-xs">
                  {actionLabel(lang, a)} × {n}
                </span>
              ))}
            </div>
          </section>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={() => download(r)} className="rounded-lg bg-blue-500 hover:bg-blue-600 px-4 py-2 text-sm font-semibold">
            ⬇ {t("sum.download", "Download data (JSON)")}
          </button>
          <button onClick={closeSessionReport} className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm">
            {t("sum.close", "Close")}
          </button>
        </div>
      </div>
    </div>
  );
}
