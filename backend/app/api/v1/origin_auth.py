"""Phase G follow-up (Parham 2026-05-11) — origin-or-token gate.

Bots discover `doornegar-production.up.railway.app` from the
frontend bundle (NEXT_PUBLIC_API_URL is baked into the JS) and hit
the Railway origin directly, bypassing Cloudflare entirely. That's
why the Cloudflare WAF + rate-limit rules showed zero matches
against the elevated traffic.

This dependency gates `/api/v1/*` read endpoints so only legitimate
callers reach Neon:

- **Server-side fetches** (Vercel SSR / ourselves) MUST send the
  `X-API-Token` header matching the `BACKEND_API_TOKEN` env var.
- **Real browsers** loading data from doornegar.org pages send
  `Origin: https://doornegar.org` (or a referer); they pass.
- **Bots scraping the Railway URL directly** send neither — they
  get 403.

Feature-flagged: enforcement only activates when `BACKEND_API_TOKEN`
is set in the Railway env. Until then, the dependency is a no-op so
deploys don't break the live site before the env var is provisioned
(Vercel needs a matching `BACKEND_API_TOKEN` env first).

Apply at the router level on `stories.router` and `social.router`
in `app/api/v1/router.py` (or add per-route via `dependencies=`).
"""

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request


_TOKEN_ENV = "BACKEND_API_TOKEN"

# Hosts whose Origin/Referer headers are accepted as legitimate
# browser traffic. Match by substring so subdomains and locale paths
# pass too.
_ALLOWED_HOST_SUBSTRINGS = (
    "doornegar.org",
)


async def require_origin_or_token(request: Request) -> None:
    """Reject requests that aren't from doornegar.org browsers or
    that lack the server-side X-API-Token.

    No-op when BACKEND_API_TOKEN env var is unset (deploy-safe).
    """
    expected_token = os.getenv(_TOKEN_ENV, "")
    if not expected_token:
        return  # feature off — pre-rollout state

    # Server-side caller with the shared token.
    token = request.headers.get("x-api-token") or request.headers.get(
        "X-API-Token", ""
    )
    if token and token == expected_token:
        return

    # Real browser fetch from one of our pages.
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    for host in _ALLOWED_HOST_SUBSTRINGS:
        if host in origin or host in referer:
            return

    raise HTTPException(
        status_code=403,
        detail={
            "error": "forbidden",
            "hint": (
                "This endpoint is only reachable from doornegar.org "
                "or server-side callers with a valid X-API-Token. "
                "Direct access to the Railway origin is blocked."
            ),
        },
    )


# Type alias for routes that want to declare the dependency explicitly:
#   `OriginOrToken = Depends(require_origin_or_token)`
OriginOrToken = Annotated[None, Depends(require_origin_or_token)]
