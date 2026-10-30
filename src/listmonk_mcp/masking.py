"""Mask secrets in Listmonk's settings document by key name, on top of Listmonk's own bullet masking.

Listmonk v6.2.0 masks its known secret fields with one bullet per character, which reveals
their length, and a later version may add secrets it doesn't mask. Masking by name covers both.
"""

import re
from typing import Any

MASK = "********"

_SECRET_NAME = re.compile("password|secret", re.IGNORECASE)

# Secret fields whose names don't say so: (parent key, key). None is the top level.
_SECRET_PATHS = frozenset({
    (None, "bounce.sendgrid_key"),
    ("bounce.forwardemail", "key"),
    ("bounce.lettermint", "key"),
})


def _is_secret(parent: str | None, key: str) -> bool:
    return bool(_SECRET_NAME.search(key)) or (parent, key) in _SECRET_PATHS


def mask_settings(data: Any, parent: str | None = None) -> Any:
    """Return a copy of `data` with every non-empty secret string replaced by MASK.

    Items of a list are checked with the list's own parent key, so `smtp[0].password`
    is matched by its name. Empty strings and non-string values are kept as they are.
    """
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str) and value and _is_secret(parent, key):
                masked[key] = MASK
            else:
                masked[key] = mask_settings(value, key)
        return masked
    if isinstance(data, list):
        return [mask_settings(item, parent) for item in data]
    return data
