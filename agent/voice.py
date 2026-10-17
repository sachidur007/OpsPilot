"""Speak whatever the agent found, in the commander's recorded voice."""

import requests

CLONE_URL = "http://127.0.0.1:8011/speak"


def synthesize_speech(text: str) -> bytes:
    spoken = " ".join(text.split())[:600]
    if not spoken:
        spoken = "Nothing to report yet."
    response = requests.post(CLONE_URL, json={"text": spoken}, timeout=180)
    if response.status_code != 200 or not response.content.startswith(b"RIFF"):
        raise RuntimeError("cloned voice did not return audio")
    return response.content
