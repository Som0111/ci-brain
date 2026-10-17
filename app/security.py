"""Optional shared-secret guard for write / LLM-cost endpoints.

CORS is a browser policy, not authentication: it does not stop curl or any
server-side client. When API_KEY is set, the guarded routes require a matching
`X-API-Key` header; when unset the API stays open (local dev, current public
demo) and that is a deliberate, documented trade-off.
"""

import hmac

from fastapi import Header, HTTPException

from app.config import settings


def require_api_key(x_api_key: str | None = Header(None)) -> None:
    expected = settings.api_key
    if not expected:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")
