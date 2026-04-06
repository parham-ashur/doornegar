"""Authentication service for invite-only rater access.

Only admins can create accounts. No public signup.
Uses JWT tokens for stateless authentication.
"""

import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # Truncate to 72 bytes (bcrypt limit)
    password = password[:72]
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, username: str, rater_level: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "username": username,
        "rater_level": rater_level,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_rater(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
    rater_level: str = "trained",
) -> User:
    """Create a new rater account. Admin-only operation."""
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        display_name=display_name,
        is_rater=True,
        rater_level=rater_level,
        rater_reliability_score=1.0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"Created rater account: {username}")
    return user


async def get_current_user(db: AsyncSession, token: str) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
