"""Deepgram streaming WebSocket proxy for live transcript display."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.providers.audio_processing import _load_env_file

ws_router = APIRouter(tags=["transcription"])
_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
_DEEPGRAM_EU_BASE = "wss://api.eu.deepgram.com"


@ws_router.websocket("/ws/transcribe")
async def transcribe_websocket(websocket: WebSocket, session_id: str = "live") -> None:
    """Proxy browser MediaRecorder chunks to Deepgram without exposing the API key."""
    await websocket.accept()
    config = _deepgram_streaming_config()
    if config is None:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Deepgram streaming yapılandırması eksik. DEEPGRAM_API_KEY ve AB endpoint gerekir.",
            }
        )
        await websocket.close(code=1011)
        return

    try:
        import websockets
    except ImportError:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Backend streaming bağımlılığı eksik. requirements.txt içindeki websockets paketini kurun.",
            }
        )
        await websocket.close(code=1011)
        return

    uri = _deepgram_streaming_uri(config)
    headers = {"Authorization": f"Token {config['api_key']}"}

    try:
        deepgram_connector = _connect_deepgram(websockets, uri, headers)
        async with deepgram_connector as deepgram:
            await websocket.send_json({"type": "ready", "session_id": session_id})
            await _bridge_streams(websocket, deepgram)
    except Exception:
        await _safe_send_json(websocket, {"type": "error", "message": "Deepgram streaming bağlantısı kurulamadı."})
        await websocket.close(code=1011)


async def _bridge_streams(websocket: WebSocket, deepgram: Any) -> None:
    client_task = asyncio.create_task(_forward_browser_audio(websocket, deepgram))
    deepgram_task = asyncio.create_task(_forward_deepgram_transcript(websocket, deepgram))
    done, pending = await asyncio.wait(
        {client_task, deepgram_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    for task in done:
        try:
            task.result()
        except WebSocketDisconnect:
            pass
        except Exception:
            await _safe_send_json(websocket, {"type": "error", "message": "Canlı transkript akışı durdu."})


def _connect_deepgram(websockets: Any, uri: str, headers: dict[str, str]) -> Any:
    parameters = inspect.signature(websockets.connect).parameters
    header_arg = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    return websockets.connect(uri, **{header_arg: headers})


async def _forward_browser_audio(websocket: WebSocket, deepgram: Any) -> None:
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            await deepgram.send(json.dumps({"type": "CloseStream"}))
            return
        if message.get("bytes"):
            await deepgram.send(message["bytes"])
            continue
        text = message.get("text")
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = {}
        if parsed.get("type") == "stop":
            await deepgram.send(json.dumps({"type": "CloseStream"}))
            return


async def _forward_deepgram_transcript(websocket: WebSocket, deepgram: Any) -> None:
    async for raw_message in deepgram:
        try:
            payload = json.loads(raw_message)
        except ValueError:
            continue
        event = _transcript_event_from_deepgram(payload)
        if event is not None:
            await _safe_send_json(websocket, event)


async def _safe_send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await websocket.send_json(payload)
    except RuntimeError:
        pass


def _deepgram_streaming_config() -> Optional[dict[str, str]]:
    _load_env_file(_ENV_FILE)
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    base_url = os.environ.get("DEEPGRAM_BASE_URL", "https://api.eu.deepgram.com").strip().rstrip("/")
    if not api_key or base_url != "https://api.eu.deepgram.com":
        return None
    return {
        "api_key": api_key,
        "model": os.environ.get("DEEPGRAM_MODEL", "nova-3").strip() or "nova-3",
        "language": os.environ.get("DEEPGRAM_LANGUAGE", "tr").strip() or "tr",
    }


def _deepgram_streaming_uri(config: dict[str, str]) -> str:
    params = urlencode(
        {
            "model": config["model"],
            "language": config["language"],
            "diarize": "true",
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            "utterances": "true",
        }
    )
    return f"{_DEEPGRAM_EU_BASE}/v1/listen?{params}"


def _transcript_event_from_deepgram(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    channel = payload.get("channel") or {}
    alternatives = channel.get("alternatives") or []
    if not alternatives:
        return None
    alternative = alternatives[0]
    transcript = str(alternative.get("transcript") or "").strip()
    if not transcript:
        return None
    words = alternative.get("words") or []
    speaker = _speaker_from_words(words)
    return {
        "type": "transcript",
        "speaker_id": speaker,
        "text": transcript,
        "is_final": bool(payload.get("is_final") or payload.get("speech_final")),
    }


def _speaker_from_words(words: list[dict[str, Any]]) -> str:
    speaker = None
    for word in words:
        if word.get("speaker") is not None:
            speaker = word.get("speaker")
            break
    try:
        index = int(speaker)
    except (TypeError, ValueError):
        return "A"
    return chr(ord("A") + max(0, min(index, 25)))
