import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
	grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))
	database_url: str = os.getenv("DATABASE_URL", "sqlite:///./lostfound.db")
	jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret")
	jwt_issuer: str = os.getenv("JWT_ISSUER", "lostfound-backend")
	uploads_dir: str = os.getenv("UPLOADS_DIR", "uploads")
	match_threshold: float = float(os.getenv("MATCH_THRESHOLD", "0.55"))


settings = Settings()
