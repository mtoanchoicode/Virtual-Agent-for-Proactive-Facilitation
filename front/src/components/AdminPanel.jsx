// Admin observer panel: live status + every finished session's report, kept in browser memory only,
// each downloadable as a CSV. Shown only to the admin.
import { useState } from "react";
import { useChat } from "../hooks/useChat";
import { useT } from "../i18n";

const fmtDuration = (sec) => {
  const s = Math.round(sec || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const fmtTime = (iso) => {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
};

export default function AdminPanel() {
  const { isAdmin, adminReports, downloadAdminReport, downloadAllAdminReports, voiceSessionActive, participants } =
    useChat();
  const t = useT();
  const [collapsed, setCollapsed] = useState(false);
  if (!isAdmin) return null;

  const pending = adminReports.filter((r) => !r.downloaded).length;

  return (
    <div className="fixed bottom-4 left-4 z-40 w-[340px] max-w-[calc(100vw-2rem)] rounded-2xl bg-slate-900/95 text-white shadow-2xl border border-amber-400/40 backdrop-blur">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left"
      >
        <span className="text-sm font-bold text-amber-300">
          🛡 {t("admin.title", "Admin · observing (hidden)")}
        </span>
        <span className="flex items-center gap-2">
          {pending > 0 && (
            <span className="rounded-full bg-red-500 px-2 py-0.5 text-[11px] font-bold">{pending}</span>
          )}
          <span className="text-slate-400 text-xs">{collapsed ? "▲" : "▼"}</span>
        </span>
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-3">
          <div className="text-xs text-slate-300 space-y-1">
            <div>
              {t("admin.status", "Session")}:{" "}
              <span className={voiceSessionActive ? "text-green-400 font-semibold" : "text-slate-400"}>
                {voiceSessionActive ? t("admin.running", "running") : t("admin.idle", "not running")}
              </span>
            </div>
            <div>
              {t("admin.participants", "Participants")}:{" "}
              {participants.length ? participants.map((p) => p.name).join(", ") : "—"}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                {t("admin.sessions", "Finished sessions")}
              </h4>
              {pending > 0 && (
                <button
                  onClick={downloadAllAdminReports}
                  className="rounded-md bg-blue-500 hover:bg-blue-600 px-2 py-1 text-[11px] font-semibold"
                >
                  ⬇ {t("admin.downloadAll", "Download all")}
                </button>
              )}
            </div>
            {adminReports.length === 0 ? (
              <p className="text-xs text-slate-500">
                {t("admin.noSessions", "No finished session yet. Data appears here when a session ends.")}
              </p>
            ) : (
              <ul className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {adminReports.map(({ report: r, downloaded }) => {
                  const fr = r.metrics?.finalRanking;
                  return (
                    <li
                      key={r.meta.sessionId}
                      className={`rounded-lg px-3 py-2 text-xs ${downloaded ? "bg-slate-800" : "bg-amber-500/10 border border-amber-400/40"}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold">
                          {fmtTime(r.meta.startedAt)} · {fmtDuration(r.meta.durationSec)}
                        </span>
                        {downloaded ? (
                          <span className="text-green-400">✓ {t("admin.downloaded", "downloaded")}</span>
                        ) : (
                          <span className="text-amber-300">{t("admin.notDownloaded", "not downloaded")}</span>
                        )}
                      </div>
                      <div className="text-slate-400 truncate">
                        {(r.meta.participants || []).join(" & ") || "—"}
                        {fr ? ` · ${t("admin.score", "score")} ${fr.score}/${fr.maxScore}` : ""}
                      </div>
                      <button
                        onClick={() => downloadAdminReport(r.meta.sessionId)}
                        className="mt-1 rounded-md bg-slate-700 hover:bg-slate-600 px-2 py-1 text-[11px] font-semibold"
                      >
                        ⬇ {t("admin.downloadCsv", "Download CSV")}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
