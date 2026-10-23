"""Record the Day 12 reel narration in the commander's cloned voice."""

import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "voice"
OUT.mkdir(parents=True, exist_ok=True)

LINES = [
    "Day twelve. I made a classic developer mistake.",
    "I have been building features, when I should have been preparing the demo.",
    "The command center is running. The incidents work. Recovery is taking shape.",
    "Then I looked at what I actually have to submit.",
    "The Alexa skill is still not built. And the latest code is not committed.",
    "The readme needs work. There is no public demo video. And Devpost is not submitted.",
    "And I am still dealing with the Bedrock blocker.",
    "Building a product, and getting it ready for someone else to judge, are two different jobs.",
    "So the order changes. Secure the code. Make the demo repeatable. Finish Alexa. Then submit.",
    "Eleven days left. The question is not whether I can build FleetOps. It is whether I can get it ready in time.",
    "If you have done a hackathon, what is the one thing you wish you had done earlier?",
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
