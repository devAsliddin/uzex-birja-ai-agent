"""Authentication service."""


from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.crud import crud_api_key, crud_user
from app.db.models.user import User
from app.schemas.user import UserCreate


async def register_user(db, user_in: UserCreate) -> User:
    existing = await crud_user.get_by_email(db, email=user_in.email)
    if existing:
        raise ValueError("Пользователь с таким email уже существует")
    existing_u = await crud_user.get_by_username(db, username=user_in.username)
    if existing_u:
        raise ValueError("Пользователь с таким именем уже существует")
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db, username: str, password: str) -> User | None:
    user = await crud_user.get_by_username(db, username=username)
    if not user:
        user = await crud_user.get_by_email(db, email=username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def issue_tokens(user: User):
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"username": user.username, "role": user.role},
    )
    refresh_token = create_refresh_token(subject=str(user.id))
    return access_token, refresh_token


async def get_user_by_token_payload(db, payload: dict) -> User | None:
    sub = payload.get("sub")
    if sub is None:
        return None
    user = await crud_user.get(db, int(sub))
    if user and user.is_active:
        return user
    return None


async def create_api_key(db, user_id: int, name: str) -> tuple:
    import secrets
    raw = f"uzex_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    from app.core.security import hash_api_key
    api_key = __import__("app.db.models.api_key", fromlist=["ApiKey"]).ApiKey(
        name=name,
        key_hash=hash_api_key(raw),
        key_prefix=prefix,
        user_id=user_id,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, raw


async def verify_api_key_raw(db, raw_key: str):
    prefix = raw_key[:12]
    api_key = await crud_api_key.get_by_prefix(db, key_prefix=prefix)
    if not api_key or not api_key.is_active:
        return None
    from app.core.security import verify_api_key
    if not verify_api_key(raw_key, api_key.key_hash):
        return None
    api_key.last_used_at = __import__("datetime", fromlist=["datetime"]).datetime.now(__import__("datetime", fromlist=["timezone"]).timezone.utc)
    await db.commit()
    return api_key.user
