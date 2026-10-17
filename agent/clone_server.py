"""Speaks any text in the commander's own voice, using the recorded sample."""

import io
import os
import threading
import wave
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from mlx_audio.tts.utils import load

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "voice_data" / "myvoice.wav"
MODEL_ID = os.getenv("VOICE_MODEL", "mlx-community/chatterbox-turbo-fp16")

app = FastAPI(title="OpsPilot voice")
model = None
lock = threading.Lock()


def _wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    audio = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


@app.on_event("startup")
def load_model() -> None:
    global model
    model = load(MODEL_ID)
    model.prepare_conditionals(str(REFERENCE))
    print("voice ready", flush=True)


class SpeakRequest(BaseModel):
    text: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if model is not None else "loading", "voice": "commander"}


@app.post("/speak")
def speak(req: SpeakRequest) -> Response:
    if model is None:
        return Response(status_code=503)
    text = " ".join(req.text.split())[:600] or "Nothing to report yet."
    pieces = []
    sample_rate = 24000
    with lock:
        for result in model.generate(text, ref_audio=str(REFERENCE)):
            pieces.append(np.array(result.audio, dtype=np.float32))
            sample_rate = int(result.sample_rate)
    if not pieces:
        return Response(status_code=500)
    return Response(content=_wav_bytes(np.concatenate(pieces), sample_rate), media_type="audio/wav")
