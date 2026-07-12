// App.jsx
import { useState, useCallback, useRef, useEffect } from "react";
import { Loader } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Leva } from "leva";
import { Experience } from "./components/Experience";
import { UI } from "./components/UI";
import { useChat } from "./hooks/useChat";
import { ImageSegmenter, FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

// ── Join Modal ──────────────────────────────────────────────────────────────
function JoinModal({ onJoin }) {
  const [name, setName] = useState("");

  const handleSubmit = () => {
    if (name.trim()) onJoin(name.trim());
  };

  return (
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
          Join Meeting
        </h2>
        <p className="mb-6 text-sm text-slate-400">
          Enter your display name to enter the room.
        </p>

        <input
          autoFocus
          type="text"
          placeholder="Your name…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          className="w-full rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 outline-none focus:ring-2 focus:ring-sky-500/50 transition"
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(148,163,184,0.15)",
          }}
        />

        <button
          onClick={handleSubmit}
          disabled={!name.trim()}
          className="mt-4 w-full rounded-lg py-3 text-sm font-semibold text-white transition-all"
          style={{
            background: name.trim()
              ? "linear-gradient(135deg, #0ea5e9, #6366f1)"
              : "rgba(148,163,184,0.15)",
            cursor: name.trim() ? "pointer" : "not-allowed",
          }}
        >
          Join →
        </button>
      </div>
    </div>
  );
}

// ── Entropy Chart ───────────────────────────────────────────────────────────
function EntropyChart({ data }) {
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
        Entropy: {Math.round(latestValue)}%
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
              You
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
          Participant
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
                title={micActive ? "Mute your mic" : "Unmute your mic"}
              >
                {micActive ? (
                  <>
                    <MicOnIcon /> Mute
                  </>
                ) : (
                  <>
                    <MicOffIcon /> Unmute
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
                title={webcamActive ? "Turn off camera" : "Turn on camera"}
              >
                {webcamActive ? (
                  <>
                    <CamOnIcon /> Cam off
                  </>
                ) : (
                  <>
                    <CamOffIcon /> Cam on
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
              <span>{participant.micActive ? "Live" : "Muted"}</span>
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
              title={blurActive ? "Turn off background blur" : "Turn on background blur"}
            >
              {blurActive ? (
                <>
                  <BlurOnIcon /> Blur on
                </>
              ) : (
                <>
                  <BlurOffIcon /> Blur off
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Empty Cell ──────────────────────────────────────────────────────────────
function EmptyCell() {
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
        Empty
      </span>
    </div>
  );
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
  } = useChat();

  const [showJoinModal, setShowJoinModal] = useState(false);
  const isJoined = !!sessionId;

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
      <UI />

      {showJoinModal && <JoinModal onJoin={handleJoin} />}

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
                ? `${participants.length} participant${participants.length !== 1 ? "s" : ""} in room`
                : "Not in room"}
            </div>

            {isJoined && myName && (
              <div
                className="rounded-full px-3 py-1.5 text-xs font-semibold text-sky-300"
                style={{
                  background: "rgba(14,165,233,0.1)",
                  border: "1px solid rgba(14,165,233,0.25)",
                }}
              >
                Joined as {myName}
              </div>
            )}
          </div>

          {isJoined ? (
            <button
              onClick={handleLeave}
              className="rounded-full px-5 py-2.5 text-sm font-semibold text-red-300 transition-all hover:bg-red-500/20"
              style={{
                background: "rgba(239,68,68,0.1)",
                border: "1px solid rgba(239,68,68,0.25)",
              }}
            >
              Leave Meeting
            </button>
          ) : (
            <button
              onClick={() => setShowJoinModal(true)}
              className="rounded-full px-5 py-2.5 text-sm font-semibold text-white transition-all"
              style={{
                background: "linear-gradient(135deg, #0ea5e9, #6366f1)",
              }}
            >
              Join Meeting
            </button>
          )}
        </header>

        {/* Meeting grid */}
        <section className="grid flex-1 gap-4 sm:grid-cols-3 min-h-0">
          {/* Left user */}
          <div className="h-full">
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
            className="relative h-full overflow-hidden rounded-3xl shadow-2xl shadow-black/30"
            style={{
              border: "1px solid rgba(148,163,184,0.2)",
              background: "rgba(15,23,42,0.6)",
              backdropFilter: "blur(16px)",
            }}
          >
            <div
              className="absolute left-4 top-4 z-10 rounded-full px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-200 shadow-lg"
              style={{
                background: "rgba(15,23,42,0.9)",
                border: "1px solid rgba(148,163,184,0.15)",
              }}
            >
              AI Facilitator
            </div>

            <div
              className="pointer-events-none absolute inset-0 rounded-3xl"
              style={{
                background:
                  "radial-gradient(ellipse at 50% 0%, rgba(99,102,241,0.12) 0%, transparent 70%)",
              }}
            />

            <div className="h-full">
              <Canvas
                shadows
                camera={{ position: [0, 0, 1], fov: 30 }}
                style={{ width: "100%", height: "100%" }}
              >
                <Experience />
              </Canvas>
            </div>
          </div>

          {/* Right user */}
          <div className="h-full">
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
    </>
  );
}

export default App;
