// App.jsx
import { useState, useCallback, useRef, useEffect } from "react";
import { Loader } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Leva } from "leva";
import { Experience } from "./components/Experience";
import { UI } from "./components/UI";
import { useChat } from "./hooks/useChat";
import { ImageSegmenter, FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { MicTestModal } from "./components/MicTestModal";
import { SimulatorPanel } from "./components/SimulatorPanel";
import RankingBoard from "./components/RankingBoard";
import { useT, useLang, actionLabel } from "./i18n";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";

// ── Join Modal ──────────────────────────────────────────────────────────────
function JoinModal({ onJoin }) {
  const t = useT();
  const [name, setName] = useState("");
  const [showMicTest, setShowMicTest] = useState(false);

  const handleSubmit = () => {
    if (name.trim()) onJoin(name.trim());
  };

  return (
    <>
      {showMicTest && <MicTestModal onClose={() => setShowMicTest(false)} />}

      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
        <div
          className="relative w-full max-w-sm mx-4 rounded-2xl p-8 shadow-2xl"
          style={{
            background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
            border: "1px solid rgba(148,163,184,0.15)",
          }}
        >
          {/* Glow accent */}
          <div
            className="absolute -top-px left-1/2 -translate-x-1/2 h-px w-3/4"
            style={{
              background:
                "linear-gradient(90deg, transparent, #38bdf8, transparent)",
            }}
          />

          <h2
            className="mb-1 text-xl font-bold tracking-tight text-white"
            style={{ fontFamily: "'DM Sans', sans-serif" }}
          >
            {t("join.title", "Join Meeting")}
          </h2>
          <p className="mb-6 text-sm text-slate-400">
            {t("join.subtitle", "Enter your display name to enter the room.")}
          </p>

          <input
            autoFocus
            type="text"
            placeholder={t("join.placeholder", "Your name…")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            className="w-full rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 outline-none focus:ring-2 focus:ring-sky-500/50 transition"
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(148,163,184,0.15)",
            }}
          />

          {/* Test mic — subtle link-style button */}
          <button
            onClick={() => setShowMicTest(true)}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-all"
            style={{
              background: "rgba(56,189,248,0.07)",
              border: "1px solid rgba(56,189,248,0.18)",
              color: "#7dd3fc",
              cursor: "pointer",
            }}
          >
            <span>🎙</span> {t("join.testMic", "Test my mic before joining")}
          </button>

          <button
            onClick={handleSubmit}
            disabled={!name.trim()}
            className="mt-3 w-full rounded-lg py-3 text-sm font-semibold text-white transition-all"
            style={{
              background: name.trim()
                ? "linear-gradient(135deg, #0ea5e9, #6366f1)"
                : "rgba(148,163,184,0.15)",
              cursor: name.trim() ? "pointer" : "not-allowed",
            }}
          >
            {t("join.button", "Join →")}
          </button>
        </div>
      </div>
    </>
  );
}

// ── Entropy Chart ───────────────────────────────────────────────────────────
function EntropyChart({ data }) {
  const t = useT();
  const width = 100;
  const height = 30;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - (d / 100) * height;
    return `${x},${y}`;
  }).join(" ");

  const latestValue = data[data.length - 1] || 0;
  const color = latestValue > 60 ? "#22c55e" : latestValue > 30 ? "#eab308" : "#ef4444";

  return (
    <div className="absolute top-4 right-4 z-20 flex flex-col items-end gap-1">
      <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color, textShadow: "0 1px 2px rgba(0,0,0,0.8)" }}>
        {t("entropy", "Entropy")}: {Math.round(latestValue)}%
      </div>
      <svg width={width} height={height} className="overflow-visible opacity-90" viewBox={`0 0 ${width} ${height}`}>
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="4"
          filter="blur(4px)"
          opacity="0.6"
        />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

// ── Webcam Video Feed ───────────────────────────────────────────────────────
function WebcamFeed({ stream, mirror = false, applyBlur = false, isMe = false, isSpeaking = false, onEntropyUpdate }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const rafRef = useRef(null);
  const segmenterRef = useRef(null);
  const faceLandmarkerRef = useRef(null);

  const isSpeakingRef = useRef(isSpeaking);
  useEffect(() => {
    isSpeakingRef.current = isSpeaking;
  }, [isSpeaking]);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !stream) return;

    let cancelled = false;

    async function init() {
      if (!applyBlur && !isMe) {
        video.srcObject = stream;
        video.style.display = "block";
        if (canvas) canvas.style.display = "none";
        video.play().catch(console.error);
        return;
      }

      const vision = await FilesetResolver.forVisionTasks("/mediapipe-wasm");

      if (applyBlur) {
        segmenterRef.current = await ImageSegmenter.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath: "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          outputCategoryMask: false,
          outputConfidenceMasks: true,
        });
      }

      if (isMe) {
        faceLandmarkerRef.current = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          numFaces: 1
        });
      }

      if (cancelled) return;

      video.srcObject = stream;
      video.style.display = applyBlur ? "none" : "block";
      if (canvas) canvas.style.display = applyBlur ? "block" : "none";
      await video.play();

      let blurCanvas, blurCtx, ctx;
      if (applyBlur) {
        blurCanvas = document.createElement("canvas");
        blurCtx = blurCanvas.getContext("2d", { willReadFrequently: true });
        ctx = canvas.getContext("2d", { willReadFrequently: true });
      }

      let lastTime = -1;
      let lastEntropyTime = 0;

      function render(now) {
        if (cancelled) return;
        rafRef.current = requestAnimationFrame(render);

        if (video.readyState < 2 || now === lastTime) return;
        lastTime = now;

        const w = video.videoWidth;
        const h = video.videoHeight;
        if (!w || !h) return;

        // --- Entropy Tracking (Every ~200ms) ---
        if (isMe && faceLandmarkerRef.current && (now - lastEntropyTime > 200)) {
          lastEntropyTime = now;
          let focusScore = 0.0;
          const faceResult = faceLandmarkerRef.current.detectForVideo(video, now);
          if (faceResult.faceLandmarks && faceResult.faceLandmarks.length > 0) {
            const landmarks = faceResult.faceLandmarks[0];
            const nose = landmarks[1];
            const leftEye = landmarks[133];
            const rightEye = landmarks[362];
            const distLeft = Math.abs(nose.x - leftEye.x);
            const distRight = Math.abs(nose.x - rightEye.x);
            const min = Math.min(distLeft, distRight);
            const max = Math.max(distLeft, distRight);
            const ratio = max === 0 ? 0 : min / max;
            focusScore = ratio;
          }

          const isSpk = isSpeakingRef.current;
          const speakingBonus = isSpk ? 30 : 0;
          const entropy = Math.min(100, Math.max(0, (focusScore * 70) + speakingBonus));
          if (onEntropyUpdate) onEntropyUpdate(entropy);
        }

        // --- Background Blur ---
        if (applyBlur && segmenterRef.current) {
          if (canvas.width !== w) {
            canvas.width = w;
            canvas.height = h;
            blurCanvas.width = w;
            blurCanvas.height = h;
          }

          const result = segmenterRef.current.segmentForVideo(video, now);
          const masks = result.confidenceMasks;
          if (!masks || masks.length === 0) return;

          const personMask = masks[0];
          const maskFloat = personMask.getAsFloat32Array();

          blurCtx.filter = "blur(18px)";
          blurCtx.drawImage(video, 0, 0, w, h);
          blurCtx.filter = "none";
          const bgPixels = blurCtx.getImageData(0, 0, w, h);

          blurCtx.drawImage(video, 0, 0, w, h);
          const fgPixels = blurCtx.getImageData(0, 0, w, h);

          const out = ctx.createImageData(w, h);
          const out32 = new Uint32Array(out.data.buffer);
          const fg32 = new Uint32Array(fgPixels.data.buffer);
          const bg32 = new Uint32Array(bgPixels.data.buffer);

          for (let i = 0; i < maskFloat.length; i++) {
            const alpha = maskFloat[i];
            const fg = fg32[i];
            const bg = bg32[i];

            if (alpha > 0.95) { out32[i] = fg; continue; }
            if (alpha < 0.05) { out32[i] = bg; continue; }

            const fgR = fg & 0xff;
            const fgG = (fg >> 8) & 0xff;
            const fgB = (fg >> 16) & 0xff;

            const bgR = bg & 0xff;
            const bgG = (bg >> 8) & 0xff;
            const bgB = (bg >> 16) & 0xff;

            const r = fgR * alpha + bgR * (1 - alpha);
            const g = fgG * alpha + bgG * (1 - alpha);
            const b = fgB * alpha + bgB * (1 - alpha);

            out32[i] = (255 << 24) | (b << 16) | (g << 8) | r;
          }

          if (mirror) {
            const tmp = document.createElement("canvas");
            tmp.width = w;
            tmp.height = h;
            const tCtx = tmp.getContext("2d");
            tCtx.putImageData(out, 0, 0);
            ctx.save();
            ctx.translate(w, 0);
            ctx.scale(-1, 1);
            ctx.drawImage(tmp, 0, 0);
            ctx.restore();
          } else {
            ctx.putImageData(out, 0, 0);
          }
          masks.forEach((m) => m.close());
        }
      }

      rafRef.current = requestAnimationFrame(render);
    }

    init().catch(console.error);

    return () => {
      cancelled = true;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      segmenterRef.current?.close();
      segmenterRef.current = null;
      faceLandmarkerRef.current?.close();
      faceLandmarkerRef.current = null;
      video.srcObject = null;
    };
  }, [stream, mirror, applyBlur, isMe]);

  return (
    <>
      <video
        ref={videoRef}
        playsInline
        muted={applyBlur || isMe}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          borderRadius: "inherit",
          transform: mirror ? "scaleX(-1)" : "none",
          display: applyBlur ? "none" : "block"
        }}
      />
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
          borderRadius: "inherit",
          transform: "none",
          display: applyBlur ? "block" : "none"
        }}
      />
    </>
  );
}

// ── Participant Cell ────────────────────────────────────────────────────────
function ParticipantCell({
  participant,
  isMe,
  micActive,
  onToggleMic,
  webcamActive,
  webcamStream,
  onToggleWebcam,
}) {
  const { updateEntropy, participantEntropies } = useChat();
  const t = useT();
  const [blurActive, setBlurActive] = useState(false);
  const [entropyHistory, setEntropyHistory] = useState(Array(50).fill(0));

  const handleEntropyUpdate = useCallback((val) => {
    setEntropyHistory(prev => [...prev.slice(1), val]);
    updateEntropy(val);
  }, [updateEntropy]);

  // Sync from backend for remote users
  const remoteEntropy = participantEntropies[participant.sessionId];
  useEffect(() => {
    if (!isMe && remoteEntropy !== undefined) {
      setEntropyHistory(prev => [...prev.slice(1), remoteEntropy]);
    }
  }, [isMe, remoteEntropy]);

  const initial = participant.name.charAt(0).toUpperCase();
  const hue = (participant.name.charCodeAt(0) * 37) % 360;

  // We show the chart if we have data for the remote user, or if local webcam is active
  const shouldShowChart = isMe ? webcamActive : (remoteEntropy !== undefined);

  // Check if the stream actually has a video track
  const hasVideo = isMe 
    ? webcamActive 
    : !!(webcamStream && webcamStream.getVideoTracks().length > 0);

  // A ref to play remote audio reliably
  const audioRef = useRef(null);
  useEffect(() => {
    if (!isMe && webcamStream && audioRef.current) {
      if (audioRef.current.srcObject !== webcamStream) {
        audioRef.current.srcObject = webcamStream;
        audioRef.current.play().catch(e => console.error("Audio play failed:", e));
      }
    }
  }, [isMe, webcamStream]);

  return (
    <div
      className="relative flex h-full flex-col items-center justify-center gap-4 rounded-3xl overflow-hidden"
      style={{
        background:
          "linear-gradient(135deg, rgba(15,23,42,0.85), rgba(30,41,59,0.7))",
        border: "1px solid rgba(148,163,184,0.12)",
        backdropFilter: "blur(12px)",
      }}
    >
      {/* Entropy Chart overlay */}
      {shouldShowChart && (
        <EntropyChart data={entropyHistory} />
      )}

      {/* Remote Audio Player (Always active if remote stream exists) */}
      {!isMe && webcamStream && (
        <audio ref={audioRef} autoPlay playsInline style={{ display: "none" }} />
      )}

      {/* Webcam video fill — renders behind everything when active */}
      {hasVideo && webcamStream && (
        <WebcamFeed
          stream={webcamStream}
          mirror={isMe}
          applyBlur={blurActive}
          isMe={isMe}
          isSpeaking={participant.micActive}
          onEntropyUpdate={isMe ? handleEntropyUpdate : undefined}
        />
      )}

      {/* Subtle animated ring when speaking (mic on) */}
      {participant.micActive && (
        <div
          className="absolute inset-0 rounded-3xl pointer-events-none animate-pulse"
          style={{
            boxShadow: `inset 0 0 0 1.5px hsla(${hue},70%,60%,0.35)`,
          }}
        />
      )}

      {/* Avatar circle — hidden when webcam is active */}
      {!hasVideo && (
        <div
          className="flex h-14 w-14 items-center justify-center rounded-full text-xl font-bold text-white shadow-lg"
          style={{
            background: `linear-gradient(135deg, hsl(${hue},65%,40%), hsl(${hue + 40
              },65%,50%))`,
          }}
        >
          {initial}
        </div>
      )}

      {/* Name + role — always visible, floated to bottom when webcam on */}
      <div
        className="text-center"
        style={
          hasVideo
            ? {
              position: "absolute",
              bottom: "1rem",
              left: 0,
              right: 0,
              zIndex: 10,
            }
            : {}
        }
      >
        <p
          className="text-sm font-semibold"
          style={{
            color: isMe && hasVideo ? "#fff" : "#f1f5f9",
            textShadow:
              isMe && hasVideo ? "0 1px 4px rgba(0,0,0,0.7)" : "none",
          }}
        >
          {participant.name}
          {isMe && (
            <span className="ml-2 rounded-full bg-sky-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-sky-300">
              {t("cell.you", "You")}
            </span>
          )}
        </p>
        <p
          className="mt-0.5 text-[11px] uppercase tracking-[0.2em]"
          style={{
            color:
              isMe && hasVideo
                ? "rgba(255,255,255,0.6)"
                : "rgb(100,116,139)",
          }}
        >
          {t("cell.participant", "Participant")}
        </p>

        {/* Controls row */}
        <div
          className="mt-2 flex flex-wrap items-center justify-center gap-2"
          style={{ position: "relative", zIndex: 10 }}
        >
          {isMe ? (
            <>
              {/* Mic toggle */}
              <button
                onClick={onToggleMic}
                className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all"
                style={{
                  background: micActive
                    ? "rgba(34,197,94,0.15)"
                    : "rgba(239,68,68,0.15)",
                  border: micActive
                    ? "1px solid rgba(34,197,94,0.35)"
                    : "1px solid rgba(239,68,68,0.35)",
                  color: micActive ? "#86efac" : "#fca5a5",
                  backdropFilter: "blur(8px)",
                }}
                title={micActive ? t("cell.muteTitle", "Mute your mic") : t("cell.unmuteTitle", "Unmute your mic")}
              >
                {micActive ? (
                  <>
                    <MicOnIcon /> {t("cell.mute", "Mute")}
                  </>
                ) : (
                  <>
                    <MicOffIcon /> {t("cell.unmute", "Unmute")}
                  </>
                )}
              </button>

              {/* Webcam toggle */}
              <button
                onClick={onToggleWebcam}
                className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all"
                style={{
                  background: webcamActive
                    ? "rgba(99,102,241,0.2)"
                    : "rgba(148,163,184,0.1)",
                  border: webcamActive
                    ? "1px solid rgba(99,102,241,0.45)"
                    : "1px solid rgba(148,163,184,0.25)",
                  color: webcamActive ? "#a5b4fc" : "#94a3b8",
                  backdropFilter: "blur(8px)",
                }}
                title={webcamActive ? t("cell.camOffTitle", "Turn off camera") : t("cell.camOnTitle", "Turn on camera")}
              >
                {webcamActive ? (
                  <>
                    <CamOnIcon /> {t("cell.camOff", "Cam off")}
                  </>
                ) : (
                  <>
                    <CamOffIcon /> {t("cell.camOn", "Cam on")}
                  </>
                )}
              </button>
            </>
          ) : (
            /* Read-only mic indicator for others */
            <div
              className="flex items-center justify-center gap-1 rounded-full px-3 py-1.5 text-xs"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: participant.micActive ? "#86efac" : "#fca5a5",
                backdropFilter: "blur(8px)",
              }}
            >
              {participant.micActive ? <MicOnIcon /> : <MicOffIcon />}
              <span>{participant.micActive ? t("cell.live", "Live") : t("cell.muted", "Muted")}</span>
            </div>
          )}

          {/* Blur toggle */}
          {hasVideo && (
            <button
              onClick={() => setBlurActive(!blurActive)}
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all"
              style={{
                background: blurActive
                  ? "rgba(168,85,247,0.2)"
                  : "rgba(148,163,184,0.1)",
                border: blurActive
                  ? "1px solid rgba(168,85,247,0.45)"
                  : "1px solid rgba(148,163,184,0.25)",
                color: blurActive ? "#d8b4fe" : "#94a3b8",
                backdropFilter: "blur(8px)",
              }}
              title={blurActive ? t("cell.blurOffTitle", "Turn off background blur") : t("cell.blurOnTitle", "Turn on background blur")}
            >
              {blurActive ? (
                <>
                  <BlurOnIcon /> {t("cell.blurOn", "Blur on")}
                </>
              ) : (
                <>
                  <BlurOffIcon /> {t("cell.blurOff", "Blur off")}
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Facilitator Status Box (collapsible) ──────────────────────────────────
const LOG_LEVEL_STYLES = {
  info:    { color: "#94a3b8", prefix: "" },
  success: { color: "#4ade80", prefix: "✓" },
  warning: { color: "#fbbf24", prefix: "⚠" },
  error:   { color: "#f87171", prefix: "✗" },
};

function FacilitatorStatusBox({ logs, voiceSessionActive }) {
  const t = useT();
  const [open, setOpen] = useState(false); // closed by default
  const bottomRef = useRef(null);

  // Auto-scroll to bottom whenever new logs arrive (only when open)
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, open]);

  return (
    <div
      style={{
        position: "absolute",
        bottom: "1rem",
        left: "1rem",
        right: "1rem",
        zIndex: 20,
        borderRadius: "14px",
        overflow: "hidden",
        background: "rgba(7, 11, 22, 0.80)",
        border: "1px solid rgba(148,163,184,0.12)",
        backdropFilter: "blur(14px)",
        boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
        display: "flex",
        flexDirection: "column",
        maxHeight: open ? "38%" : undefined,
      }}
    >
      {/* ── Header / toggle bar ── */}
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "7px 10px",
          background: "rgba(15,23,42,0.7)",
          border: "none",
          borderBottom: open ? "1px solid rgba(148,163,184,0.1)" : "none",
          cursor: "pointer",
          width: "100%",
          textAlign: "left",
          flexShrink: 0,
        }}
      >
        {/* Pulsing live dot */}
        <span
          style={{
            display: "inline-block",
            width: "7px",
            height: "7px",
            borderRadius: "50%",
            background: voiceSessionActive ? "#4ade80" : "#475569",
            boxShadow: voiceSessionActive ? "0 0 6px #4ade80" : "none",
            animation: voiceSessionActive ? "pulse 1.6s ease-in-out infinite" : "none",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: voiceSessionActive ? "#94a3b8" : "#475569",
            fontFamily: "'DM Mono', 'Fira Mono', monospace",
          }}
        >
          {t("fac.log", "Facilitator Log")}
        </span>

        {/* LIVE label */}
        {voiceSessionActive && (
          <span
            style={{
              fontSize: "9px",
              fontWeight: 700,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "#4ade80",
              fontFamily: "'DM Mono', monospace",
            }}
          >
            {t("fac.live", "LIVE")}
          </span>
        )}

        {/* Chevron toggle */}
        <span
          style={{
            marginLeft: "auto",
            color: "#475569",
            fontSize: "12px",
            lineHeight: 1,
            transition: "transform 0.2s",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            display: "inline-block",
          }}
        >
          ▾
        </span>
      </button>

      {/* ── Log entries (only rendered when open) ── */}
      {open && (
        <div
          style={{
            overflowY: "auto",
            padding: "8px 12px",
            display: "flex",
            flexDirection: "column",
            gap: "3px",
            fontFamily: "'DM Mono', 'Fira Mono', 'Courier New', monospace",
            fontSize: "11px",
            lineHeight: "1.5",
            scrollbarWidth: "thin",
            scrollbarColor: "rgba(148,163,184,0.2) transparent",
            flex: 1,
          }}
        >
          {logs.length === 0 ? (
            <span style={{ color: "#334155", fontStyle: "italic" }}>
              {t("fac.waiting", "Waiting for session to start…")}
            </span>
          ) : (
            logs.map((entry) => {
              const { color, prefix } = LOG_LEVEL_STYLES[entry.level] ?? LOG_LEVEL_STYLES.info;
              const time = new Date(entry.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              });
              return (
                <div key={entry.id} style={{ display: "flex", gap: "8px", alignItems: "flex-start" }}>
                  <span style={{ color: "#334155", flexShrink: 0, fontSize: "10px", paddingTop: "1px" }}>
                    {time}
                  </span>
                  {prefix && (
                    <span style={{ color, flexShrink: 0, fontWeight: 700 }}>{prefix}</span>
                  )}
                  <span style={{ color, wordBreak: "break-word" }}>{entry.message}</span>
                </div>
              );
            })
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

// ── Action Badge ─────────────────────────────────────────────────────────────
const ACTION_STYLES = {
  NO_ACTION:  { bg: "rgba(71,85,105,0.55)",  border: "rgba(100,116,139,0.35)", color: "#94a3b8",  icon: "—"  },
  LITE:       { bg: "rgba(251,191,36,0.2)",  border: "rgba(251,191,36,0.45)",  color: "#fde68a",  icon: "⚡"  },
  MEDIATE:    { bg: "rgba(99,102,241,0.25)",  border: "rgba(99,102,241,0.5)",   color: "#a5b4fc",  icon: "⚖"  },
  ENCOURAGE:  { bg: "rgba(34,197,94,0.2)",   border: "rgba(34,197,94,0.45)",   color: "#86efac",  icon: "✦"  },
  SUMMARIZE:  { bg: "rgba(14,165,233,0.2)",  border: "rgba(14,165,233,0.45)",  color: "#7dd3fc",  icon: "≡"  },
  REDIRECT:   { bg: "rgba(251,191,36,0.2)",  border: "rgba(251,191,36,0.45)",  color: "#fde68a",  icon: "→"  },
  CLARIFY:    { bg: "rgba(168,85,247,0.22)", border: "rgba(168,85,247,0.45)",  color: "#d8b4fe",  icon: "?"  },
  INTERVENE:  { bg: "rgba(239,68,68,0.2)",   border: "rgba(239,68,68,0.4)",    color: "#fca5a5",  icon: "!"  },
  UNKNOWN:    { bg: "rgba(71,85,105,0.3)",   border: "rgba(100,116,139,0.25)", color: "#64748b",  icon: "~"  },
};

function ActionBadge({ action }) {
  const t = useT();
  const lang = useLang();
  // Always visible — show a placeholder when idle
  const isIdle = !action;
  const style = !isIdle
    ? (ACTION_STYLES[action] ?? ACTION_STYLES.UNKNOWN)
    : { bg: "rgba(30,41,59,0.5)", border: "rgba(71,85,105,0.25)", color: "#334155", icon: "" };

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "3px 10px 3px 8px",
        borderRadius: "999px",
        background: style.bg,
        border: `1px solid ${style.border}`,
        backdropFilter: "blur(8px)",
        transition: "all 0.35s ease",
        flexShrink: 0,
      }}
    >
      {style.icon && (
        <span style={{ fontSize: "11px", lineHeight: 1 }}>{style.icon}</span>
      )}
      <span
        style={{
          fontSize: "9px",
          fontWeight: 700,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: style.color,
          fontFamily: "'DM Mono', 'Fira Mono', monospace",
          transition: "color 0.35s ease",
        }}
      >
        {isIdle ? t("fac.idle", "IDLE") : actionLabel(lang, action)}
      </span>
    </div>
  );
}


function EmptyCell() {
  const t = useT();
  return (
    <div
      className="flex h-full flex-col items-center justify-center rounded-3xl"
      style={{
        background: "rgba(15,23,42,0.4)",
        border: "1px dashed rgba(148,163,184,0.12)",
      }}
    >
      <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-slate-800/60">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4 text-slate-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
          />
        </svg>
      </div>
      <span className="text-xs uppercase tracking-[0.25em] text-slate-600">
        {t("cell.empty", "Empty")}
      </span>
    </div>
  );
}

// ── Lite Avatar View ─────────────────────────────────────────────────────────
function LiteAvatarView({ roomState }) {
  const t = useT();
  // Color + behaviour per state
  const stateConfig = {
    idle:       { color: "#6366f1", glow: "rgba(99,102,241,0.35)",  label: t("state.idle", "Idle"),       bars: 4 },
    listening:  { color: "#22c55e", glow: "rgba(34,197,94,0.45)",   label: t("state.listening", "Listening"),  bars: 7 },
    processing: { color: "#f59e0b", glow: "rgba(245,158,11,0.45)",  label: t("state.processing", "Thinking"),   bars: 5 },
    speaking:   { color: "#38bdf8", glow: "rgba(56,189,248,0.5)",   label: t("state.speaking", "Speaking"),   bars: 9 },
  };
  const cfg = stateConfig[roomState] ?? stateConfig.idle;

  const styleTag = `
    @keyframes lite-pulse {
      0%, 100% { transform: scale(1);   opacity: 0.7; }
      50%       { transform: scale(1.18); opacity: 1;   }
    }
    @keyframes lite-ring {
      0%   { transform: scale(0.85); opacity: 0.6; }
      50%  { transform: scale(1.35); opacity: 0;   }
      100% { transform: scale(0.85); opacity: 0;   }
    }
    @keyframes lite-bar {
      0%, 100% { transform: scaleY(0.25); }
      50%      { transform: scaleY(1);    }
    }
  `;

  const numBars = cfg.bars;
  const bars = Array.from({ length: numBars });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "28px",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <style>{styleTag}</style>

      {/* Ambient background glow */}
      <div
        style={{
          position: "absolute",
          width: "300px",
          height: "300px",
          borderRadius: "50%",
          background: `radial-gradient(circle, ${cfg.glow} 0%, transparent 70%)`,
          transition: "background 0.6s ease",
          pointerEvents: "none",
        }}
      />

      {/* Outer pulsing rings */}
      {[1, 2].map((i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            width: `${90 + i * 55}px`,
            height: `${90 + i * 55}px`,
            borderRadius: "50%",
            border: `1px solid ${cfg.color}`,
            opacity: roomState === "idle" ? 0 : 0.4,
            animation: roomState !== "idle" ? `lite-ring ${1.2 + i * 0.5}s ease-out ${i * 0.3}s infinite` : "none",
            transition: "opacity 0.4s",
            pointerEvents: "none",
          }}
        />
      ))}

      {/* Core orb */}
      <div
        style={{
          position: "relative",
          width: "80px",
          height: "80px",
          borderRadius: "50%",
          background: `radial-gradient(circle at 35% 35%, ${cfg.color}cc, ${cfg.color}55)`,
          boxShadow: `0 0 32px ${cfg.glow}, 0 0 8px ${cfg.color}88`,
          animation: "lite-pulse 2s ease-in-out infinite",
          transition: "background 0.6s ease, box-shadow 0.6s ease",
          flexShrink: 0,
        }}
      />

      {/* Sound bars — visible when listening or speaking */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "5px",
          height: "40px",
          opacity: (roomState === "listening" || roomState === "speaking") ? 1 : 0.2,
          transition: "opacity 0.4s",
        }}
      >
        {bars.map((_, i) => {
          const delay = (i / numBars) * 0.9;
          const dur = 0.5 + (i % 3) * 0.2;
          return (
            <div
              key={i}
              style={{
                width: "4px",
                height: "100%",
                borderRadius: "2px",
                background: cfg.color,
                transformOrigin: "center",
                animation: (roomState === "listening" || roomState === "speaking")
                  ? `lite-bar ${dur}s ease-in-out ${delay}s infinite`
                  : "none",
                transform: "scaleY(0.25)",
                transition: "background 0.5s",
              }}
            />
          );
        })}
      </div>

      {/* State label */}
      <div
        style={{
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "0.25em",
          textTransform: "uppercase",
          color: cfg.color,
          fontFamily: "'DM Mono', 'Fira Mono', monospace",
          opacity: 0.8,
          transition: "color 0.5s",
        }}
      >
        {cfg.label}
      </div>
    </div>
  );
}

// ── Lite Audio Player ────────────────────────────────────────────────────────
// Handles audio playback and onMessagePlayed() when the 3D Avatar is absent.
function LiteAudioPlayer() {
  const { message, onMessagePlayed } = useChat();
  const audioCtxRef = useRef(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!message) return;

    const audio = message.audioEl
      ? message.audioEl
      : (() => {
          const mimeType = message.audio?.startsWith("UklGR") ? "audio/wav" : "audio/mpeg";
          return new Audio(`data:${mimeType};base64,${message.audio}`);
        })();

    // Set up AudioContext (needed to unlock autoplay in browsers)
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") ctx.resume();

    try {
      if (sourceRef.current) sourceRef.current.disconnect();
      const source = ctx.createMediaElementSource(audio);
      source.connect(ctx.destination);
      sourceRef.current = source;
    } catch (e) {
      // Already connected — ignore
    }

    audio.play().catch((err) => {
      console.error("[LiteAudioPlayer] play error:", err);
      // Still need to call onMessagePlayed so the queue doesn't jam
      onMessagePlayed();
    });

    audio.onended = () => {
      onMessagePlayed();
      if (sourceRef.current) {
        try { sourceRef.current.disconnect(); } catch (_) {}
      }
    };
  }, [message]); // eslint-disable-line react-hooks/exhaustive-deps

  return null; // renders nothing
}

// ── Icon helpers ────────────────────────────────────────────────────────────
function MicOnIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
      />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.531V19.94a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.506-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.395C2.806 8.757 3.63 8.25 4.51 8.25H6.75z"
      />
    </svg>
  );
}

function CamOnIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
      />
    </svg>
  );
}

function CamOffIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-3.5 w-3.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M12 18.75H4.5a2.25 2.25 0 01-2.25-2.25v-9m12.75 0A2.25 2.25 0 0012.75 5.25h-1.5M3 3l18 18"
      />
    </svg>
  );
}

function BlurOnIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12a3 3 0 116 0 3 3 0 01-6 0z" />
    </svg>
  );
}

function BlurOffIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12a3 3 0 116 0 3 3 0 01-6 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 4.5l15 15" />
    </svg>
  );
}

// ── App ─────────────────────────────────────────────────────────────────────
function App() {
  const {
    sessionId,
    myName,
    participants,
    micActive,
    joinRoom,
    leaveRoom,
    toggleMic,
    // Now from useChat instead of local state:
    webcamActive,
    webcamStream,
    toggleWebcam,
    remoteStreams,
    facilitatorLogs,
    voiceSessionActive,
    lastFacilitatorAction,
    roomState,
    facilitatorMode,
    toggleFacilitatorMode,
    modeLoading,
    language,
    languageLoading,
    toggleLanguage,
  } = useChat();
  const t = useT();

  const [showJoinModal, setShowJoinModal] = useState(false);
  const [showSimulator, setShowSimulator] = useState(false);
  const isJoined = !!sessionId;

  // ── Ping Backend ─────────────────────────────────────────────────────────
  const [pingStatus, setPingStatus] = useState("idle"); // "idle" | "pinging" | "success" | "error"

  const handlePing = async () => {
    setPingStatus("pinging");
    try {
      const res = await fetch(`${BACKEND_URL}/api`);
      if (res.ok) {
        setPingStatus("success");
        setTimeout(() => setPingStatus("idle"), 3000);
      } else {
        setPingStatus("error");
        setTimeout(() => setPingStatus("idle"), 3000);
      }
    } catch (e) {
      setPingStatus("error");
      setTimeout(() => setPingStatus("idle"), 3000);
    }
  };

  const handleJoin = useCallback(
    (name) => {
      joinRoom(name);
      setShowJoinModal(false);
    },
    [joinRoom],
  );

  const handleLeave = useCallback(() => {
    leaveRoom();
  }, [leaveRoom, webcamStream]);

  const participantSlots = [participants[0] ?? null, participants[1] ?? null];

  return (
    <>
      <Loader />
      <Leva hidden />
      <RankingBoard />
      {facilitatorMode === "lite" && <LiteAudioPlayer />}

      {showJoinModal && <JoinModal onJoin={handleJoin} />}
      {showSimulator && isJoined && (
        <SimulatorPanel onClose={() => setShowSimulator(false)} />
      )}

      {/* Shell: shrinks from the right while the ranking drawer is open (--ranking-offset set by RankingBoard).
          The transform makes it the containing block for fixed children such as <UI />. */}
      <div
        id="app-shell"
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          bottom: 0,
          right: "var(--ranking-offset, 0px)",
          transition: "right 0.25s ease",
          transform: "translateZ(0)",
          overflow: "hidden",
        }}
      >
      <UI />
      <main
        className="h-screen overflow-hidden flex flex-col p-4 md:p-6 lg:p-10"
        style={{ fontFamily: "'DM Sans', sans-serif" }}
      >
        {/* ── Header bar ─────────────────────────────────────────────────── */}
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className="flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold"
              style={{
                background: "rgba(15,23,42,0.7)",
                border: "1px solid rgba(148,163,184,0.15)",
                color: "#94a3b8",
                backdropFilter: "blur(8px)",
              }}
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{
                  background: isJoined ? "#22c55e" : "#64748b",
                  boxShadow: isJoined ? "0 0 6px #22c55e" : "none",
                }}
              />
              {isJoined
                ? (language === "vi"
                  ? `${participants.length} ${t("hdr.participants", "participants in room")}`
                  : `${participants.length} participant${participants.length !== 1 ? "s" : ""} in room`)
                : t("hdr.notInRoom", "Not in room")}
            </div>

            {isJoined && myName && (
              <div
                className="rounded-full px-3 py-1.5 text-xs font-semibold text-sky-300"
                style={{
                  background: "rgba(14,165,233,0.1)",
                  border: "1px solid rgba(14,165,233,0.25)",
                }}
              >
                {t("hdr.joinedAs", "Joined as")} {myName}
              </div>
            )}
            
            {/* Ping Button */}
            <button
              onClick={handlePing}
              disabled={pingStatus === "pinging"}
              className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold transition-all shadow-lg ${
                pingStatus === "pinging" ? "animate-pulse" : "hover:scale-105 active:scale-95"
              }`}
              style={{
                background: pingStatus === "pinging" 
                  ? "linear-gradient(135deg, #f59e0b, #d97706)" 
                  : pingStatus === "success" 
                    ? "linear-gradient(135deg, #22c55e, #16a34a)" 
                    : pingStatus === "error" 
                      ? "linear-gradient(135deg, #ef4444, #dc2626)" 
                      : "linear-gradient(135deg, #0ea5e9, #4f46e5)",
                color: "#ffffff",
                boxShadow: pingStatus === "pinging"
                  ? "0 0 20px rgba(245, 158, 11, 0.5)"
                  : pingStatus === "success"
                    ? "0 0 20px rgba(34, 197, 94, 0.5)"
                    : pingStatus === "error"
                      ? "0 0 20px rgba(239, 68, 68, 0.5)"
                      : "0 0 20px rgba(14, 165, 233, 0.5)",
                textShadow: "0 1px 3px rgba(0,0,0,0.6)",
                letterSpacing: "0.05em",
                cursor: pingStatus === "pinging" ? "wait" : "pointer",
                border: "1px solid rgba(255,255,255,0.2)",
              }}
              title={t("hdr.pingTitle", "Ping backend to wake it up from Render free tier sleep")}
            >
              {pingStatus === "pinging" ? t("hdr.waking", "Waking up...") : pingStatus === "success" ? t("hdr.awake", "Backend Awake ✓") : pingStatus === "error" ? t("hdr.pingFail", "Ping Failed ✗") : t("hdr.wake", "Wake Backend")}
            </button>
          </div>

          {isJoined ? (
            <div className="flex flex-wrap items-center gap-2">
              {/* Language toggle (EN / VI) — shared by the whole room */}
              <button
                id="lang-toggle-btn"
                onClick={toggleLanguage}
                disabled={languageLoading}
                title={language === "vi" ? "Switch to English" : "Chuyển sang tiếng Việt"}
                className="flex items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold transition-all"
                style={{
                  background: language === "vi" ? "rgba(239,68,68,0.15)" : "rgba(148,163,184,0.08)",
                  border: language === "vi" ? "1px solid rgba(239,68,68,0.4)" : "1px solid rgba(148,163,184,0.18)",
                  color: language === "vi" ? "#fca5a5" : "#94a3b8",
                  opacity: languageLoading ? 0.6 : 1,
                  cursor: languageLoading ? "not-allowed" : "pointer",
                }}
              >
                🌐 {language === "vi" ? "VI · Tiếng Việt" : "EN · English"}
              </button>

              {/* Mode toggle */}
              <button
                id="mode-toggle-btn"
                onClick={toggleFacilitatorMode}
                disabled={modeLoading}
                title={language === "vi" ? `${t("hdr.switchTo", "Switch to")} ${facilitatorMode === "full" ? t("hdr.lite", "Lite") : t("hdr.full", "Full")}` : `Switch to ${facilitatorMode === "full" ? "Lite" : "Full"} Mode`}
                className="flex items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold transition-all"
                style={{
                  background: facilitatorMode === "lite"
                    ? "rgba(251,191,36,0.15)"
                    : "rgba(148,163,184,0.08)",
                  border: facilitatorMode === "lite"
                    ? "1px solid rgba(251,191,36,0.4)"
                    : "1px solid rgba(148,163,184,0.18)",
                  color: facilitatorMode === "lite" ? "#fde68a" : "#94a3b8",
                  opacity: modeLoading ? 0.6 : 1,
                  cursor: modeLoading ? "not-allowed" : "pointer",
                }}
              >
                {/* Toggle track */}
                <span
                  style={{
                    display: "inline-flex",
                    width: "28px",
                    height: "16px",
                    borderRadius: "999px",
                    background: facilitatorMode === "lite" ? "rgba(251,191,36,0.5)" : "rgba(100,116,139,0.35)",
                    alignItems: "center",
                    padding: "2px",
                    transition: "background 0.25s",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: "12px",
                      height: "12px",
                      borderRadius: "50%",
                      background: facilitatorMode === "lite" ? "#fbbf24" : "#64748b",
                      transform: facilitatorMode === "lite" ? "translateX(12px)" : "translateX(0px)",
                      transition: "transform 0.25s, background 0.25s",
                      flexShrink: 0,
                    }}
                  />
                </span>
                {facilitatorMode === "lite" ? t("hdr.lite", "Lite") : t("hdr.full", "Full")}
              </button>

              {/* Simulator toggle button */}
              <button
                id="sim-toggle-btn"
                onClick={() => setShowSimulator((v) => !v)}
                title={showSimulator ? t("hdr.simClose", "Close simulator") : t("hdr.simOpen", "Open User 2 Simulator")}
                className="flex items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold transition-all"
                style={{
                  background: showSimulator
                    ? "rgba(99,102,241,0.18)"
                    : "rgba(148,163,184,0.08)",
                  border: showSimulator
                    ? "1px solid rgba(99,102,241,0.4)"
                    : "1px solid rgba(148,163,184,0.18)",
                  color: showSimulator ? "#a5b4fc" : "#94a3b8",
                }}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                </svg>
                {showSimulator ? t("hdr.simHide", "Hide Simulator") : t("hdr.simAdd", "Add Simulator")}
              </button>

              {/* Leave */}
              <button
                onClick={handleLeave}
                className="rounded-full px-5 py-2.5 text-sm font-semibold text-red-300 transition-all hover:bg-red-500/20"
                style={{
                  background: "rgba(239,68,68,0.1)",
                  border: "1px solid rgba(239,68,68,0.25)",
                }}
              >
                {t("hdr.leave", "Leave Meeting")}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowJoinModal(true)}
              className="rounded-full px-5 py-2.5 text-sm font-semibold text-white transition-all"
              style={{
                background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
              }}
            >
              {t("hdr.join", "Join Meeting")}
            </button>
          )}
        </header>

        {/* Meeting grid */}
        <section className="grid flex-1 gap-4 grid-cols-2 grid-rows-2 md:grid-cols-3 md:grid-rows-1 min-h-0">
          {/* Left user */}
          <div className="h-full order-1">
            {participantSlots[0] ? (
              <ParticipantCell
                participant={participantSlots[0]}
                isMe={participantSlots[0].sessionId === sessionId}
                micActive={micActive}
                onToggleMic={toggleMic}
                webcamActive={
                  participantSlots[0].sessionId === sessionId
                    ? webcamActive
                    : !!remoteStreams[participantSlots[0].sessionId] // true if remote has video
                }
                webcamStream={
                  participantSlots[0].sessionId === sessionId
                    ? webcamStream
                    : (remoteStreams[participantSlots[0].sessionId] ?? null) // remote stream
                }
                onToggleWebcam={toggleWebcam}
              />
            ) : (
              <EmptyCell />
            )}
          </div>

          {/* Facilitator */}
          <div
            className="relative h-full overflow-hidden rounded-3xl shadow-2xl shadow-black/30 col-span-2 order-3 md:col-span-1 md:order-2"
            style={{
              border: "1px solid rgba(148,163,184,0.2)",
              background: "rgba(15,23,42,0.6)",
              backdropFilter: "blur(16px)",
            }}
          >
            {/* AI Facilitator label + action badge — inline pill row */}
            <div
              className="absolute left-4 top-4 z-10 flex items-center gap-2"
            >
              <div
                className="rounded-full px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-200 shadow-lg"
                style={{
                  background: "rgba(15,23,42,0.9)",
                  border: "1px solid rgba(148,163,184,0.15)",
                }}
              >
                {t("fac.title", "AI Facilitator")}
              </div>
              <ActionBadge action={lastFacilitatorAction} />
            </div>

            <div
              className="pointer-events-none absolute inset-0 rounded-3xl"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 0%, rgba(99,102,241,0.12) 0%, transparent 70%)",
              }}
            />

            <div className="h-full">
              {facilitatorMode === "lite" ? (
                <LiteAvatarView roomState={roomState} />
              ) : (
                <Canvas
                  shadows
                  camera={{ position: [0, 0, 1], fov: 30 }}
                  style={{ width: "100%", height: "100%" }}
                >
                  <Experience />
                </Canvas>
              )}
            </div>

            {/* Facilitator status log box */}
            <FacilitatorStatusBox
              logs={facilitatorLogs}
              voiceSessionActive={voiceSessionActive}
            />

          </div>

          {/* Right user */}
          <div className="h-full order-2 md:order-3">
            {participantSlots[1] ? (
              <ParticipantCell
                participant={participantSlots[1]}
                isMe={participantSlots[1].sessionId === sessionId}
                micActive={micActive}
                onToggleMic={toggleMic}
                webcamActive={
                  participantSlots[1].sessionId === sessionId
                    ? webcamActive
                    : !!remoteStreams[participantSlots[1].sessionId] // ✅ check remote
                }
                webcamStream={
                  participantSlots[1].sessionId === sessionId
                    ? webcamStream
                    : (remoteStreams[participantSlots[1].sessionId] ?? null) // ✅ pass remote stream
                }
                onToggleWebcam={toggleWebcam}
              />
            ) : (
              <EmptyCell />
            )}
          </div>
        </section>
      </main>
      </div>
    </>
  );
}

export default App;
