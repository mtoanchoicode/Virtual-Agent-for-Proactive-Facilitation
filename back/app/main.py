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

cors_origins_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = [origin.strip() for origin in cors_origins_env.split(",")] if cors_origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: COOP/COEP headers are intentionally NOT added here.
# They are set by the frontend (Vite/Vercel) only. Adding them to backend
# API responses blocks cross-origin resource loading when frontend (Vercel)
# and backend (Render) are on different domains.

os.makedirs(os.path.join(BASE_DIR, "audios"), exist_ok=True)

# Include routers
app.include_router(http_routes.router)
app.include_router(websocket.router)

# ---------------------------------------------------------------------------
# Serve Frontend
# ---------------------------------------------------------------------------
# BASE_DIR is back/app, so we need to go up two levels to reach the root project folder
dist_path = os.path.abspath(os.path.join(BASE_DIR, "../../front/dist"))

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
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    ssl_keyfile = os.getenv("SSL_KEYFILE")
    ssl_certfile = os.getenv("SSL_CERTFILE")

    run_kwargs = {
        "host": host,
        "port": port,
    }

    if ssl_keyfile and ssl_certfile:
        run_kwargs["ssl_keyfile"] = ssl_keyfile
        run_kwargs["ssl_certfile"] = ssl_certfile
    else:
        # Fallback to local certs for development if they exist
        local_key = os.path.abspath(os.path.join(BASE_DIR, "../../front/certs/192.168.1.20+3-key.pem"))
        local_cert = os.path.abspath(os.path.join(BASE_DIR, "../../front/certs/192.168.1.20+3.pem"))
        if os.path.exists(local_key) and os.path.exists(local_cert):
            run_kwargs["ssl_keyfile"] = local_key
            run_kwargs["ssl_certfile"] = local_cert

    uvicorn.run("app.main:app", **run_kwargs)
