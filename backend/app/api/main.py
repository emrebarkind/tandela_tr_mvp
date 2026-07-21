"""Klinia TR FastAPI app."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat_router, auth_router, health_router, patients_router, router as sessions_router
from app.api.transcription_ws import ws_router

app = FastAPI(title="Klinia TR API", version="0.1.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
