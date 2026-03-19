"""Auth service — password hashing, JWT tokens, register/login."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode

import aiosqlite

from maelstrom.db import user_repo

logger = logging.getLogger(__name__)

_SECRET = os.environ.get("MAELSTROM_JWT_SECRET", "maelstrom-dev-secret-change-me")
_TOKEN_TTL = 86400 * 7  # 7 days


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${h}"


def verify_password(password: str, password_hash: str) -> bool:
    parts = password_hash.split("$")
    if len(parts) != 2:
        return False
    salt, stored = parts
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(h, stored)


def create_token(user_id: str, username: str) -> str:
    header = urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = urlsafe_b64encode(json.dumps({
        "sub": user_id, "username": username,
        "exp": int(time.time()) + _TOKEN_TTL,
        "jti": str(uuid.uuid4()),
    }).encode()).decode().rstrip("=")
    sig = hmac.new(_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header, payload, sig = parts
    expected = hmac.new(_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    # Pad base64
    padded = payload + "=" * (-len(payload) % 4)
    try:
        data = json.loads(urlsafe_b64decode(padded))
    except Exception:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data


async def register(db: aiosqlite.Connection, username: str, email: str, password: str) -> dict:
    existing = await user_repo.get_by_username(db, username)
    if existing:
        raise ValueError("Username already taken")
    pw_hash = hash_password(password)
    return await user_repo.create_user(db, username, email, pw_hash)


async def login(db: aiosqlite.Connection, username: str, password: str) -> str:
    user = await user_repo.get_by_username(db, username)
    if not user or not verify_password(password, user["password_hash"]):
        raise ValueError("Invalid credentials")
    return create_token(user["id"], user["username"])
