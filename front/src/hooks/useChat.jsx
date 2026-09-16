// front/src/hooks/useChat.jsx
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";

const isSecure = window.location.protocol === "https:";
const wsProtocol = isSecure ? "wss" : "ws";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";
const API_URL = BACKEND_URL;
const wsHost = BACKEND_URL ? BACKEND_URL.replace(/^http/, "ws") : `${wsProtocol}://${window.location.host}`;
const WS_URL = `${wsHost}/ws/voice`;

const ChatContext = createContext();

const SAMPLE_RATE = 16000;
const CHUNK_SIZE = 4096;
const WARMUP_MS = 1500;

const ICE_SERVERS = {
  iceServers: [
    {
      urls: "stun:stun.relay.metered.ca:80",
    },
    {
      urls: "turn:global.relay.metered.ca:80",
      username: "4a675b16a4b55511680ac09e",
      credential: "wcY9X5cDbKj8d4g2",
    },
    {
      urls: "turn:global.relay.metered.ca:80?transport=tcp",
      username: "4a675b16a4b55511680ac09e",
      credential: "wcY9X5cDbKj8d4g2",
    },
    {
      urls: "turn:global.relay.metered.ca:443",
      username: "4a675b16a4b55511680ac09e",
      credential: "wcY9X5cDbKj8d4g2",
    },
    {
      urls: "turns:global.relay.metered.ca:443?transport=tcp",
      username: "4a675b16a4b55511680ac09e",
      credential: "wcY9X5cDbKj8d4g2",
    },
  ],
};

export const ChatProvider = ({ children }) => {
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cameraZoomed, setCameraZoomed] = useState(true);
  const [roomState, setRoomState] = useState("idle");
  const [turnTranscripts, setTurnTranscripts] = useState([]);
  const [modelTranscripts, setModelTranscripts] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [myName, setMyName] = useState(null);
  const [participants, setParticipants] = useState([]);
  const [micActive, setMicActive] = useState(true);
  const [voiceSessionActive, setVoiceSessionActive] = useState(false);
  const [localVoiceStreaming, setLocalVoiceStreaming] = useState(false);
  const [participantEntropies, setParticipantEntropies] = useState({});
  const [facilitatorLogs, setFacilitatorLogs] = useState([]);
  const [lastFacilitatorAction, setLastFacilitatorAction] = useState(null);
  
  // ── Facilitator Mode ─────────────────────────────────────────────────────
  const [facilitatorMode, setFacilitatorMode] = useState("full");
  const [modeLoading, setModeLoading] = useState(false);

  useEffect(() => {
    fetch(`${BACKEND_URL}/room/mode`)
      .then((r) => r.json())
      .then((data) => setFacilitatorMode(data.mode))
      .catch(() => {});
  }, []);

  const toggleFacilitatorMode = useCallback(async () => {
    const next = facilitatorMode === "full" ? "lite" : "full";
    setModeLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/room/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: next }),
      });
      const data = await res.json();
      setFacilitatorMode(data.mode ?? next);
    } catch (e) {
      console.error("Failed to switch mode", e);
    } finally {
      setModeLoading(false);
    }
  }, [facilitatorMode]);

  // ── WebRTC state ────────────────────────────────────────────────────────
  // Map of sessionId → MediaStream (remote video streams)
  const [remoteStreams, setRemoteStreams] = useState({});
  // Our local webcam stream (shared with WebRTC peers)
  const [webcamActive, setWebcamActive] = useState(false);
  const [webcamStream, setWebcamStream] = useState(null);

  const wsRef = useRef(null);
  const audioCtxRef = useRef(null);
  const processorRef = useRef(null);
  const streamRef = useRef(null);
  const warmupTimerRef = useRef(null);
  const isWarmingUp = useRef(true);
  const blockedRef = useRef(false);
  // Map of msgId → { mediaSource, sourceBuffer, audioEl, objectUrl, appendQueue, isAppending, streamEnded }
  const activeStreamsRef = useRef({});

  // peerConnections: Map<sessionId, RTCPeerConnection>
  const peerConnectionsRef = useRef({});
  const peerAudioStreamRef = useRef(null);
  // Keep a ref to webcamStream so callbacks always see the latest value
  const webcamStreamRef = useRef(null);
  const sessionIdRef = useRef(null);

  useEffect(() => {
    webcamStreamRef.current = webcamStream;
  }, [webcamStream]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // ── Message queue ─────────────────────────────────────────────────────
  const addMessages = useCallback((msgs) => {
    setMessages((prev) => [...prev, ...msgs]);
  }, []);

  // Decode a base64 string to an ArrayBuffer (used for MediaSource chunk appending)
  const base64ToArrayBuffer = useCallback((b64) => {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes.buffer;
  }, []);

  // Process the pending chunk queue for a given streaming message.
  // Must be called whenever: (a) a new chunk is queued, (b) the SourceBuffer
  // finishes an append (updateend), or (c) the stream is marked as ended.
  const processStreamQueue = useCallback((msgId) => {
    const stream = activeStreamsRef.current[msgId];
    if (!stream || !stream.sourceBuffer || stream.isAppending) return;
    if (stream.appendQueue.length > 0) {
      stream.isAppending = true;
      const chunk = stream.appendQueue.shift();
      try {
        stream.sourceBuffer.appendBuffer(chunk);
      } catch (e) {
        stream.isAppending = false;
        console.error("[stream] appendBuffer error:", e);
      }
    } else if (stream.streamEnded && stream.mediaSource.readyState === "open") {
      try {
        stream.mediaSource.endOfStream();
      } catch (e) {
        // Ignore — may already be ended
      }
    }
  }, []);  // stable: only accesses refs

  const onMessagePlayed = useCallback(() => {
    setMessages((prev) => {
      const played = prev[0];
      // Revoke object URL for streaming messages to free memory
      if (played?.msgId) {
        const s = activeStreamsRef.current[played.msgId];
        if (s?.objectUrl) {
          URL.revokeObjectURL(s.objectUrl);
          delete activeStreamsRef.current[played.msgId];
        }
      }
      const next = prev.slice(1);
      if (next.length === 0) {
        blockedRef.current = false;
        setRoomState("idle");
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      setMessage(messages[0]);
      blockedRef.current = true;
      setRoomState("speaking");
    } else {
      setMessage(null);
    }
  }, [messages]);

  const chat = async (text) => {
    setLoading(true);
    const res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const { messages: msgs } = await res.json();
    addMessages(msgs);
    setLoading(false);
  };

  // ── WebRTC helpers ────────────────────────────────────────────────────

  /**
   * Create a new RTCPeerConnection for the given remote session.
   * Attaches local webcam tracks (if any) and wires up event handlers.
   */
  const createPeerConnection = useCallback((remoteSessionId) => {
    if (peerConnectionsRef.current[remoteSessionId]) {
      return peerConnectionsRef.current[remoteSessionId];
    }

    const pc = new RTCPeerConnection(ICE_SERVERS);
    peerConnectionsRef.current[remoteSessionId] = pc;

    // Add local video tracks so the remote peer can see us
    const localStream = webcamStreamRef.current;
    if (localStream) {
      localStream
        .getTracks()
        .forEach((track) => pc.addTrack(track, localStream));
    }

    // Add local audio tracks so the remote peer can hear us
    const audioStream = peerAudioStreamRef.current;
    if (audioStream) {
      console.log("[WebRTC] Adding local audio tracks to peer connection", remoteSessionId, audioStream.getAudioTracks().length);
      audioStream
        .getTracks()
        .forEach((track) => pc.addTrack(track, audioStream));
    } else {
      console.warn("[WebRTC] No local audio stream found when creating peer connection", remoteSessionId);
    }

    // When we receive a remote track, add it to the peer's unified MediaStream
    pc.ontrack = (e) => {
      console.log("[WebRTC] Received remote track:", e.track.kind, "id:", e.track.id, "from:", remoteSessionId);
      setRemoteStreams((prev) => {
        const existingStream = prev[remoteSessionId];
        const tracks = existingStream ? existingStream.getTracks() : [];
        if (!tracks.find(t => t.id === e.track.id)) {
          tracks.push(e.track);
        }
        // Create a new MediaStream to ensure React detects the object reference change
        const newStream = new MediaStream(tracks);
        return {
          ...prev,
          [remoteSessionId]: newStream,
        };
      });
    };

    // Forward ICE candidates to the remote peer via the signaling server
    pc.onicecandidate = (e) => {
      if (e.candidate && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: "webrtc_ice_candidate",
            targetSessionId: remoteSessionId,
            candidate: e.candidate,
          }),
        );
      }
    };

    pc.onconnectionstatechange = () => {
      console.log(`[WebRTC] Connection state with ${remoteSessionId}:`, pc.connectionState);
      if (
        pc.connectionState === "disconnected" ||
        pc.connectionState === "failed" ||
        pc.connectionState === "closed"
      ) {
        pc.close();
        delete peerConnectionsRef.current[remoteSessionId];
        setRemoteStreams((prev) => {
          const next = { ...prev };
          delete next[remoteSessionId];
          return next;
        });
      }
    };

    pc.oniceconnectionstatechange = () => {
      console.log(`[WebRTC] ICE connection state with ${remoteSessionId}:`, pc.iceConnectionState);
    };

    return pc;
  }, []);

  /**
   * Initiate a WebRTC offer to a remote participant.
   * Called when a new participant joins or when we turn on our webcam.
   */
  const callPeer = useCallback(
    async (remoteSessionId) => {
      const pc = createPeerConnection(remoteSessionId);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(
        JSON.stringify({
          type: "webrtc_offer",
          targetSessionId: remoteSessionId,
          offer,
        }),
      );
    },
    [createPeerConnection],
  );

  /**
   * When our webcam turns on, add the new video track to all existing peer
   * connections and renegotiate.
   */
  const addTrackToAllPeers = useCallback(async (stream) => {
    for (const [remoteSessionId, pc] of Object.entries(
      peerConnectionsRef.current,
    )) {
      stream.getTracks().forEach((track) => {
        // Avoid adding duplicates
        const alreadyAdded = pc
          .getSenders()
          .some((s) => s.track?.id === track.id);
        if (!alreadyAdded) pc.addTrack(track, stream);
      });
      // Renegotiate
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(
        JSON.stringify({
          type: "webrtc_offer",
          targetSessionId: remoteSessionId,
          offer,
        }),
      );
    }
  }, []);

  /**
   * When our webcam turns off, remove video senders and renegotiate.
   */
  const removeVideoFromAllPeers = useCallback(async () => {
    for (const [remoteSessionId, pc] of Object.entries(
      peerConnectionsRef.current,
    )) {
      const videoSenders = pc
        .getSenders()
        .filter((s) => s.track?.kind === "video");
      videoSenders.forEach((s) => pc.removeTrack(s));
      // Renegotiate
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      wsRef.current?.send(
        JSON.stringify({
          type: "webrtc_offer",
          targetSessionId: remoteSessionId,
          offer,
        }),
      );
    }
  }, []);

  // ── Webcam toggle (now also syncs with WebRTC) ─────────────────────────
  const toggleWebcam = useCallback(async () => {
    if (webcamActive) {
      webcamStreamRef.current?.getTracks().forEach((t) => t.stop());
      setWebcamStream(null);
      webcamStreamRef.current = null;
      setWebcamActive(false);
      await removeVideoFromAllPeers();
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        });
        setWebcamStream(stream);
        webcamStreamRef.current = stream;
        setWebcamActive(true);
        await addTrackToAllPeers(stream);
      } catch (err) {
        console.error("Camera access denied:", err);
      }
    }
  }, [webcamActive, addTrackToAllPeers, removeVideoFromAllPeers]);

  // ── WebSocket ─────────────────────────────────────────────────────────
  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return wsRef.current;

    const ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        handleServerMessage(data);
      } catch (err) {
        console.error("WS parse error:", err);
      }
    };

    ws.onclose = () => {
      if (voiceSessionActive || localVoiceStreaming) {
        setTimeout(connectWS, 2000);
      }
    };

    wsRef.current = ws;
    return ws;
  }, [voiceSessionActive, localVoiceStreaming]); // eslint-disable-line

  const handleServerMessage = useCallback(
    async (data) => {
      switch (data.type) {
        case "joined":
          setSessionId(data.sessionId);
          setParticipants(data.participants);
          if (data.voiceSessionActive) {
            setVoiceSessionActive(true);
            setRoomState("idle");
          }
          break;

        case "left":
          setSessionId(null);
          setMyName(null);
          setParticipants([]);
          setMicActive(true);
          setVoiceSessionActive(false);
          setLocalVoiceStreaming(false);
          setRoomState("idle");
          setTurnTranscripts([]);
          setModelTranscripts([]);
          setMessages([]);
          setFacilitatorLogs([]);
          setLastFacilitatorAction(null);
          // Close all peer connections
          Object.values(peerConnectionsRef.current).forEach((pc) => pc.close());
          peerConnectionsRef.current = {};
          setRemoteStreams({});
          break;

        case "participant_joined":
          setParticipants(data.participants);
          // As the existing participant, call the newcomer
          if (
            data.participant?.sessionId &&
            data.participant.sessionId !== sessionIdRef.current
          ) {
            await callPeer(data.participant.sessionId);
          }
          break;

        case "participant_left":
          setParticipants(data.participants);
          // Clean up that peer's connection
          if (data.sessionId) {
            peerConnectionsRef.current[data.sessionId]?.close();
            delete peerConnectionsRef.current[data.sessionId];
            setRemoteStreams((prev) => {
              const next = { ...prev };
              delete next[data.sessionId];
              return next;
            });
            setParticipantEntropies((prev) => {
              const next = { ...prev };
              delete next[data.sessionId];
              return next;
            });
          }
          break;

        case "participant_mic_updated":
        case "participant_speaking_changed":
          setParticipants(data.participants);
          break;

        case "mic_updated":
          break;

        case "participant_entropy":
          setParticipantEntropies((prev) => ({
            ...prev,
            [data.sessionId]: data.entropy,
          }));
          break;

        case "facilitator_log":
          setFacilitatorLogs((prev) => {
            const entry = {
              id: Date.now() + Math.random(),
              message: data.message,
              level: data.level ?? "info",
              timestamp: data.timestamp ?? new Date().toISOString(),
            };
            // Keep max 80 entries (ring buffer)
            const next = [...prev, entry];
            return next.length > 80 ? next.slice(next.length - 80) : next;
          });
          break;

        case "facilitator_action":
          setLastFacilitatorAction(data.action ?? null);
          break;

        case "mode_changed":
          setFacilitatorMode(data.mode);
          break;

        // ── WebRTC signaling ───────────────────────────────────────────
        case "webrtc_offer": {
          const pc = createPeerConnection(data.fromSessionId);
          await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          wsRef.current?.send(
            JSON.stringify({
              type: "webrtc_answer",
              targetSessionId: data.fromSessionId,
              answer,
            }),
          );
          break;
        }

        case "webrtc_answer": {
          const pc = peerConnectionsRef.current[data.fromSessionId];
          if (pc) {
            await pc.setRemoteDescription(
              new RTCSessionDescription(data.answer),
            );
          }
          break;
        }

        case "webrtc_ice_candidate": {
          const pc = peerConnectionsRef.current[data.fromSessionId];
          if (pc && data.candidate) {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
          }
          break;
        }

        // ── Voice session events ──────────────────────────────────────
        case "voice_session_started":
          setVoiceSessionActive(true);
          setParticipants(data.participants);
          setRoomState("idle");
          startAudioStreaming();
          break;

        case "voice_session_ended":
          setVoiceSessionActive(false);
          setLocalVoiceStreaming(false);
          setRoomState("idle");
          stopAudioStreaming();
          break;

        case "voice_started":
          setVoiceSessionActive(true);
          setLocalVoiceStreaming(true);
          startAudioStreaming();
          break;

        case "voice_stopped":
          setLocalVoiceStreaming(false);
          setRoomState("idle");
          break;

        case "turn_started":
          if (!blockedRef.current) setRoomState("listening");
          setParticipants(data.participants);
          setLastFacilitatorAction(null); // clear action badge on new turn
          break;

        case "turn_processing":
          setRoomState("processing");
          setLoading(true);
          break;

        case "turn_transcripts":
          setTurnTranscripts(data.transcripts);
          break;

        case "turn_skipped":
          setLoading(false);
          if (!blockedRef.current) setRoomState("idle");
          break;

        case "turn_interrupted":
          // Stop any active streams
          Object.values(activeStreamsRef.current).forEach(s => {
            s.audioEl?.pause();
            if (s.objectUrl) URL.revokeObjectURL(s.objectUrl);
          });
          activeStreamsRef.current = {};
          setMessages([]);
          setMessage(null);
          setLoading(false);
          blockedRef.current = false;
          setRoomState("listening");
          break;

        case "messages":
          // Legacy path (kept for backward compatibility / non-streaming fallback)
          setLoading(false);
          setModelTranscripts(data.messages.map((m) => m.text));
          addMessages(data.messages);
          break;

        // ── TTS streaming ─────────────────────────────────────────────
        case "audio_stream_start": {
          const { msgId, text, idx } = data;
          if (idx === 0) {
            setLoading(false);
            setModelTranscripts([text]);
            blockedRef.current = true;
            setRoomState("speaking");
          }
          try {
            const mediaSource = new MediaSource();
            const objectUrl = URL.createObjectURL(mediaSource);
            const audioEl = new Audio(objectUrl);
            const streamState = {
              mediaSource,
              sourceBuffer: null,
              audioEl,
              objectUrl,
              appendQueue: [],
              isAppending: false,
              streamEnded: false,
            };
            activeStreamsRef.current[msgId] = streamState;
            mediaSource.addEventListener("sourceopen", () => {
              try {
                const sb = mediaSource.addSourceBuffer("audio/mpeg");
                streamState.sourceBuffer = sb;
                sb.addEventListener("updateend", () => {
                  streamState.isAppending = false;
                  processStreamQueue(msgId);
                });
                // Drain any chunks that arrived before sourceopen fired
                processStreamQueue(msgId);
              } catch (e) {
                console.error("[stream] SourceBuffer setup error:", e);
              }
            });
            // Queue message for Avatar (audioEl replaces base64 audio)
            addMessages([{ text, msgId, audioEl }]);
          } catch (e) {
            console.error("[stream] MediaSource creation error:", e);
          }
          break;
        }

        case "audio_stream_chunk": {
          const { msgId, data: chunkB64 } = data;
          const stream = activeStreamsRef.current[msgId];
          if (!stream) break;
          const bytes = base64ToArrayBuffer(chunkB64);
          stream.appendQueue.push(bytes);
          processStreamQueue(msgId);
          break;
        }

        case "audio_stream_end": {
          const { msgId } = data;
          const stream = activeStreamsRef.current[msgId];
          if (!stream) break;
          stream.streamEnded = true;
          processStreamQueue(msgId);
          break;
        }

        case "error":
          console.error("Server error:", data.detail);
          if (data.detail && data.detail.includes("Room is full")) {
            alert(data.detail);
          }
          setLoading(false);
          blockedRef.current = false;
          setRoomState("idle");
          break;

        default:
          break;
      }
    },
    [addMessages, callPeer, createPeerConnection, processStreamQueue, base64ToArrayBuffer],
  );

  // ── Audio streaming ───────────────────────────────────────────────────
  const startAudioStreaming = useCallback(async () => {
    if (localVoiceStreaming) return;
    try {
      let stream = peerAudioStreamRef.current;
      if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        peerAudioStreamRef.current = stream;
      }
      streamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(CHUNK_SIZE, 1, 1);
      processorRef.current = proc;
      isWarmingUp.current = true;
      warmupTimerRef.current = setTimeout(() => {
        isWarmingUp.current = false;
      }, WARMUP_MS);
      proc.onaudioprocess = (e) => {
        if (isWarmingUp.current) return;
        if (blockedRef.current) return; // Don't send audio while AI is speaking
        if (wsRef.current?.readyState !== WebSocket.OPEN) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32767));
        }
        wsRef.current.send(int16.buffer);
      };
      src.connect(proc);
      proc.connect(ctx.destination);
      setLocalVoiceStreaming(true);
    } catch (err) {
      console.error("Failed to start audio streaming:", err);
    }
  }, [localVoiceStreaming]);

  const stopAudioStreaming = useCallback(() => {
    clearTimeout(warmupTimerRef.current);
    processorRef.current?.disconnect();
    audioCtxRef.current?.close();
    // Do NOT stop the tracks here, so WebRTC peer audio can continue!
    processorRef.current = null;
    audioCtxRef.current = null;
    streamRef.current = null;
    setLocalVoiceStreaming(false);
  }, []);

  // ── Room controls ─────────────────────────────────────────────────────
  const joinRoom = useCallback(
    async (name) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setMyName(trimmed);

      try {
        if (!peerAudioStreamRef.current) {
          peerAudioStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
          console.log("[WebRTC] Acquired local audio stream", peerAudioStreamRef.current.getAudioTracks().length);
        } else {
          console.log("[WebRTC] Already have local audio stream");
        }
      } catch (err) {
        console.error("[WebRTC] Mic access denied", err);
      }

      const ws = connectWS();
      const send = () =>
        ws.send(JSON.stringify({ type: "join", name: trimmed }));
      if (ws.readyState === WebSocket.OPEN) send();
      else ws.addEventListener("open", send, { once: true });
    },
    [connectWS],
  );

  const leaveRoom = useCallback(() => {
    stopAudioStreaming();
    // Stop webcam
    webcamStreamRef.current?.getTracks().forEach((t) => t.stop());
    setWebcamStream(null);
    webcamStreamRef.current = null;
    setWebcamActive(false);
    // Stop peer audio
    peerAudioStreamRef.current?.getTracks().forEach((t) => t.stop());
    peerAudioStreamRef.current = null;
    // Close peer connections
    Object.values(peerConnectionsRef.current).forEach((pc) => pc.close());
    peerConnectionsRef.current = {};
    setRemoteStreams({});
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "leave" }));
    }
    setSessionId(null);
    setMyName(null);
    setParticipants([]);
    setMicActive(true);
    setVoiceSessionActive(false);
    setLocalVoiceStreaming(false);
    setRoomState("idle");
    setTurnTranscripts([]);
    setModelTranscripts([]);
    setMessages([]);
    setFacilitatorLogs([]);
    setLastFacilitatorAction(null);
    wsRef.current?.close();
  }, [stopAudioStreaming]);

  const toggleMic = useCallback(() => {
    if (!sessionId) return;
    const next = !micActive;
    setMicActive(next);
    wsRef.current?.send(
      JSON.stringify({ type: "update_mic", micActive: next }),
    );
    if (peerAudioStreamRef.current) {
      peerAudioStreamRef.current.getAudioTracks().forEach((t) => {
        t.enabled = next;
      });
    }
  }, [sessionId, micActive]);

  const updateEntropy = useCallback((entropy) => {
    if (!sessionId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "update_entropy", entropy }));
    }
  }, [sessionId]);

  const startVoiceSession = useCallback(() => {
    if (!sessionId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "start_voice" }));
    }
  }, [sessionId]);

  const stopVoiceSession = useCallback(() => {
    if (!sessionId) return;
    stopAudioStreaming();
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "stop_voice" }));
    }
  }, [sessionId, stopAudioStreaming]);

  return (
    <ChatContext.Provider
      value={{
        chat,
        message,
        onMessagePlayed,
        loading,
        cameraZoomed,
        setCameraZoomed,
        sessionId,
        myName,
        participants,
        micActive,
        joinRoom,
        leaveRoom,
        toggleMic,
        updateEntropy,
        participantEntropies,
        voiceSessionActive,
        localVoiceStreaming,
        startVoiceSession,
        stopVoiceSession,
        roomState,
        turnTranscripts,
        modelTranscripts,
        // WebRTC / video
        webcamActive,
        webcamStream,
        toggleWebcam,
        remoteStreams, // { [sessionId]: MediaStream }
        facilitatorLogs,
        lastFacilitatorAction,
        facilitatorMode,
        toggleFacilitatorMode,
        modeLoading,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within a ChatProvider");
  return ctx;
};
