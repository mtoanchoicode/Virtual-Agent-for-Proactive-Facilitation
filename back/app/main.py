import os
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api import http_routes, websocket
from app.core.config import BASE_DIR

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="IAcine Avatar 3D API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Temporary for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(os.path.join(BASE_DIR, "audios"), exist_ok=True)

# Include routers
app.include_router(http_routes.router)
app.include_router(websocket.router)

# ---------------------------------------------------------------------------
# Serve Frontend
# ---------------------------------------------------------------------------
dist_path = os.path.join(BASE_DIR, "../front/dist")

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
        "app.main:app",
        host="0.0.0.0",
        port=3000,
        ssl_keyfile=os.path.join(BASE_DIR, "../front/certs/192.168.1.20+3-key.pem"),
        ssl_certfile=os.path.join(BASE_DIR, "../front/certs/192.168.1.20+3.pem"),
    )
