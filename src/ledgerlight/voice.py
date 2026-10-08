"""Optional CPU transcription; multipart parsing without another dependency."""

import importlib.util
import io
import threading
from email import policy
from email.parser import BytesParser

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ledgerlight import llm_client

router = APIRouter()
_model = None
_lock = threading.Lock()
_loading = False
MAX_AUDIO = 10 * 1024 * 1024


def status():
    info = llm_client.status()
    if info["provider"] == "fake":
        engine = "fake"
    elif info["provider"] == "openai":
        engine = "openai" if info["key_present"] else None
    else:
        engine = (
            "faster-whisper" if importlib.util.find_spec("faster_whisper") else None
        )
    return {"engine": engine, "available": engine is not None, "loading": _loading}


@router.get("/api/stt/status")
def stt_status():
    return status()


def transcribe(audio, engine):
    global _model, _loading
    if engine == "fake":
        return "Show spending by category"
    if engine == "openai":
        return llm_client.transcribe_openai(audio, "recording.webm")
    if engine != "faster-whisper":
        raise ValueError("No speech engine available; install the voice extra")
    try:
        with _lock:
            if _model is None:
                _loading = True
                from faster_whisper import WhisperModel

                _model = WhisperModel("small.en", device="cpu", compute_type="int8")
                _loading = False
            segments, _ = _model.transcribe(io.BytesIO(audio))
            return llm_client.redact(
                " ".join(segment.text.strip() for segment in segments)
            )
    except Exception as exc:
        raise ValueError(
            "Local transcription failed; check microphone audio and voice installation"
        ) from exc
    finally:
        _loading = False


@router.post("/api/stt")
async def stt(request: Request):
    engine = status()["engine"]
    if engine is None:
        raise ValueError("No speech engine available")
    content_type = request.headers.get("content-type", "")
    if (
        not content_type.startswith("multipart/form-data;")
        or "\n" in content_type
        or "\r" in content_type
    ):
        raise ValueError("Expected multipart audio")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_AUDIO:
            raise ValueError("Audio exceeds 10 MiB limit")
    message = BytesParser(policy=policy.default).parsebytes(
        ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode()
        + data
    )
    parts = [
        p
        for p in message.walk()
        if p.get_param("name", header="content-disposition") == "audio"
    ]
    if len(parts) != 1:
        raise ValueError("One audio field is required")
    audio = parts[0].get_payload(decode=True)
    if not audio:
        raise ValueError("Audio is empty")
    return {"text": await run_in_threadpool(transcribe, audio, engine)}
