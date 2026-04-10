"""Shared rate limiter configuration.

All routers import `limiter` from here so per-endpoint decorators
and the main app middleware share the same backend store.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_client_ip(request: Request) -> str:
    """Get real client IP from Cloudflare/Railway proxy headers."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Single limiter instance used by main.py and per-router decorators.
# Default limits apply to every endpoint unless it specifies its own.
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["200/minute", "2000/hour"],
)
