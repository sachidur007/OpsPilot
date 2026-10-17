"""Local language model for the command-center conversation. Run with the dialogue venv."""

import os

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from fastapi import FastAPI
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler
from pydantic import BaseModel

MODEL_ID = os.getenv("OPSPILOT_DIALOGUE_MODEL", "mlx-community/Qwen2.5-3B-Instruct-4bit")
print(f"loading {MODEL_ID}", flush=True)
model, tokenizer = load(MODEL_ID)
print("dialogue ready", flush=True)

app = FastAPI(title="OpsPilot dialogue")


class ReplyRequest(BaseModel):
    system: str
    user: str
    max_tokens: int = 180
    temperature: float = 0.0


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID}


@app.post("/reply")
def reply(req: ReplyRequest):
    messages = [
        {"role": "system", "content": req.system},
        {"role": "user", "content": req.user},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    text = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max(8, min(req.max_tokens, 300)),
        verbose=False,
        sampler=make_sampler(temp=max(0.0, min(req.temperature, 1.0))),
    )
    if not isinstance(text, str):
        text = str(text)
    if text.startswith(prompt):
        text = text[len(prompt):]
    cleaned = " ".join(text.strip().split())
    return {"reply": cleaned[:1800]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8012)
