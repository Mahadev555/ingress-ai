"""Encrypt provider credentials at rest.

Provider API keys are more sensitive than most rows, so when a
``CREDENTIAL_ENCRYPTION_KEY`` is configured we encrypt them with Fernet
(AES-CBC + HMAC) before they touch the database, and decrypt only in-process
when building an upstream request. Values are tagged with an ``enc:`` prefix so
encrypted and plaintext rows can coexist (e.g. env-seeded keys, or a database
created before a key was set).

If no encryption key is configured the value is stored as plaintext — fine for
local dev, but production should set the key. Either way the key is **never**
returned by the admin API; the dashboard only ever sees a "set/masked" flag.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger("ingress.secrets")

_ENC_PREFIX = "enc:"


def _fernet() -> Fernet | None:
    """A Fernet built from the configured passphrase, or None if unset.

    Any passphrase is accepted: it's hashed to a valid 32-byte Fernet key, so
    operators don't have to generate a base64 key by hand.
    """
    passphrase = get_settings().credential_encryption_key
    if not passphrase:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(passphrase.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage. Returns plaintext unchanged when no
    encryption key is configured (with a one-time warning)."""
    if not plaintext:
        return plaintext
    fernet = _fernet()
    if fernet is None:
        logger.warning(
            "CREDENTIAL_ENCRYPTION_KEY not set — storing provider keys as plaintext"
        )
        return plaintext
    return _ENC_PREFIX + fernet.encrypt(plaintext.encode()).decode()


def decrypt(stored: str) -> str:
    """Decrypt a stored secret. Plaintext (untagged) values pass through, so a
    DB with mixed encrypted/plaintext rows still works."""
    if not stored or not stored.startswith(_ENC_PREFIX):
        return stored  # plaintext / env-seeded
    fernet = _fernet()
    if fernet is None:
        logger.error("encrypted credential found but CREDENTIAL_ENCRYPTION_KEY is not set")
        return ""
    try:
        return fernet.decrypt(stored[len(_ENC_PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.error("failed to decrypt a provider credential (wrong encryption key?)")
        return ""
