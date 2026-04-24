from fastapi import APIRouter

from app.api.v1 import admin, arcs, articles, auth, feedback, hitl, improvements, lab, ratings, social, sources, stories, submissions, suggestions, worldviews

api_router = APIRouter()
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(stories.router, prefix="/stories", tags=["stories"])
api_router.include_router(social.router, prefix="/social", tags=["social"])
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
