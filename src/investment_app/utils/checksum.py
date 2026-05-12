"""Checksum utilities for raw-data integrity verification."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_str(text: str) -> str:
    """Return the SHA-256 hex digest of a UTF-8 encoded string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    """Return the SHA-256 hex digest of a JSON-serialised object.

    Keys are sorted so the result is independent of insertion order.
    """
    serialised = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return sha256_str(serialised)
