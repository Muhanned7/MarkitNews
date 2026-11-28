from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def is_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    em = email.strip().lower()
    raw_list = os.environ.get("ADMIN_EMAILS", "admin@marketpulse.ai,dev@marketpulse.ai")
    allowed = {x.strip().lower() for x in raw_list.split(",") if x.strip()}
    return em in allowed


def create_token(user_id: int, email: str, role: Optional[str] = None) -> str:
    resolved_role = role or ("admin" if is_admin_email(email) else "user")
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": resolved_role,
        "is_admin": resolved_role == "admin",
        "exp": datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def require_admin_or_service(
    authorization: Optional[str] = Header(None),
    x_service_key: Optional[str] = Header(None)
) -> dict:
    user = get_service_or_user(authorization=authorization, x_service_key=x_service_key)
    if user.get("role") in ("admin", "service") or user.get("is_admin") or is_admin_email(user.get("email")):
        return user
    raise HTTPException(status_code=403, detail="Forbidden: developer admin account required")

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    payload = decode_token(credentials.credentials)
    if "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token: missing subject claim")
    return payload

import hmac

INTERNAL_SERVICE_KEY = os.environ.get("INTERNAL_SERVICE_KEY")

def get_service_or_user(
    authorization: Optional[str] = Header(None),
    x_service_key: Optional[str] = Header(None)
) -> dict:
    # 1. Always decode the user's Bearer token first when present so user identity & tier checks work
    #    even when the Next.js proxy attaches X-Service-Key on every request.
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            payload = decode_token(parts[1])
            if "sub" in payload:
                return payload
    # 2. Fall back to internal service identity only for background/server-only calls without a user JWT
    if x_service_key and INTERNAL_SERVICE_KEY:
        try:
            if hmac.compare_digest(x_service_key.encode("utf-8"), INTERNAL_SERVICE_KEY.encode("utf-8")):
                return {"sub": "internal-service", "role": "service"}
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Unauthorized: valid bearer token or service key required")