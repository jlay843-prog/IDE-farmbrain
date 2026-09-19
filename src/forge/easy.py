"""Easy desk routing — capability questions vs create/change work."""

from __future__ import annotations

ASK_HINTS = (
    "what can you",
    "what do you",
    "how do i",
    "how does",
    "what is",
    "what are",
    "explain",
    "tell me",
    "help me understand",
    "can you explain",
    "who are you",
    "capabilities",
    "what tools",
    "how to use",
    "what software",
    "what can forge",
)

EDIT_HINTS = (
    "create",
    "add",
    "build",
    "make",
    "write",
    "implement",
    "fix",
    "change",
    "update",
    "rename",
    "delete",
    "remove",
    "scaffold",
    "generate a",
    "set up",
    "setup",
    "draft",
    "code",
)


def classify_easy_prompt(prompt: str) -> str:
    """Return ``ask`` for capability questions, ``edit`` for create/change work."""
    text = (prompt or "").strip().lower()
    if not text:
        return "ask"
    wants_edit = any(hint in text for hint in EDIT_HINTS)
    wants_ask = any(hint in text for hint in ASK_HINTS)
    if wants_ask:
        return "ask"
    if wants_edit:
        return "edit"
    if text.endswith("?") and len(text.split()) <= 14:
        return "ask"
    return "edit"
