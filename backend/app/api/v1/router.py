from fastapi import APIRouter

from app.api.v1 import admin, articles, social, sources, stories

api_router = APIRouter()
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(stories.router, prefix="/stories", tags=["stories"])
api_router.include_router(social.router, prefix="/social", tags=["social"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
