"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin, require_user
from app.core.security import create_access_token
from app.schemas.token import LoginRequest, LoginResponse, RefreshRequest, Token
from app.schemas.user import UserCreate, UserOut
from app.services.auth_service import authenticate_user, issue_tokens, register_user

router = APIRouter()


@router.post("/register", response_model=UserOut, summary="Register a new user")
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    try:
        return await register_user(db, user_in)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=LoginResponse, summary="Login and get tokens")
async def login(login_in: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, login_in.username, login_in.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token, refresh_token = issue_tokens(user)
    return LoginResponse(
        user=UserOut.model_validate(user).model_dump(),
        tokens=Token(access_token=access_token, refresh_token=refresh_token),
    )


@router.post("/refresh", response_model=Token, summary="Refresh access token")
async def refresh(refresh_in: RefreshRequest):
    from app.core.security import decode_token
    payload = decode_token(refresh_in.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    access_token = create_access_token(subject=str(payload["sub"]))
    return Token(access_token=access_token, refresh_token=refresh_in.refresh_token)


@router.get("/me", response_model=UserOut, summary="Current user")
async def me(current_user=Depends(require_user)):
    return current_user
