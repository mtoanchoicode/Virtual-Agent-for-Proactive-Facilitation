import uuid
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.room_manager import room, Participant

router = APIRouter()

@router.websocket("/ws/mic_test")
async def mic_test_ws(websocket: WebSocket):
    await websocket.accept()
    from app.services.audio_service import is_speech_present
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes"):
                speaking = is_speech_present(msg["bytes"])
                await websocket.send_json({"is_speech_present": speaking})
    except WebSocketDisconnect:
        pass

@router.websocket("/ws/voice")
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
                        **room.session_timer(),
                    })

                    await room.broadcast(
                        {
                            "type": "participant_joined",
                            "participant": participant.to_dict(),
                            "participants": room.participant_list(),
                        },
                        exclude=session_id,
                    )
                    await room.send_board_to(session_id)
                    print(f"[room] {name} joined (session={session_id})")

                elif msg_type in ("board_drag_start", "board_drag_end", "board_move", "board_agree"):
                    await room.board_action(session_id, payload)

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

                    if len(room.participant_list()) == 0:
                        from app.services.llm_service import shared_conv
                        shared_conv.clear()
                        room.board.reset()
                    else:
                        await room.broadcast_board()

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
            if len(room.participant_list()) == 0:
                from app.services.llm_service import shared_conv
                shared_conv.clear()
                room.board.reset()
            else:
                await room.broadcast_board()
            print(f"[room] {participant.name} disconnected")
