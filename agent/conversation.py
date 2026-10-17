"""Spoken replies for ordinary conversation. Incident findings stay on the analyze path."""


_GREETINGS = (
    "what's up",
    "whats up",
    "what is up",
    "wassup",
    "whatsup",
    "what up",
    "how are you",
    "how're you",
    "howre you",
    "how's it going",
    "hows it going",
    "how is it going",
    "how's everything",
    "hows everything",
    "how are things",
    "how do you do",
    "how you doing",
    "how're you doing",
    "good morning",
    "good evening",
    "good afternoon",
    "good night",
    "are you there",
    "you there",
)

_EXACT = {
    "hi",
    "hey",
    "hello",
    "yo",
    "sup",
    "thanks",
    "thank you",
    "ty",
    "ok",
    "okay",
    "k",
    "cool",
    "nice",
    "great",
    "bye",
    "goodbye",
    "test",
    "testing",
    "lol",
    "haha",
    "nm",
    "nothing",
    "not much",
    "all good",
}

_IDENTITY = (
    "who are you",
    "what are you",
    "what's your name",
    "whats your name",
    "your name",
    "introduce yourself",
)

_CAPABILITY = (
    "what can you",
    "what do you do",
    "what are you for",
    "how can you help",
    "can you help",
    "help me",
    "what should i ask",
)

_OPEN = (
    "talk about this",
    "this service",
    "this incident",
    "the incident",
    "open incident",
    "this one",
    "the open one",
    "what's wrong",
    "whats wrong",
    "what is wrong",
    "what wrong",
    "what happened",
    "how bad",
    "error rate",
    "is it healthy",
    "is this healthy",
    "status of this",
    "the status",
    "its status",
    "the log",
    "root cause",
    "suggested fix",
    "the fix",
    "more detail",
    "more details",
    "go deeper",
    "in detail",
    "tell me more",
    "elaborate",
    "full picture",
    "break it down",
    "go more",
    "everything about",
    "explain everything",
    "explain this",
    "explain it",
    "explain the service",
    "explain the incident",
)


def _plain(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split()).strip(" ?.!,")


def is_product_aside(text: str) -> bool:
    """A question about the product itself, not a fleet service."""
    lowered = _plain(text)
    cues = (
        "the build",
        "the project",
        "the app",
        "the application",
        "the product",
        "the hackathon",
        "the demo",
        "our build",
        "this build",
        "it looking",
    )
    return any(cue in lowered for cue in cues) and not any(
        word in lowered for word in ("service", "fleet", "incident", "error")
    )


def is_decision_talk(text: str) -> bool:
    """A question about approve, reject, or override, rather than a status check."""
    lowered = _plain(text)
    return any(
        cue in lowered
        for cue in (
            "override",
            "what happens if",
            "what if we",
            "what if i",
            "if we approve",
            "if we reject",
            "if i approve",
            "if i reject",
        )
    )


def is_small_talk(text: str) -> bool:
    lowered = _plain(text)
    if not lowered or lowered in _EXACT:
        return True
    if any(lowered == cue or lowered.startswith(cue + " ") for cue in _GREETINGS + _IDENTITY):
        return True
    return False


def is_open_incident_talk(text: str) -> bool:
    """True when the operator is asking about the service already on screen."""
    lowered = _plain(text)
    if any(cue in lowered for cue in ("explain yourself", "explain who", "who are you", "what are you")):
        return False
    if lowered in {"talk about this service", "talk about this"}:
        return True
    if any(cue in lowered for cue in _OPEN):
        return True
    words = lowered.split()
    if len(words) <= 4 and any(word in words for word in ("explain", "details", "detail", "deeper", "elaborate")):
        return True
    if "why" in words and any(word in words for word in ("it", "this", "service", "error", "incident", "log", "pool")):
        return True
    return False


def reply(text: str, service_id: str | None) -> str:
    lowered = _plain(text)
    if any(lowered == cue or lowered.startswith(cue) for cue in ("thanks", "thank you", "ty")):
        return "Anytime."
    if lowered in {"ok", "okay", "k", "cool", "nice", "great"}:
        return "Got it. I'm here when you want to look at a service, the fleet, or how this product works."
    if lowered in {"bye", "goodbye"}:
        return "I'll be here. The command record keeps what we already said."
    if any(lowered == cue or lowered.startswith(cue) for cue in _IDENTITY) or "who are you" in lowered:
        return _identity(service_id)
    if any(cue in lowered for cue in _CAPABILITY) or lowered in {"help", "commands", "command"}:
        return _capability(service_id)
    if is_product_aside(lowered):
        return _build()
    if is_small_talk(lowered):
        return _greeting(lowered)
    if is_decision_talk(lowered):
        return "Tell me which service you mean, or open one, and I'll walk through override, approve, or reject."
    return _general(service_id)


def _build() -> str:
    return (
        "The build is in good shape for a demo. The board, the chat, and the fleet all work. "
        "Bedrock is still blocked on the account, so when I investigate a service I say Scenario fallback. "
        "Alexa+ is the piece that is not wired yet."
    )


def _greeting(text: str) -> str:
    if text.startswith("how ") or text.startswith("how's ") or text.startswith("hows "):
        return "I'm good. What do you want to know about this board?"
    if text.startswith("good "):
        words = text.split()
        salutation = " ".join(words[:2]).capitalize() if len(words) >= 2 else "Hey"
        return f"{salutation}. What do you want to know about this board?"
    return "Hey. What do you want to know about this board?"


def _identity(service_id: str | None) -> str:
    watching = f" You have {service_id} open." if service_id else ""
    return (
        "I'm OpsPilot. I only talk about this board. "
        "I read a service when you ask, I explain what I find, and I wait for your approve before anything changes. "
        "I will not write other material or answer questions outside this product."
        + watching
    )


def _capability(service_id: str | None) -> str:
    focus = f" You have {service_id} open, so you can ask what's wrong with it." if service_id else ""
    return (
        "I only help with this product. "
        "Ask what's wrong with a service and I investigate it: Bedrock when the account allows it, otherwise I say Scenario fallback out loud. "
        "Ask how the fleet is and I count what's open. "
        "Say approve or reject only when you mean the decision. "
        "Ask how a button, a route, or a file in this repository works and I read the project and answer. "
        "Everything you and I say stays in the command record."
        + focus
    )


def _general(service_id: str | None) -> str:
    return (
        "I only answer questions about OpsPilot. Ask about a service on this board, what is wrong, "
        "or what Approve, Reject, and Override do. I will not write other material or answer anything outside this product."
    )
