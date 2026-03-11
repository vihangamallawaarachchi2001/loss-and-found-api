from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
	return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
	return pwd_context.verify(plain_password, hashed_password)


def issue_access_token(user_id: str, email: str, expires_minutes: int = 60) -> str:
	now = datetime.now(timezone.utc)
	payload = {
		"sub": user_id,
		"email": email,
		"iss": settings.jwt_issuer,
		"iat": int(now.timestamp()),
		"exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
	}
	return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
