"""Ask the local dialogue model. The phrase router is only the fallback."""

import json
from urllib import error, request

from simulator.main import dialogue_pack

ENDPOINT = "http://127.0.0.1:8012/reply"

_KINDS = ("greeting", "product", "decision", "finding", "explain", "offtopic")
_ALLOWED = {"greeting", "product", "decision", "finding", "explain"}
REFUSAL = (
    "I only answer questions about FleetOps. Ask about a service on this board, what is wrong, "
    "or what Approve, Reject, and Override do. I will not write other material or answer anything outside this product."
)
_BLOCKED = (
    "poem", "essay", "short story", "joke", "homework", "resume", "cover letter",
    "lyrics", "recipe", "weather", "stock price", "write code", "python script",
    "love letter", "song", "novel", "blog post",
)

_SORT = """Sort the question into one word: greeting, product, decision, finding, explain, offtopic.
greeting: hello, wassup, what's up, how are you, thanks, okay.
product: how's the build, what is this app, are we ready for the demo, who are you.
decision: what happens if we override, approve, or reject.
finding: what's wrong, how bad, a heads-up, status of a service.
explain: I don't understand this screen, what do I do here, what is SEV-1.
offtopic: write a poem, write code, tell a joke, homework, weather, email, anything that is not this board.
Reply with that one word and nothing else."""


def answer(service_id: str | None, question: str) -> str | None:
    asked = " ".join((question or "").split())
    if not asked:
        return None
    pack = dialogue_pack(service_id)
    if _blocked(asked):
        return REFUSAL
    kind = _product_kind(asked)
    if kind is None:
        kind = _sort(asked)
        if kind is None:
            return None
        if kind not in _ALLOWED:
            return REFUSAL
    if kind == "decision":
        anchor = service_id or (pack["selected"] or {}).get("service_id")
        if anchor:
            from simulator.main import explain_decision

            return explain_decision(anchor, asked)[:1800]
    if kind == "finding":
        from simulator.main import _named_service, _read

        if _named_service(asked, _read()["services"]):
            return None
    reply = _ask(
        "You are FleetOps, the Fleet Commander. Speak in short ordinary sentences to someone who may know nothing about software. "
        "Say you, not they. Use only the facts given. Do not invent buttons, numbers, or versions.",
        _prompt(kind, asked, pack),
        160,
    )
    if not reply:
        return None
    reply = _trim_echo(reply, asked)
    if kind == "finding" and "source:" not in reply.lower():
        reply = reply.removesuffix("Source").strip().rstrip(".")
        reply = reply + ". Source: Scenario fallback."
    return reply[:1800] or None


def _prompt(kind: str, question: str, pack: dict) -> str:
    selected = pack["selected"]
    name = selected["service_id"] if selected else "nothing"
    if kind == "greeting":
        facts = "No service facts. This is only a hello."
        task = "Give one short greeting and ask what they want to know about this board. Do not mention a service or a number. Do not invite questions outside FleetOps."
    elif kind == "product":
        facts = (
            "The board, the chat, and the fleet work. "
            "A service lookup calls Amazon Bedrock. If Bedrock is unavailable the source line says Scenario fallback. "
            "The board is the Alexa+ client: it calls the MCP server with initialize, tools/list, and tools/call. "
            "Alexa uses this same agent for what's wrong, approve, reject, and tell me."
        )
        task = "Say how the product is coming along. Do not mention a broken service."
    elif kind == "decision":
        facts = _selected_facts(selected) or "No service is open on screen."
        facts += (
            " Approve runs the suggested fix and the service becomes healthy. "
            "Override does not run the suggested fix. You type a different action and a different target, then press Execute. "
            "Until Execute, the service stays as it is. "
            "Reject does not run the fix. The service stays broken and is marked triage."
        )
        task = f"Explain only the choice asked about, for {name}. Do not pretend override runs the suggested fix."
    elif kind == "finding":
        facts = "\n".join(pack["open_lines"]) or "Nothing is broken."
        task = "Say what is wrong, in plain words, using these facts. End with the Source line."
    elif kind == "explain":
        on_screen = f" The service on screen is {name}." if selected else ""
        facts = (
            "The left side lists broken services under Open, and fine ones under Fleet. "
            "The middle is the service they picked. "
            "Approve does the suggested fix and the service becomes healthy. "
            "Reject leaves it broken and marks it triage. "
            "Override lets them pick a different fix, and nothing happens until Execute. "
            "They can also type a question in the box at the bottom. The right side keeps every message. There is no question-mark button."
            + on_screen
        )
        task = "Explain the screen as if they have never seen it, and tell them what they can do next."
    else:
        facts = _selected_facts(selected) or "No service is open."
        facts += f"\nBroken count: {pack['open_count']}. Fine count: {pack['healthy_count']}."
        task = "This question is outside FleetOps. Say only that you cannot help with it."
    return f"Facts:\n{facts}\n\nQuestion: {question}\n\n{task}"


def _selected_facts(selected: dict | None) -> str:
    if not selected:
        return ""
    if selected["status"] == "HEALTHY":
        return f"{selected['service_id']} is fine, live {selected['version']}. Nothing is waiting."
    return (
        f"{selected['service_id']} is {selected['status']}, {selected.get('severity') or 'open'}, "
        f"live {selected['version']}, {selected['error_rate'] * 100:.1f}% of calls failing. "
        f"Suggested fix: {selected.get('recommended_action')} to {selected.get('target')}."
    )


def _product_kind(question: str) -> str | None:
    """Product questions are never refused, even if the sorter misses them."""
    from agent.conversation import is_decision_talk, is_open_incident_talk, is_product_aside, is_small_talk
    from agent.project_knowledge import is_incident_question, is_project_question

    lowered = question.lower()
    if is_decision_talk(question) or any(word in lowered for word in ("approve", "reject", "override")):
        return "decision"
    if is_incident_question(question) or is_open_incident_talk(question):
        return "finding"
    if is_product_aside(question):
        return "product"
    if is_project_question(question):
        return "explain"
    if is_small_talk(question):
        return "greeting"
    return None


def _blocked(question: str) -> bool:
    lowered = question.lower()
    return any(cue in lowered for cue in _BLOCKED)


def _sort(question: str) -> str | None:
    word = _ask(_SORT, f"Question: {question}", 8)
    if word is None:
        return None
    kind = "".join(ch for ch in word.lower().split(" ")[0] if ch.isalpha())
    return kind if kind in _ALLOWED else "offtopic"


def _ask(system: str, user: str, max_tokens: int) -> str | None:
    try:
        body = json.dumps({
            "system": system,
            "user": user,
            "max_tokens": max_tokens,
            "temperature": 0,
        }).encode()
        req = request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=50) as response:
            payload = json.loads(response.read().decode())
    except (error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    reply = " ".join(str(payload.get("reply") or "").split())
    return reply or None


def _trim_echo(reply: str, question: str) -> str:
    asked = question.strip().rstrip("?").lower()
    kept = []
    for sentence in reply.split(". "):
        plain = sentence.strip().rstrip("?").lower()
        if plain == asked or plain.endswith(asked):
            continue
        kept.append(sentence)
    return ". ".join(kept).strip()
