"""Authentication endpoints.

Login for raters. Account creation is admin-only (via /admin/raters).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import LoginRequest, Token, UserResponse
from app.services.auth import authenticate_user, create_access_token, get_current_user

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login for invited raters. Returns JWT token."""
    user = await authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_rater:
        raise HTTPException(status_code=403, detail="Account is not authorized for rating")

    token = create_access_token(
        user_id=str(user.id),
        username=user.username,
        rater_level=user.rater_level,
    )
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    authorization: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Get current user info from JWT token."""
    from fastapi import Header

    # Extract token from Authorization header
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.replace("Bearer ", "")
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return UserResponse.model_validate(user)
