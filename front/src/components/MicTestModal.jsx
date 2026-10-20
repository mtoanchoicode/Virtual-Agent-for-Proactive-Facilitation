// MicTestModal.jsx
// Mic health checker — connects to backend Silero VAD to test if AI detects voice

import { useState, useEffect, useRef, useCallback } from "react";
import { useT } from "../i18n";

// ── Constants ────────────────────────────────────────────────────────────────
const SAMPLE_RATE = 16000;
const CHUNK_SIZE = 4096;

const isSecure = window.location.protocol === "https:";
const wsProtocol = isSecure ? "wss" : "ws";

// ── MicTestModal ─────────────────────────────────────────────────────────────
export function MicTestModal({ onClose }) {
  const t = useT();
  const [status, setStatus] = useState("idle"); // idle | requesting | active | denied
  const [aiVadDetected, setAiVadDetected] = useState(false);

  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const wsRef = useRef(null);
  const processorRef = useRef(null);

  // ── Start mic ──────────────────────────────────────────────────────────────
  const startMic = useCallback(async () => {
    setStatus("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);

      // ScriptProcessor to send to backend VAD
      const proc = ctx.createScriptProcessor(CHUNK_SIZE, 1, 1);
      processorRef.current = proc;

      const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/mic_test`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          setAiVadDetected(data.is_speech_present);
        } catch (err) { }
      };

      proc.onaudioprocess = (e) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32767));
        }
        ws.send(int16.buffer);
      };

      source.connect(proc);
      proc.connect(ctx.destination);

      setStatus("active");
    } catch (e) {
      console.error(e);
      setStatus("denied");
    }
  }, []);

  // ── Stop mic ───────────────────────────────────────────────────────────────
  const stopMic = useCallback(() => {
    wsRef.current?.close();
    processorRef.current?.disconnect();
    streamRef.current?.getTracks().forEach(t => t.stop());
    audioCtxRef.current?.close();
    streamRef.current = null;
    audioCtxRef.current = null;
    wsRef.current = null;
    processorRef.current = null;
    setAiVadDetected(false);
  }, []);

  useEffect(() => () => stopMic(), [stopMic]);

  // ── Derived UI state ────────────────────────────────────────────────────────
  const isVoiceDetected = aiVadDetected;

  const diagnose = () => {
    if (status !== "active") return null;
    if (aiVadDetected)
      return { icon: "✅", color: "#22c55e", text: t("mic.diagOk", "Silero AI VAD detected your voice! You're good to join.") };
    return { icon: "⚠️", color: "#eab308", text: t("mic.diagWarn", "AI is not detecting voice. If you are speaking, try speaking louder or check your mic settings.") };
  };

  const diagnosis = diagnose();

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.75)",
        backdropFilter: "blur(6px)",
      }}
    >
      <div
        style={{
          position: "relative",
          width: "100%",
          maxWidth: 440,
          margin: "0 16px",
          borderRadius: 20,
          padding: "32px 28px 28px",
          background: "linear-gradient(145deg, #0f172a 0%, #1e293b 100%)",
          border: "1px solid rgba(148,163,184,0.15)",
          boxShadow: "0 25px 60px rgba(0,0,0,0.6)",
          fontFamily: "'DM Sans', sans-serif",
        }}
      >
        {/* Top accent line */}
        <div style={{
          position: "absolute",
          top: 0, left: "50%",
          transform: "translateX(-50%)",
          height: 1, width: "60%",
          background: "linear-gradient(90deg, transparent, #38bdf8, transparent)",
        }} />

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <span style={{ fontSize: 20 }}>🎙</span>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#f1f5f9" }}>
            {t("mic.title", "Mic Check")}
          </h2>
        </div>
        <p style={{ margin: "0 0 22px", fontSize: 13, color: "#64748b" }}>
          {t("mic.desc", "Tests whether your mic is correctly routed to the AI and if the backend Silero VAD detects your speech.")}
        </p>

        {/* Action button */}
        {status === "idle" && (
          <button onClick={startMic} style={btnStyle("#0ea5e9", "#6366f1")}>
            {t("mic.start", "Start Mic Test")}
          </button>
        )}
        {status === "requesting" && (
          <p style={{ color: "#94a3b8", fontSize: 13 }}>{t("mic.requesting", "⏳ Waiting for browser mic permission…")}</p>
        )}
        {status === "denied" && (
          <div style={alertStyle("#ef4444")}>
            {t("mic.denied", "❌ Mic access denied. Please allow microphone access in your browser and reload.")}
          </div>
        )}

        {/* Live meter */}
        {status === "active" && (
          <>
            {/* Status badge */}
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "16px",
              borderRadius: 12, marginBottom: 18,
              background: isVoiceDetected ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
              border: `1px solid ${isVoiceDetected ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`,
              transition: "all 0.2s ease"
            }}>
              <span style={{ fontSize: 24 }}>{isVoiceDetected ? "🟢" : "🔴"}</span>
              <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 15, fontWeight: "600", color: isVoiceDetected ? "#86efac" : "#fca5a5" }}>
                  {isVoiceDetected ? t("mic.detected", "Voice Detected") : t("mic.listening", "Listening...")}
                </span>
                <span style={{ fontSize: 12, color: "#94a3b8" }}>
                  {isVoiceDetected ? t("mic.confirmed", "Backend AI confirms speech") : t("mic.waiting", "Waiting for human voice")}
                </span>
              </div>
            </div>

            {/* Diagnosis */}
            {diagnosis && (
              <div style={{
                padding: "10px 14px", borderRadius: 10, marginBottom: 18,
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(148,163,184,0.1)",
                fontSize: 12, color: "#94a3b8", lineHeight: 1.5,
              }}>
                <span style={{ marginRight: 6 }}>{diagnosis.icon}</span>
                {diagnosis.text}
              </div>
            )}

            <button
              onClick={() => { stopMic(); setStatus("idle"); }}
              style={btnStyle("#475569", "#334155")}
            >
              {t("mic.stop", "Stop Test")}
            </button>
          </>
        )}

        {/* Close */}
        <button
          onClick={() => { stopMic(); onClose(); }}
          style={{
            position: "absolute", top: 14, right: 14,
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "50%",
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", color: "#64748b", fontSize: 13,
            transition: "background 0.2s",
          }}
          onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.12)"}
          onMouseLeave={e => e.currentTarget.style.background = "rgba(255,255,255,0.06)"}
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// ── Tiny style helpers ────────────────────────────────────────────────────────
function btnStyle(from, to) {
  return {
    display: "block", width: "100%",
    padding: "11px 0",
    borderRadius: 10,
    border: "none",
    background: `linear-gradient(135deg, ${from}, ${to})`,
    color: "#fff",
    fontSize: 14, fontWeight: 600,
    cursor: "pointer",
    marginBottom: 8,
    transition: "opacity 0.2s",
  };
}

function alertStyle(color) {
  return {
    padding: "10px 14px", borderRadius: 10,
    background: `${color}18`,
    border: `1px solid ${color}44`,
    color: "#fca5a5", fontSize: 13, lineHeight: 1.5,
    marginBottom: 12,
  };
}
