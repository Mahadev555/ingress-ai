"""Lightweight, opt-in input guardrails.

Deliberately simple and conservative: a small regex screen for the most common
prompt-injection phrasings. It is a speed bump, not a security boundary — real
deployments would layer a dedicated moderation/classifier service on top.
"""

import re
from typing import Optional

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|the) (previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"disregard (all|any|the) (previous|prior|above)", re.I),
    re.compile(r"you are now (a|an|in) ", re.I),
    re.compile(r"reveal (your )?(system prompt|instructions)", re.I),
    re.compile(r"(print|repeat|output) (your )?(system prompt|instructions)", re.I),
]


def screen_text(text: str) -> Optional[str]:
    """Return a short reason if the text trips a guardrail, else None."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return "possible prompt-injection detected"
    return None
