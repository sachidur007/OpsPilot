"""One continuous telling, in the commander's voice."""

import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "story"
OUT.mkdir(parents=True, exist_ok=True)

LINES = [
    (
        "01",
        "Here is the board tonight. Three incidents are open, and payment service is the serious one. "
        "The connection pool is exhausted. I asked this screen to call Bedrock. It never got through. "
        "The account is not authorized to perform this action, and verification is still pending.",
    ),
    (
        "02",
        "So what you are looking at is the backup. Roll back, from version two point one point zero, "
        "to two point zero point nine. Right under the name, it still says scenario fallback. "
        "I am leaving that on the screen. When this line says Bedrock, that is the one I wanted. "
        "Until then, I keep building.",
    ),
]


def main() -> None:
    for name, text in LINES:
        path = OUT / f"{name}.wav"
        if path.exists() and path.stat().st_size > 8000:
            print("keep", name, flush=True)
            continue
        print("speak", name, flush=True)
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
