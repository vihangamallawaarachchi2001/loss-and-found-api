import os
import socket
from dataclasses import dataclass


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.2) -> bool:
	try:
		with socket.create_connection((host, port), timeout=timeout_seconds):
			return True
	except OSError:
		return False


def _default_database_url() -> str:
	explicit = os.getenv("DATABASE_URL")
	if explicit:
		return explicit

	if _is_port_open("127.0.0.1", 5433):
		return "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/lostfound"

	return "sqlite:///./lostfound.db"


@dataclass(frozen=True)
class Settings:
	grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))
	dashboard_port: int = int(os.getenv("DASHBOARD_PORT", "5050"))
	database_url: str = _default_database_url()
	jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret")
	jwt_issuer: str = os.getenv("JWT_ISSUER", "lostfound-backend")
	uploads_dir: str = os.getenv("UPLOADS_DIR", "uploads")
	match_threshold: float = float(os.getenv("MATCH_THRESHOLD", "0.55"))


settings = Settings()
