"""Auth API — register, login, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from maelstrom.db.database import get_db
from maelstrom.schemas.auth import TokenResponse, UserCreate, UserLogin, UserResponse
from maelstrom.services import auth_service
from maelstrom.services.auth_middleware import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserCreate):
    db = await get_db()
    try:
        user = await auth_service.register(db, body.username, body.email, body.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return UserResponse(id=user["id"], username=user["username"], email=user["email"], created_at=user["created_at"])


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin):
    db = await get_db()
    try:
        token = await auth_service.login(db, body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(id=user["id"], username=user["username"], email=user["email"], created_at=user["created_at"])
