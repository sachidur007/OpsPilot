"""Record the Day 7 reel narration in the commander's cloned voice."""

import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "voice"
OUT.mkdir(parents=True, exist_ok=True)

LINES = [
    "Day seven. I tried to connect this app to the model.",
    "The app works.",
    "Amazon does not.",
    "The screen changed.",
    "The old model is not there anymore.",
    "The use case request was rejected.",
    "Your account is not authorized to perform this action.",
    "Verification is still pending.",
    "The fleet still runs. I can investigate, see the evidence, and get a recommendation. The label says scenario fall back. I am leaving that on screen.",
    "Next. Finish verification. Open Bedrock. Get one real answer. The screen has to show source, Bedrock. And I keep building.",
]


def main() -> None:
    for index, text in enumerate(LINES, start=1):
        path = OUT / f"{index:02d}.wav"
        if path.exists() and path.stat().st_size > 8000:
            print("keep", path.name, flush=True)
            continue
        print("speak", index, text, flush=True)
        request = urllib.request.Request(
            "http://127.0.0.1:8011/speak",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            path.write_bytes(response.read())
        print("wrote", path.name, path.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
