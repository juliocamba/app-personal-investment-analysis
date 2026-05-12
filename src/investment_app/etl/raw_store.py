"""Raw provider payload storage.

Stores raw provider responses into ``provider_requests`` and
``raw_provider_payloads`` before any normalisation step.

Duplicate detection uses a SHA-256 checksum over provider + endpoint + params
+ payload so the same response is never stored twice.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from investment_app.connectors.base import ProviderResponse
from investment_app.utils.checksum import sha256_json
from investment_app.utils.dates import utc_now

logger = logging.getLogger(__name__)

# Only accept the safe short-form produced by sanitized connectors:
# "{provider_tag}_request_failed ({ExcClassName})"  e.g. "fmp_request_failed (ConnectError)"
# Any other value — including raw exception text, URLs, or credentials — is
# replaced with a fixed placeholder before persistence.
_SAFE_ERROR_RE = re.compile(r"^[a-z0-9_]+ \([A-Za-z0-9_]+\)$")
_MAX_ERROR_LEN = 120


def _sanitize_provider_error(msg: str | None) -> str | None:
    """Return *msg* if it matches the safe connector tag format, else a placeholder.

    Acts as a belt-and-suspenders defence: even if a connector accidentally
    passes raw exception text, URLs, keys, or credentials this function ensures
    they are never persisted to ``provider_requests.error_message``.
    """
    if msg is None:
        return None
    if len(msg) <= _MAX_ERROR_LEN and _SAFE_ERROR_RE.match(msg):
        return msg
    return "provider_error_sanitized"


def _make_checksum(response: ProviderResponse) -> str:
    """Return a deterministic checksum over the response contents."""
    data = {
        "provider": response.provider,
        "endpoint": response.endpoint,
        "params": response.params,
        "payload": response.payload,
        "payload_text": response.payload_text,
    }
    return sha256_json(data)


def store_raw_response(
    response: ProviderResponse,
    company_id: str | None,
    *,
    client: Any = None,
) -> str | None:
    """Persist a ProviderResponse to Supabase raw storage tables.

    Inserts a row into ``provider_requests`` and, if the checksum has not been
    seen before, a row into ``raw_provider_payloads``.

    Args:
        response: The provider response to store.
        company_id: UUID of the associated company row, or ``None``.
        client: Optional Supabase client for testing.

    Returns:
        The UUID of the ``raw_provider_payloads`` row, or ``None`` if the
        response had no payload to store.
    """
    from investment_app.db.supabase_client import get_supabase_client

    db = client or get_supabase_client()
    checksum = None
    if response.payload is not None or response.payload_text is not None:
        checksum = _make_checksum(response)

    # 1. Insert provider_requests record (always, regardless of duplicate).
    req_payload: dict[str, Any] = {
        "provider": response.provider,
        "endpoint": response.endpoint,
        "request_params": response.params,
        "requested_at": utc_now().isoformat(),
        "status_code": response.status_code,
        "success": response.success,
    }
    if checksum is not None:
        req_payload["response_checksum"] = checksum
    if response.error_message:
        req_payload["error_message"] = _sanitize_provider_error(response.error_message)
    if company_id:
        req_payload["company_id"] = company_id

    req_resp = db.table("provider_requests").insert(req_payload).execute()
    request_id: str | None = req_resp.data[0]["id"] if req_resp.data else None

    # 2. Only store raw payload when there is something to store.
    if response.payload is None and response.payload_text is None:
        logger.debug(
            "No payload to store for %s / %s", response.provider, response.endpoint
        )
        return None

    # 3. Check for duplicate checksum — skip insert if already stored.
    existing = (
        db.table("raw_provider_payloads")
        .select("id")
        .eq("checksum", checksum)
        .limit(1)
        .execute()
    )
    if existing.data:
        logger.debug(
            "Duplicate checksum %s for %s / %s — skipping insert",
            checksum[:12],
            response.provider,
            response.endpoint,
        )
        return existing.data[0]["id"]

    # 4. Insert the raw payload.
    raw_payload: dict[str, Any] = {
        "provider": response.provider,
        "endpoint": response.endpoint,
        "request_params": response.params,
        "checksum": checksum,
        "fetched_at": utc_now().isoformat(),
    }
    if request_id:
        raw_payload["provider_request_id"] = request_id
    if company_id:
        raw_payload["company_id"] = company_id
    if response.payload is not None:
        raw_payload["payload"] = response.payload
    if response.payload_text is not None:
        raw_payload["payload_text"] = response.payload_text

    raw_resp = db.table("raw_provider_payloads").insert(raw_payload).execute()
    if not raw_resp.data:
        logger.error(
            "Failed to insert raw payload for %s / %s",
            response.provider,
            response.endpoint,
        )
        return None

    raw_id: str = raw_resp.data[0]["id"]
    logger.debug(
        "Stored raw payload %s for %s / %s", raw_id[:8], response.provider, response.endpoint
    )
    return raw_id

