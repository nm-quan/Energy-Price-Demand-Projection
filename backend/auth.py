"""JWT authentication for the energy broker API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import JWTError, jwt
from passlib.context import CryptContext

from models import Broker

# ── Config ───────────────────────────────────────────────────────────────────

SECRET_KEY = "demo-secret-key-change-in-prod"
ALGORITHM = "HS256"
EXPIRY_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# ── Demo broker store ────────────────────────────────────────────────────────

DEMO_BROKERS = {
    "broker-1": {
        "id": "broker-1",
        "name": "Alex Chen",
        "email": "broker@demo.com",
        "firm": "Energia Advisory",
        # bcrypt hash of "demo1234"
        "password_hash": pwd_context.hash("demo1234"),
    }
}

BROKER_BY_EMAIL = {b["email"]: b for b in DEMO_BROKERS.values()}


# ── Token helpers ─────────────────────────────────────────────────────────────

def create_token(broker_id: str) -> str:
    """Create a JWT for the given broker_id with 24-hour expiry."""
    expire = datetime.now(timezone.utc) + timedelta(hours=EXPIRY_HOURS)
    payload = {"sub": broker_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> str:
    """Decode token and return broker_id, or raise HTTP 401."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        broker_id: Optional[str] = payload.get("sub")
        if broker_id is None:
            raise credentials_exception
        return broker_id
    except JWTError:
        raise credentials_exception


def get_current_broker(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Broker:
    """FastAPI dependency: validate Bearer token and return Broker object."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    broker_id = verify_token(credentials.credentials)
    broker_data = DEMO_BROKERS.get(broker_id)
    if broker_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broker not found",
        )
    return Broker(
        id=broker_data["id"],
        name=broker_data["name"],
        email=broker_data["email"],
        firm=broker_data["firm"],
    )


def authenticate_broker(email: str, password: str) -> Optional[Broker]:
    """Verify credentials; return Broker if valid, else None."""
    broker_data = BROKER_BY_EMAIL.get(email)
    if broker_data is None:
        return None
    if not pwd_context.verify(password, broker_data["password_hash"]):
        return None
    return Broker(
        id=broker_data["id"],
        name=broker_data["name"],
        email=broker_data["email"],
        firm=broker_data["firm"],
    )
