// Build one combined CSV from an end-of-session report: SUMMARY block, FINAL RANKING block, TRANSCRIPT block.
// Nothing is stored on the server; the admin downloads it straight from browser memory.

const cell = (v) => {
  if (v === null || v === undefined) return "";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
const row = (...vals) => vals.map(cell).join(",");

export function reportToCsv(report) {
  const { meta = {}, summary: s = {}, metrics: m = {} } = report || {};
  const bal = m.conversationalBalance || {};
  const dl = m.deadlocks || {};
  const fr = m.finalRanking;
  const names = meta.participants || [];
  const lines = [];

  lines.push(row("SUMMARY"));
  lines.push(row("key", "value"));
  const kv = (k, v) => lines.push(row(k, v));
  kv("sessionId", meta.sessionId);
  kv("startedAt", meta.startedAt);
  kv("endedAt", meta.endedAt);
  kv("durationSec", meta.durationSec);
  kv("timeLimitSec", meta.timeLimitSec);
  kv("endReason", meta.endReason);
  kv("mode", meta.mode);
  kv("language", meta.language);
  kv("participants", names.join(" | "));
  kv("conversationalBalanceD", bal.D);
  kv("deadlockCount", dl.count);
  kv("deadlockTotalSilenceSec", dl.totalSilenceSec);
  kv("deadlockCountParticipantsSilentOnly", dl.countParticipantsSilentOnly);
  kv("rankingScore", fr ? fr.score : null);
  kv("rankingMaxScore", fr ? fr.maxScore : null);
  kv("bothAgreed", fr ? fr.bothAgreed : null);
  kv("rankingComplete", fr ? fr.complete : null);
  kv("unplacedCount", fr ? fr.unplacedCount : null);
  kv("conversationTurns", s.conversationTurns);
  names.forEach((n) => {
    kv(`words:${n}`, s.participantWords?.[n] ?? 0);
    kv(`utterances:${n}`, s.participantUtterances?.[n] ?? 0);
    kv(`speakingSec:${n}`, s.participantSpeakingSec?.[n] ?? 0);
  });
  kv("facilitatorUtterances", s.facilitatorUtterances);
  kv("facilitatorWords", s.facilitatorWords);
  kv("facilitatorSpeakingSecEstimate", s.facilitatorSpeakingSecEstimate);
  kv("facilitatorSilentTurns", s.facilitatorSilentTurns);
  kv("interruptionsOfFacilitator", s.interruptionsOfFacilitator);
  kv("boardMoves", s.boardMoves);
  Object.entries(s.boardMovesBy || {}).forEach(([n, c]) => kv(`boardMoves:${n}`, c));
  Object.entries(s.facilitatorActions || {}).forEach(([a, c]) => kv(`facilitatorAction:${a}`, c));

  lines.push("");
  lines.push(row("FINAL RANKING"));
  lines.push(row("rank", "itemId", "item", "expertRank", "deviation", "unplaced"));
  (fr?.ranking || []).forEach((r) =>
    lines.push(row(r.rank, r.itemId, r.item, r.expertRank, r.deviation, r.unplaced ? "yes" : "no")),
  );

  lines.push("");
  lines.push(row("TRANSCRIPT"));
  lines.push(row("t", "ts", "endT", "role", "speaker", "action", "interrupted", "words", "text"));
  (report?.transcript || []).forEach((u) =>
    lines.push(
      row(u.t, u.ts, u.endT, u.role, u.speaker, u.action ?? "", u.role === "facilitator" ? !!u.interrupted : "", u.words, u.text),
    ),
  );

  // BOM so Excel opens UTF-8 (Vietnamese) correctly.
  return "﻿" + lines.join("\r\n") + "\r\n";
}

export function downloadReportCsv(report) {
  const blob = new Blob([reportToCsv(report)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = (report?.meta?.startedAt || "").replace(/[:.]/g, "-");
  a.href = url;
  a.download = `session_${stamp}_${report?.meta?.sessionId || "unknown"}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
