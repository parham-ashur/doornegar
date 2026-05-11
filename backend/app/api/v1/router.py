from fastapi import APIRouter, Depends

from app.api.v1 import admin, arcs, articles, auth, feedback, hitl, improvements, lab, ratings, social, sources, stories, submissions, suggestions, worldviews
from app.api.v1.origin_auth import require_origin_or_token

api_router = APIRouter()

# Phase G follow-up (Parham 2026-05-11) — block bots that scrape the
# Railway origin URL directly, bypassing Cloudflare. Feature-flagged
# via BACKEND_API_TOKEN env var: when unset (current state) the gate
# is a no-op, so this deploy is safe before the env var is set on
# Railway + Vercel. See app/api/v1/origin_auth.py for the contract.
# Applied to the public read paths; admin keeps its existing auth
# (already gated by Bearer token via require_admin in admin.py).
_origin_gate = [Depends(require_origin_or_token)]

api_router.include_router(sources.router, prefix="/sources", tags=["sources"], dependencies=_origin_gate)
api_router.include_router(articles.router, prefix="/articles", tags=["articles"], dependencies=_origin_gate)
api_router.include_router(stories.router, prefix="/stories", tags=["stories"], dependencies=_origin_gate)
api_router.include_router(social.router, prefix="/social", tags=["social"], dependencies=_origin_gate)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(ratings.router, prefix="/rate", tags=["ratings"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(lab.router, prefix="/lab", tags=["lab"])
api_router.include_router(suggestions.router, prefix="/suggestions", tags=["suggestions"])
api_router.include_router(improvements.router, prefix="/improvements", tags=["improvements"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["submissions"])
api_router.include_router(hitl.router, prefix="/admin/hitl", tags=["hitl"])
api_router.include_router(arcs.admin_router, prefix="/admin/hitl/arcs", tags=["arcs"])
api_router.include_router(arcs.public_router, prefix="/arcs", tags=["arcs"])
api_router.include_router(worldviews.router, prefix="/worldviews", tags=["worldviews"])
