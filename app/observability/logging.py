import logging
import re

# Patterns for secrets that must never reach the logs.
_REDACTIONS = [
    (re.compile(r"[Bb]earer\s+\S+"), "Bearer ***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]+"), "sk-***"),
    (re.compile(r"(api[-_]?key\"?\s*[:=]\s*\"?)[^\s\"]+", re.IGNORECASE), r"\1***"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    """Scrub secrets (bearer tokens, API keys) out of every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Attach the redacting filter to the root logger's handlers. Idempotent so
    repeated calls (e.g. across test app restarts) don't stack handlers."""
    root = logging.getLogger()
    if getattr(root, "_ingress_configured", False):
        return

    logging.basicConfig(level=level)
    redacting = RedactingFilter()
    for handler in root.handlers:
        handler.addFilter(redacting)

    root._ingress_configured = True  # type: ignore[attr-defined]
