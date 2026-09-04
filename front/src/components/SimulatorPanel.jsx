// front/src/components/SimulatorPanel.jsx
// ─────────────────────────────────────────────────────────────────────────────
// User 2 Simulator — connects as a second user, plays pre-recorded audio
// files, and streams the PCM audio to the backend just like a real user.
// ─────────────────────────────────────────────────────────────────────────────
import { useState, useRef, useEffect, useCallback } from "react";

// ── Constants ────────────────────────────────────────────────────────────────
const SAMPLE_RATE = 16000;   // Must match backend expectation
const CHUNK_SIZE  = 4096;    // Samples per chunk (same as useChat.jsx)
const CHUNK_INTERVAL_MS = (CHUNK_SIZE / SAMPLE_RATE) * 1000; // ~256 ms

const ICE_SERVERS = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
    {
      urls: "turn:openrelay.metered.ca:80",
      username: "openrelayproject",
      credential: "openrelayproject",
    },
    {
      urls: "turn:openrelay.metered.ca:443",
      username: "openrelayproject",
      credential: "openrelayproject",
    },
  ],
};

// ── Fallback phrase list (used if phrases.json hasn't been generated yet) ────
const FALLBACK_PHRASES = [
  { name: "Greeting",        file: "greeting.mp3",      text: "Hello! Great to meet you here today." },
  { name: "Agreement",       file: "agreement.mp3",     text: "Yes, I completely agree with that point." },
  { name: "Question",        file: "question.mp3",      text: "Can you explain more about what you just said?" },
  { name: "Positive Feedback", file: "positive.mp3",   text: "That's a really interesting perspective, thank you." },
  { name: "Disagreement",    file: "disagreement.mp3",  text: "I'm not quite sure I fully agree. Can we discuss it?" },
  { name: "Summary",         file: "summary.mp3",       text: "So to summarize what we have discussed so far..." },
  { name: "Redirect",        file: "redirect.mp3",      text: "Let's try to move on to the next topic now." },
  { name: "Clarify",         file: "clarify.mp3",       text: "What exactly do you mean by that? Could you elaborate?" },
  { name: "Encouragement",   file: "encourage.mp3",     text: "You are doing great, please keep going!" },
  { name: "Closing",         file: "close.mp3",         text: "I think we have covered everything. Thank you all." },
];

// ── Utility: tiny icon components ────────────────────────────────────────────
function PlayIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
      <polygon points="2,1 11,6 2,11" />
    </svg>
  );
}
function StopIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
      <rect x="2" y="2" width="8" height="8" rx="1" />
    </svg>
  );
}
function ChevronLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}
function ChevronRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

// ── SimulatorPanel ────────────────────────────────────────────────────────────
export function SimulatorPanel({ onClose }) {
  const [phrases, setPhrases]     = useState(FALLBACK_PHRASES);
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [joined, setJoined]       = useState(false);
  const [voiceReady, setVoiceReady] = useState(false);
  const [playing, setPlaying]     = useState(false);
  const [status, setStatus]       = useState("Connecting…");
  const [loadingAudio, setLoadingAudio] = useState(false);

  // Refs that survive re-renders without causing them
  const wsRef          = useRef(null);
  const audioCtxRef    = useRef(null);
  const sourceNodeRef  = useRef(null);   // AudioBufferSourceNode currently playing
  const sendTimerRef   = useRef(null);   // setInterval handle for PCM streaming
  const pcRef          = useRef(null);   // RTCPeerConnection (answers main user's offer)
  const voiceReadyRef  = useRef(false);  // mirror so cleanup can read without re-render

  const isSecure  = window.location.protocol === "https:";
  const WS_URL    = `${isSecure ? "wss" : "ws"}://${window.location.host}/ws/voice`;

  // ── Load phrases.json from public/simulator/ ──────────────────────────────
  useEffect(() => {
    fetch("/simulator/phrases.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (Array.isArray(data) && data.length) setPhrases(data); })
      .catch(() => {}); // silently fall back to FALLBACK_PHRASES
  }, []);

  // ── Internal stop helper (doesn't touch React state directly) ────────────
  const stopStream = useCallback(() => {
    if (sendTimerRef.current) {
      clearInterval(sendTimerRef.current);
      sendTimerRef.current = null;
    }
    try { sourceNodeRef.current?.stop(); } catch (_) {}
    sourceNodeRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
  }, []);

  // ── WebSocket + lifecycle ─────────────────────────────────────────────────
  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "join", name: "Simulator" }));
    };

    ws.onmessage = async (e) => {
      // Binary frames are not expected inbound, but guard anyway
      if (e.data instanceof ArrayBuffer) return;

      let data;
      try { data = JSON.parse(e.data); } catch { return; }

      switch (data.type) {
        case "joined":
          setJoined(true);
          setStatus("Joined ✓");
          if (data.voiceSessionActive) {
            setVoiceReady(true);
            voiceReadyRef.current = true;
            setStatus("Ready");
          }
          break;

        case "voice_session_started":
          setVoiceReady(true);
          voiceReadyRef.current = true;
          setStatus("Ready");
          break;

        case "voice_session_ended":
          setVoiceReady(false);
          voiceReadyRef.current = false;
          setStatus("Session ended");
          break;

        case "error":
          setStatus(`⚠ ${String(data.detail ?? "error").slice(0, 40)}`);
          break;

        // ── WebRTC signaling ─────────────────────────────────────────────
        // The main user calls us when we join; we answer so their PC
        // doesn't hang. We don't add audio tracks here because the
        // simulator audio goes through the WebSocket (PCM → backend),
        // not WebRTC peer-to-peer.
        case "webrtc_offer": {
          try {
            pcRef.current?.close();
            const pc = new RTCPeerConnection(ICE_SERVERS);
            pcRef.current = pc;

            pc.onicecandidate = (ev) => {
              if (ev.candidate && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                  type: "webrtc_ice_candidate",
                  targetSessionId: data.fromSessionId,
                  candidate: ev.candidate,
                }));
              }
            };

            await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            ws.send(JSON.stringify({
              type: "webrtc_answer",
              targetSessionId: data.fromSessionId,
              answer,
            }));
          } catch (err) {
            console.error("[Simulator] WebRTC offer error:", err);
          }
          break;
        }

        case "webrtc_answer": {
          // Simulator never initiates offers, but handle gracefully
          break;
        }

        case "webrtc_ice_candidate": {
          try {
            if (pcRef.current && data.candidate) {
              await pcRef.current.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
          } catch (err) {
            console.warn("[Simulator] ICE candidate error:", err);
          }
          break;
        }

        default:
          break;
      }
    };

    ws.onerror  = () => setStatus("Connection error");
    ws.onclose  = () => {
      setJoined(false);
      setVoiceReady(false);
      voiceReadyRef.current = false;
      setPlaying(false);
    };

    return () => {
      stopStream();
      ws.close();
      pcRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Play / Stop ───────────────────────────────────────────────────────────
  const handlePlay = useCallback(async () => {
    // Stop if already playing
    if (playing) {
      stopStream();
      setPlaying(false);
      setStatus("Ready");
      return;
    }

    if (!joined) return;

    const phrase = phrases[phraseIdx];
    if (!phrase) return;

    setLoadingAudio(true);
    setStatus(`Loading ${phrase.name}…`);

    try {
      // 1. Fetch the audio file
      const response = await fetch(`/simulator/${phrase.file}`);
      if (!response.ok) {
        throw new Error(`File not found: /simulator/${phrase.file} — run generate_simulator_audio.py first`);
      }
      const arrayBuffer = await response.arrayBuffer();

      // 2. Create an AudioContext at exactly 16 kHz.
      //    decodeAudioData automatically resamples to this rate.
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = ctx;

      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

      // 3. Play through speakers so you can hear it
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      sourceNodeRef.current = source;

      source.onended = () => {
        // Clean up when audio finishes naturally
        if (sendTimerRef.current) {
          clearInterval(sendTimerRef.current);
          sendTimerRef.current = null;
        }
        sourceNodeRef.current = null;
        setPlaying(false);
        setStatus("Ready");
      };

      source.start();

      setLoadingAudio(false);
      setPlaying(true);
      setStatus(`▶ ${phrase.name}`);

      // 4. Send PCM to backend as Int16 chunks at real-time rate
      //    (identical to how useChat.jsx streams the microphone)
      const channelData = audioBuffer.getChannelData(0); // Float32 @ 16 kHz
      const int16 = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, channelData[i] * 32767));
      }

      let offset = 0;
      sendTimerRef.current = setInterval(() => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          clearInterval(sendTimerRef.current);
          sendTimerRef.current = null;
          return;
        }
        if (offset >= int16.length) {
          clearInterval(sendTimerRef.current);
          sendTimerRef.current = null;
          return;
        }
        const end = Math.min(offset + CHUNK_SIZE, int16.length);
        // slice returns a copy; .buffer is that copy's buffer — safe to transfer
        const chunk = int16.slice(offset, end);
        ws.send(chunk.buffer);
        offset = end;
      }, CHUNK_INTERVAL_MS);

    } catch (err) {
      console.error("[Simulator] Play error:", err);
      setStatus(`⚠ ${err.message.slice(0, 50)}`);
      setLoadingAudio(false);
      setPlaying(false);
    }
  }, [joined, phrases, phraseIdx, playing, stopStream]);

  // ── Phrase navigation ─────────────────────────────────────────────────────
  const goNext = useCallback(() => {
    if (playing) { stopStream(); setPlaying(false); }
    setPhraseIdx((i) => (i + 1) % phrases.length);
    if (voiceReadyRef.current) setStatus("Ready");
  }, [playing, phrases.length, stopStream]);

  const goPrev = useCallback(() => {
    if (playing) { stopStream(); setPlaying(false); }
    setPhraseIdx((i) => (i - 1 + phrases.length) % phrases.length);
    if (voiceReadyRef.current) setStatus("Ready");
  }, [playing, phrases.length, stopStream]);

  const currentPhrase = phrases[phraseIdx];

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Keyframe animation injected once */}
      <style>{`
        @keyframes sim-slide-in {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)    scale(1);    }
        }
        @keyframes sim-scan {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%);  }
        }
        @keyframes sim-pulse-dot {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.35; }
        }
      `}</style>

      <div
        role="dialog"
        aria-label="User 2 Simulator"
        style={{
          position:       "fixed",
          top:            "5.5rem",
          right:          "1.5rem",
          zIndex:         1000,
          width:          "300px",
          borderRadius:   "18px",
          background:     "rgba(7, 11, 22, 0.93)",
          border:         "1px solid rgba(148,163,184,0.14)",
          backdropFilter: "blur(24px)",
          boxShadow:      "0 20px 60px rgba(0,0,0,0.65), 0 0 0 1px rgba(99,102,241,0.08)",
          fontFamily:     "'DM Sans', sans-serif",
          overflow:       "hidden",
          animation:      "sim-slide-in 0.25s ease both",
        }}
      >
        {/* ── Header ────────────────────────────────────────────────────── */}
        <div
          style={{
            display:      "flex",
            alignItems:   "center",
            gap:          "8px",
            padding:      "10px 14px",
            background:   "rgba(15,23,42,0.75)",
            borderBottom: "1px solid rgba(148,163,184,0.09)",
          }}
        >
          {/* Live dot */}
          <span
            style={{
              width:       "7px",
              height:      "7px",
              borderRadius:"50%",
              flexShrink:  0,
              background:  joined ? (playing ? "#a5b4fc" : "#22c55e") : "#475569",
              boxShadow:   joined ? (playing ? "0 0 6px #a5b4fc" : "0 0 6px #22c55e") : "none",
              animation:   playing ? "sim-pulse-dot 1s ease-in-out infinite" : "none",
            }}
          />

          <span
            style={{
              fontSize:       "10px",
              fontWeight:     700,
              letterSpacing:  "0.18em",
              textTransform:  "uppercase",
              color:          joined ? "#94a3b8" : "#475569",
            }}
          >
            Simulator
          </span>

          {/* Status chip */}
          <span
            style={{
              marginLeft:   "auto",
              fontSize:     "10px",
              color:        playing ? "#a5b4fc" : voiceReady ? "#4ade80" : "#64748b",
              maxWidth:     "120px",
              overflow:     "hidden",
              textOverflow: "ellipsis",
              whiteSpace:   "nowrap",
            }}
            title={status}
          >
            {status}
          </span>

          {/* Close */}
          <button
            id="sim-close-btn"
            onClick={onClose}
            title="Close simulator"
            style={{
              background:  "none",
              border:      "none",
              cursor:      "pointer",
              color:       "#475569",
              fontSize:    "15px",
              lineHeight:  1,
              padding:     "0 0 0 8px",
              transition:  "color 0.15s",
              flexShrink:  0,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#94a3b8")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#475569")}
          >
            ✕
          </button>
        </div>

        {/* ── Body ──────────────────────────────────────────────────────── */}
        <div style={{ padding: "14px" }}>

          {/* Phrase card */}
          <div
            style={{
              background:   "rgba(255,255,255,0.035)",
              border:       `1px solid ${playing ? "rgba(99,102,241,0.3)" : "rgba(148,163,184,0.1)"}`,
              borderRadius: "12px",
              padding:      "12px 14px",
              marginBottom: "12px",
              position:     "relative",
              overflow:     "hidden",
              transition:   "border-color 0.25s",
            }}
          >
            {/* Scanning highlight when playing */}
            {playing && (
              <div
                style={{
                  position:   "absolute",
                  top:        0,
                  left:       0,
                  width:      "40%",
                  height:     "100%",
                  background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.07), transparent)",
                  animation:  "sim-scan 1.8s linear infinite",
                  pointerEvents: "none",
                }}
              />
            )}

            {/* Counter */}
            <div
              style={{
                fontSize:      "9px",
                fontWeight:    700,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color:         "#334155",
                marginBottom:  "5px",
              }}
            >
              {phraseIdx + 1} / {phrases.length}
            </div>

            {/* Phrase name */}
            <div
              style={{
                fontSize:   "15px",
                fontWeight: 700,
                color:      playing ? "#c7d2fe" : "#e2e8f0",
                transition: "color 0.2s",
                lineHeight: 1.2,
                marginBottom: "5px",
              }}
            >
              {currentPhrase?.name ?? "—"}
            </div>

            {/* Phrase preview text */}
            <div
              style={{
                fontSize:              "11px",
                color:                 "#475569",
                lineHeight:            1.5,
                overflow:              "hidden",
                display:               "-webkit-box",
                WebkitLineClamp:       2,
                WebkitBoxOrient:       "vertical",
              }}
            >
              {currentPhrase?.text ?? ""}
            </div>
          </div>

          {/* Controls row */}
          <div style={{ display: "flex", gap: "8px", alignItems: "stretch" }}>
            {/* Prev */}
            <button
              id="sim-prev-btn"
              onClick={goPrev}
              title="Previous phrase"
              style={btnStyle("ghost")}
              onMouseEnter={(e) => applyHover(e, true)}
              onMouseLeave={(e) => applyHover(e, false)}
            >
              <ChevronLeft />
            </button>

            {/* Play / Stop */}
            <button
              id="sim-play-btn"
              onClick={handlePlay}
              disabled={!joined || loadingAudio}
              title={playing ? "Stop" : "Play phrase"}
              style={{
                ...btnStyle(playing ? "stop" : "play"),
                flex: 1,
                opacity: (!joined || loadingAudio) ? 0.45 : 1,
                cursor:  (!joined || loadingAudio) ? "not-allowed" : "pointer",
              }}
            >
              {loadingAudio ? (
                <span style={{ fontSize: "12px" }}>…</span>
              ) : playing ? (
                <><StopIcon /><span>Stop</span></>
              ) : (
                <><PlayIcon /><span>Play</span></>
              )}
            </button>

            {/* Next */}
            <button
              id="sim-next-btn"
              onClick={goNext}
              title="Next phrase"
              style={btnStyle("ghost")}
              onMouseEnter={(e) => applyHover(e, true)}
              onMouseLeave={(e) => applyHover(e, false)}
            >
              <ChevronRight />
            </button>
          </div>

          {/* Thin progress bar — appears while playing */}
          <div
            style={{
              marginTop:    "10px",
              height:       "2px",
              borderRadius: "999px",
              background:   "rgba(255,255,255,0.05)",
              overflow:     "hidden",
              opacity:      playing ? 1 : 0,
              transition:   "opacity 0.3s",
            }}
          >
            <div
              style={{
                height:     "100%",
                width:      "35%",
                background: "linear-gradient(90deg, #6366f1, #0ea5e9)",
                borderRadius: "999px",
                animation:  playing ? "sim-scan 1.6s ease-in-out infinite" : "none",
              }}
            />
          </div>

          {/* Hint text */}
          <p
            style={{
              marginTop:  "10px",
              marginBottom: 0,
              fontSize:   "10px",
              color:      "#1e293b",
              textAlign:  "center",
              lineHeight: 1.4,
            }}
          >
            {!joined
              ? "Joining room…"
              : !voiceReady
              ? "Waiting for voice session to start…"
              : "Audio is sent to backend as real user mic data."}
          </p>
        </div>
      </div>
    </>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────
function btnStyle(variant) {
  const base = {
    display:        "flex",
    alignItems:     "center",
    justifyContent: "center",
    gap:            "6px",
    borderRadius:   "9px",
    fontSize:       "12px",
    fontWeight:     600,
    cursor:         "pointer",
    padding:        "8px 14px",
    transition:     "all 0.18s",
    border:         "1px solid",
    fontFamily:     "'DM Sans', sans-serif",
  };
  if (variant === "play") return {
    ...base,
    background:   "linear-gradient(135deg, rgba(99,102,241,0.25), rgba(14,165,233,0.22))",
    borderColor:  "rgba(99,102,241,0.4)",
    color:        "#c7d2fe",
  };
  if (variant === "stop") return {
    ...base,
    background:   "rgba(239,68,68,0.12)",
    borderColor:  "rgba(239,68,68,0.35)",
    color:        "#fca5a5",
  };
  // ghost
  return {
    ...base,
    background:   "rgba(255,255,255,0.04)",
    borderColor:  "rgba(148,163,184,0.14)",
    color:        "#64748b",
    padding:      "8px 12px",
  };
}

function applyHover(e, isEnter) {
  e.currentTarget.style.background   = isEnter ? "rgba(255,255,255,0.07)" : "rgba(255,255,255,0.04)";
  e.currentTarget.style.borderColor  = isEnter ? "rgba(148,163,184,0.25)" : "rgba(148,163,184,0.14)";
  e.currentTarget.style.color        = isEnter ? "#94a3b8" : "#64748b";
}
