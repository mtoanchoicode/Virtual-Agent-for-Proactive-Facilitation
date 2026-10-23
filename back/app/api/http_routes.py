import json
import asyncio
from fastapi import APIRouter, Request

from app.models.schemas import ChatRequest
from app.core.room_manager import room
from app.services import lang
from app.services.llm_service import process_message
from app.utils.helpers import audio_file_to_base64
from app.core.config import OPENAI_API_KEY, client

router = APIRouter()

@router.get("/api")
async def root():
    return "Welcome to IAcine Avatar 3D API 🤖"

@router.get("/room/participants")
async def get_participants():
    return {
        "participants": room.participant_list(),
        "voiceSessionActive": room.voice_session_active,
    }

@router.get("/room/mode")
async def get_mode():
    return {"mode": room.mode}

@router.post("/room/mode")
async def set_mode(request: Request):
    body = await request.json()
    new_mode = body.get("mode", "full")
    if new_mode not in ("full", "lite"):
        return {"error": "Invalid mode. Must be 'full' or 'lite'."}
    room.mode = new_mode
    await room.broadcast({"type": "mode_changed", "mode": new_mode})
    await room.broadcast_log(f"[room] Mode switched to: {new_mode.upper()}", "warning")
    return {"mode": room.mode}

@router.get("/room/time-limit")
async def get_time_limit():
    return room.session_timer()

@router.post("/room/time-limit")
async def set_time_limit(request: Request):
    body = await request.json()
    try:
        minutes = int(body.get("minutes"))
    except (TypeError, ValueError):
        return {"error": "minutes must be an integer between 1 and 20."}
    if not 1 <= minutes <= 20:
        return {"error": "minutes must be an integer between 1 and 20."}
    await room.set_time_limit(minutes)
    return room.session_timer()

@router.get("/room/language")
async def get_language():
    return {"language": lang.get()}

@router.post("/room/language")
async def set_language(request: Request):
    body = await request.json()
    new_lang = body.get("language", "en")
    if not lang.set_lang(new_lang):
        return {"error": "Invalid language. Must be 'en' or 'vi'."}
    await room.broadcast({"type": "language_changed", "language": new_lang})
    await room.broadcast_log(f"[room] Language switched to: {new_lang.upper()}", "warning")
    return {"language": lang.get()}

@router.post("/chat")
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
