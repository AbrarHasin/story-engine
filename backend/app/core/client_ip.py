"""Real client IP behind the AWS edge (spec 002 T021).

API Gateway (REST) -> Lambda Web Adapter -> uvicorn: the socket peer is the adapter on
127.0.0.1. The adapter forwards the API Gateway request context as the
`x-amzn-request-context` header (JSON); `identity.sourceIp` (REST) or `http.sourceIp`
(HTTP API / function URL) is the caller as API Gateway saw it. The last
`X-Forwarded-For` entry (the one the proxy appended) is the fallback. Both are only trusted when TRUST_PROXY_HEADERS is on, since a direct client
could set them.
"""
import json
import logging

from starlette.requests import Request

from app.core.config import settings

logger = logging.getLogger(__name__)


def _from_request_context(raw: str) -> str | None:
    try:
        ctx = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(ctx, dict):
        return None
    for section in ("identity", "http"):
        part = ctx.get(section)
        if isinstance(part, dict) and part.get("sourceIp"):
            return str(part["sourceIp"])
    return None


def client_ip(request: Request, trust_proxy: bool | None = None) -> str | None:
    """Best-known client IP for `request`."""
    trust = settings.TRUST_PROXY_HEADERS if trust_proxy is None else trust_proxy
    if trust:
        raw_ctx = request.headers.get("x-amzn-request-context")
        if raw_ctx:
            ip = _from_request_context(raw_ctx)
            if ip:
                return ip
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # the proxy appends the peer it saw; earlier entries are client-supplied
            last = xff.split(",")[-1].strip()
            if last:
                return last
    return request.client.host if request.client else None
