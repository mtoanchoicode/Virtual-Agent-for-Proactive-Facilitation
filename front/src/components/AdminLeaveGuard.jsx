// Shown when the admin clicks Leave while some session CSVs have not been downloaded.
// Leaving discards those reports for good (they are not stored on the server).
import { useChat } from "../hooks/useChat";
import { useT } from "../i18n";

export default function AdminLeaveGuard({ onCancel, onLeave }) {
  const { adminReports, downloadAllAdminReports } = useChat();
  const t = useT();
  const pending = adminReports.filter((r) => !r.downloaded);

  const downloadAndLeave = () => {
    const n = downloadAllAdminReports();
    // Give the browser time to start the staggered downloads before the page state is cleared.
    setTimeout(onLeave, n * 400 + 600);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-xl bg-slate-900 text-white shadow-2xl p-5 space-y-4 border border-red-400/40">
        <h2 className="text-lg font-bold text-red-300">
          ⚠ {t("admin.guardTitle", "Session data not downloaded")}
        </h2>
        <p className="text-sm text-slate-300">
          {t(
            "admin.guardBody",
            "These sessions have not been downloaded yet. The data is not saved anywhere else — if you leave now it will be lost.",
          )}
        </p>
        <ul className="text-sm space-y-1 max-h-40 overflow-y-auto">
          {pending.map(({ report: r }) => (
            <li key={r.meta.sessionId} className="rounded bg-slate-800 px-3 py-1.5">
              {new Date(r.meta.startedAt).toLocaleString()} · {(r.meta.participants || []).join(" & ") || "—"}
            </li>
          ))}
        </ul>
        <div className="flex flex-col gap-2 pt-1">
          <button
            onClick={downloadAndLeave}
            className="rounded-lg bg-blue-500 hover:bg-blue-600 px-4 py-2 text-sm font-semibold"
          >
            ⬇ {t("admin.downloadAllLeave", "Download all & leave")}
          </button>
          <button
            onClick={onLeave}
            className="rounded-lg bg-red-500/20 hover:bg-red-500/30 border border-red-400/50 px-4 py-2 text-sm font-semibold text-red-300"
          >
            {t("admin.leaveAnyway", "Leave without downloading (data will be lost)")}
          </button>
          <button onClick={onCancel} className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm">
            {t("admin.cancel", "Cancel — stay")}
          </button>
        </div>
      </div>
    </div>
  );
}
