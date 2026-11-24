"""Local HTTP routes for the dashboard and the browser's WebRTC handshake."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from appointments import Appointments
from voice import run_call

load_dotenv(Path(__file__).with_name(".env"))
appointments = Appointments()
connections = SmallWebRTCRequestHandler()


@asynccontextmanager
async def lifespan(_app):
    try:
        yield
    finally:
        await connections.close()


app = FastAPI(title="Cedar Clinic demo", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


@app.get("/api/schedule")
async def schedule():
    return appointments.snapshot()


@app.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background: BackgroundTasks):
    missing = [name for name in ("ELEVENLABS_API_KEY", "GOOGLE_API_KEY") if not os.getenv(name)]
    if missing:
        raise HTTPException(503, detail=f"Configure {', '.join(missing)} in the server .env to start a call.")

    async def connected(connection):
        background.add_task(run_call, connection, appointments)

    return await connections.handle_web_request(request=request, webrtc_connection_callback=connected)


@app.patch("/api/offer")
async def candidate(request: SmallWebRTCPatchRequest):
    await connections.handle_patch_request(request)
    return {"ok": True}


frontend = Path(__file__).parent / "web" / "dist"
if (frontend / "index.html").is_file():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="dashboard")
