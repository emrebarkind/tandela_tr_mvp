"""Tandela TR FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat_router, auth_router, health_router, patients_router, router as sessions_router
from app.api.transcription_ws import ws_router

app = FastAPI(title="Tandela TR API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(ws_router)
