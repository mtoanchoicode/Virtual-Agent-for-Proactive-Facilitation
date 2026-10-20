// front/src/components/UI.jsx
import { useRef } from "react";
import { useChat } from "../hooks/useChat";
import { useT } from "../i18n";

// ── Room state → visual style map ────────────────────────────────────────────
const ROOM_STATE_STYLES = {
  idle: { btn: "bg-blue-500 hover:bg-blue-600", label: "Start Voice Session", key: "ui.startVoice" },
  listening: {
    btn: "bg-green-500 hover:bg-green-600",
    label: "Room Listening…",
    key: "ui.roomListening",
  },
  processing: { btn: "bg-amber-500 cursor-wait", label: "AI Processing…", key: "ui.aiProcessing" },
  speaking: {
    btn: "bg-purple-500 cursor-not-allowed",
    label: "Avatar Speaking…",
    key: "ui.avatarSpeaking",
  },
};

export const UI = ({ hidden, ...props }) => {
  const t = useT();
  const input = useRef();
  const {
    // Text chat
    chat,
    loading,
    cameraZoomed,
    setCameraZoomed,
    message,

    // Room
    sessionId,
    myName,
    participants,
    micActive,
    joinRoom,
    leaveRoom,
    toggleMic,

    // Voice session
    voiceSessionActive,
    localVoiceStreaming,
    startVoiceSession,
    stopVoiceSession,

    // Conversation state
    roomState,
    turnTranscripts,
    modelTranscripts,
  } = useChat();

  const { btn: btnColor, label: stateLabelEn, key: stateKey } =
    ROOM_STATE_STYLES[roomState] ?? ROOM_STATE_STYLES.idle;
  const stateLabel = t(stateKey, stateLabelEn);
  const isDisabled = roomState === "processing" || roomState === "speaking";

  const sendMessage = () => {
    const text = input.current.value;
    if (!loading && !message) {
      chat(text);
      input.current.value = "";
    }
  };

  if (hidden) return null;

  return (
    <div className="fixed top-0 left-0 right-0 bottom-0 z-10 flex justify-between p-4 flex-col pointer-events-none">
      {/* ── Top-left: Transcript panel ─────────────────────────────────── */}
      <div className="self-start max-w-md backdrop-blur-md bg-slate-900 bg-opacity-70 p-4 rounded-lg text-white text-sm space-y-3">
        {/* Turn transcripts (all speakers) */}
        {turnTranscripts.length > 0 && (
          <div>
            <p className="font-semibold text-blue-300 mb-1">
              {t("ui.turn", "🎤 Conversation turn:")}
            </p>
            <div className="space-y-1">
              {turnTranscripts.map((t, i) => (
                <p key={i} className="text-gray-100">
                  <span className="text-blue-400 font-medium">
                    {t.speaker}:
                  </span>{" "}
                  {t.text}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* AI response texts */}
        {modelTranscripts.length > 0 && (
          <div>
            <p className="font-semibold text-purple-300 mb-1">
              {t("ui.yacine", "🤖 Yacine says:")}
            </p>
            <div className="space-y-1">
              {modelTranscripts.map((text, i) => (
                <p key={i} className="text-gray-100">
                  • {text}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Room state indicator */}
        {voiceSessionActive && (
          <div className="flex items-center gap-2 pt-1 border-t border-slate-700">
            <span
              className={`w-2 h-2 rounded-full ${roomState === "listening"
                  ? "bg-green-400 animate-pulse"
                  : roomState === "processing"
                    ? "bg-amber-400 animate-pulse"
                    : roomState === "speaking"
                      ? "bg-purple-400 animate-pulse"
                      : "bg-slate-400"
                }`}
            />
            <span className="text-slate-300 text-xs">{stateLabel}</span>
          </div>
        )}
      </div>

      {/* ── Right column: controls ─────────────────────────────────────── */}
      <div className="self-end flex flex-col items-end gap-3">
        {/* Participant list (shown when in room) */}
        {sessionId && participants.length > 0 && (
          <div className="pointer-events-auto backdrop-blur-md bg-slate-900 bg-opacity-70 p-3 rounded-lg text-white text-xs max-w-xs">
            <p className="font-semibold text-slate-300 mb-2">
              {t("ui.room", "Room")} ({participants.length})
            </p>
            <ul className="space-y-1">
              {participants.map((p) => (
                <li key={p.sessionId} className="flex items-center gap-2">
                  {/* Speaking indicator */}
                  <span
                    className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${p.isSpeaking
                        ? "bg-green-400 animate-pulse"
                        : "bg-slate-500"
                      }`}
                  />
                  {/* Mic icon */}
                  <span>{p.micActive ? "🎙" : "🔇"}</span>
                  <span
                    className={
                      p.sessionId === sessionId
                        ? "text-blue-300 font-medium"
                        : "text-slate-200"
                    }
                  >
                    {p.name}
                    {p.sessionId === sessionId ? t("ui.you", " (you)") : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Voice session button — starts/stops the ROOM-LEVEL session */}
        {sessionId && (
          <button
            onClick={() =>
              voiceSessionActive ? stopVoiceSession() : startVoiceSession()
            }
            disabled={isDisabled}
            className={`pointer-events-auto ${btnColor} text-white p-4 rounded-md transition-colors`}
            title={
              voiceSessionActive
                ? `${t("ui.voiceSession", "Voice session")}: ${roomState}`
                : t("ui.startShared", "Start shared voice session")
            }
          >
            {voiceSessionActive ? (
              /* Stop icon */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
                />
              </svg>
            ) : (
              /* Mic icon */
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                />
              </svg>
            )}
          </button>
        )}

        {/* Mic mute toggle (per-participant, only during active voice session) */}
        {sessionId && voiceSessionActive && (
          <button
            onClick={toggleMic}
            className={`pointer-events-auto ${micActive
                ? "bg-slate-600 hover:bg-slate-500"
                : "bg-red-600 hover:bg-red-500"
              } text-white p-3 rounded-md transition-colors`}
            title={micActive ? t("ui.muteMy", "Mute my mic") : t("ui.unmuteMy", "Unmute my mic")}
          >
            {micActive ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-5 h-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-5 h-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.531V19.94a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.506-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.395C2.806 8.757 3.63 8.25 4.51 8.25H6.75z"
                />
              </svg>
            )}
          </button>
        )}

        {/* Camera zoom toggle */}
        <button
          onClick={() => setCameraZoomed(!cameraZoomed)}
          className="pointer-events-auto bg-slate-700 hover:bg-slate-600 text-white p-4 rounded-md transition-colors"
          title={cameraZoomed ? t("ui.zoomOut", "Zoom out") : t("ui.zoomIn", "Zoom in")}
        >
          {cameraZoomed ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM13.5 10.5h-6"
              />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="w-6 h-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607zM10.5 7.5v6m3-3h-6"
              />
            </svg>
          )}
        </button>
      </div>

      {/* ── Bottom: text chat input ────────────────────────────────────── */}
      {/* <div className="flex items-center gap-2 pointer-events-auto max-w-screen-sm w-full mx-auto">
        <input
          className="w-full placeholder:text-gray-800 placeholder:italic p-4 rounded-md bg-opacity-50 bg-white backdrop-blur-md"
          placeholder="Type a message…"
          ref={input}
          onKeyDown={(e) => {
            if (e.key === "Enter") sendMessage();
          }}
        />
        <button
          disabled={loading || !!message}
          onClick={sendMessage}
          className={`bg-blue-500 hover:bg-blue-600 text-white p-4 px-10 font-semibold uppercase rounded-md ${
            loading || message ? "cursor-not-allowed opacity-30" : ""
          }`}
        >
          Send
        </button>
      </div> */}
    </div>
  );
};
