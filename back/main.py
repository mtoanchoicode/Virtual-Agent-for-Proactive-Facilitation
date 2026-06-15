import os
import asyncio
import sys
import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from room_manager import room, Participant
from services import (
    process_message,
    audio_file_to_base64,
    client,
    OPENAI_API_KEY
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="IAcine Avatar 3D API")

local_origins = ["http://localhost:5173", "https://localhost:5173"]
local_origin_regex = (
    r"^https?://(?:localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(?::\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Temporary for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("audios", exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------

@app.get("/api")
async def root():
    return "Welcome to IAcine Avatar 3D API 🤖"


@app.get("/room/participants")
async def get_participants():
    return {
        "participants": room.participant_list(),
        "voiceSessionActive": room.voice_session_active,
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.message:
        return {
            "messages": [
                {
                    "text": "Hey dear... How was your day?",
                    "audio": await audio_file_to_base64("audios/intro_0.wav"),
                    "facialExpression": "smile",
                    "animation": "Talking_1",
                },
            ]
        }

    if OPENAI_API_KEY == "-":
        return {
            "messages": [
                {
                    "text": "Please my dear, don't forget to add your API keys!",
                    "audio": await audio_file_to_base64("audios/api_0.wav"),
                    "facialExpression": "angry",
                    "animation": "Angry",
                }
            ]
        }

    completion = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
                    Your name is Yacine, you're an expert in Artificial Intelligence and Data.
                    You will always reply with a JSON array of messages. Max 2 messages.
                    Each message has a text, facialExpression, and animation property.
                    Facial expressions: smile, sad, angry, surprised, funnyFace, default.
                    Animations: Talking_0, Talking_1, Talking_2, Crying, Laughing, Rumba, Idle, Terrified, Angry.
                """,
            },
            {"role": "user", "content": request.message},
        ],
    )
    raw = completion.choices[0].message.content
    clean = raw.replace("```json", "").replace("```", "").strip()
    messages = json.loads(clean)
    if isinstance(messages, dict):
        messages = [messages]

    tasks = [process_message(i, msg) for i, msg in enumerate(messages)]
    processed = await asyncio.gather(*tasks)
    return {"messages": processed}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    session_id = str(uuid.uuid4())
    participant: Optional[Participant] = None
    client_voice_active: bool = False

    try:
        while True:
            msg = await websocket.receive()

            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("bytes"):
                if participant is None or not room.voice_session_active:
                    continue
                if not participant.mic_active:
                    continue
                
                await room.ingest_audio(session_id, msg["bytes"])

            elif "text" in msg:
                payload = json.loads(msg["text"])
                msg_type = payload.get("type")

                if msg_type == "join":
                    if participant is not None:
                        await websocket.send_json({
                            "type": "error",
                            "detail": "Already joined. Send 'leave' first.",
                        })
                        continue

                    if len(room.participant_list()) >= 2:
                        await websocket.send_json({
                            "type": "error",
                            "detail": "Room is full. Maximum 2 users allowed.",
                        })
                        continue

                    name = (payload.get("name") or "").strip() or f"Guest-{session_id[:6]}"
                    participant = Participant(session_id, name, websocket)
                    await room.add(participant)

                    await websocket.send_json({
                        "type": "joined",
                        "sessionId": session_id,
                        "participant": participant.to_dict(),
                        "participants": room.participant_list(),
                        "voiceSessionActive": room.voice_session_active,
                    })

                    await room.broadcast(
                        {
                            "type": "participant_joined",
                            "participant": participant.to_dict(),
                            "participants": room.participant_list(),
                        },
                        exclude=session_id,
                    )
                    print(f"[room] {name} joined (session={session_id})")

                elif msg_type == "leave":
                    if participant is None:
                        continue
                    await room.remove(session_id)
                    await websocket.send_json({"type": "left", "sessionId": session_id})
                    await room.broadcast({
                        "type": "participant_left",
                        "sessionId": session_id,
                        "name": participant.name,
                        "participants": room.participant_list(),
                    })
                    print(f"[room] {participant.name} left")

                    if client_voice_active and len(room.active_participants) == 0:
                        await room.deactivate_voice_session()

                    participant = None
                    client_voice_active = False

                elif msg_type == "start_voice":
                    if participant is None:
                        await websocket.send_json({
                            "type": "error",
                            "detail": "Join the room first.",
                        })
                        continue
                    client_voice_active = True
                    await room.activate_voice_session()
                    await websocket.send_json({
                        "type": "voice_started",
                        "sessionId": session_id,
                    })

                elif msg_type == "stop_voice":
                    client_voice_active = False
                    await room.deactivate_voice_session()
                    await websocket.send_json({
                        "type": "voice_stopped",
                        "sessionId": session_id,
                    })

                elif msg_type == "update_mic":
                    if participant is None:
                        continue
                    mic_active = bool(payload.get("micActive", True))
                    participant.mic_active = mic_active
                    if not mic_active:
                        participant.audio_chunks.clear()
                        participant.is_speaking = False

                    await websocket.send_json({
                        "type": "mic_updated",
                        "sessionId": session_id,
                        "micActive": mic_active,
                    })
                    await room.broadcast(
                        {
                            "type": "participant_mic_updated",
                            "sessionId": session_id,
                            "name": participant.name,
                            "micActive": mic_active,
                            "participants": room.participant_list(),
                        },
                        exclude=session_id,
                    )

                elif msg_type == "update_entropy":
                    if participant is None:
                        continue
                    entropy = int(payload.get("entropy", 0))
                    participant.entropy = entropy
                    await room.broadcast(
                        {
                            "type": "participant_entropy",
                            "sessionId": session_id,
                            "entropy": entropy,
                        },
                        exclude=session_id,
                    )

                elif msg_type == "webrtc_offer":
                    target_sid = payload.get("targetSessionId")
                    if target_sid:
                        await room.send_to(target_sid, {
                            "type": "webrtc_offer",
                            "offer": payload.get("offer"),
                            "fromSessionId": session_id,
                            "fromName": participant.name if participant else "Unknown",
                        })

                elif msg_type == "webrtc_answer":
                    target_sid = payload.get("targetSessionId")
                    if target_sid:
                        await room.send_to(target_sid, {
                            "type": "webrtc_answer",
                            "answer": payload.get("answer"),
                            "fromSessionId": session_id,
                        })

                elif msg_type == "webrtc_ice_candidate":
                    target_sid = payload.get("targetSessionId")
                    if target_sid:
                        await room.send_to(target_sid, {
                            "type": "webrtc_ice_candidate",
                            "candidate": payload.get("candidate"),
                            "fromSessionId": session_id,
                        })

    except WebSocketDisconnect:
        pass
    finally:
        if participant is not None:
            await room.remove(session_id)
            await room.broadcast({
                "type": "participant_left",
                "sessionId": session_id,
                "name": participant.name,
                "participants": room.participant_list(),
            })
            if client_voice_active and len(room.active_participants) == 0:
                await room.deactivate_voice_session()
            print(f"[room] {participant.name} disconnected")


# ---------------------------------------------------------------------------
# Serve Frontend
# ---------------------------------------------------------------------------
dist_path = os.path.join(os.path.dirname(__file__), "../front/dist")

if os.path.exists(dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        path = os.path.join(dist_path, full_path)
        if os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(os.path.join(dist_path, "index.html"))
else:
    print(f"Warning: Frontend build directory not found at {dist_path}. Please build the frontend.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        # reload=True,
        ssl_keyfile="../front/certs/192.168.1.20+3-key.pem",
        ssl_certfile="../front/certs/192.168.1.20+3.pem",
    )