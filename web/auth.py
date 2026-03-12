import os
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import Request, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from web.models import User

SECRET_KEY = os.environ.get("WEB_SECRET_KEY", "change-me-in-production-32-chars!!")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int, email: str, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(request: Request, db: Session) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


def require_admin(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user
