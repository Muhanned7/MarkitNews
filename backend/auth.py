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

def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

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
    if x_service_key and INTERNAL_SERVICE_KEY:
        try:
            if hmac.compare_digest(x_service_key.encode("utf-8"), INTERNAL_SERVICE_KEY.encode("utf-8")):
                return {"sub": "internal-service", "role": "service"}
        except Exception:
            pass
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            payload = decode_token(parts[1])
            if "sub" in payload:
                return payload
    raise HTTPException(status_code=401, detail="Unauthorized: valid bearer token or service key required")