from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
	pass


def _new_id() -> str:
	return str(uuid.uuid4())


def _utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()


class ReportType(str, enum.Enum):
	LOST = "lost"
	FOUND = "found"


class ReportStatus(str, enum.Enum):
	ACTIVE = "active"
	CLOSED = "closed"


class MatchDecisionStatus(str, enum.Enum):
	PENDING = "pending"
	ACCEPTED = "accepted"
	REJECTED = "rejected"
	CLAIMED = "claimed"


class MatchEventType(str, enum.Enum):
	DECISION = "decision"
	NOTIFICATION = "notification"


class User(Base):
	__tablename__ = "users"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
	full_name: Mapped[str] = mapped_column(String(255))
	password_hash: Mapped[str] = mapped_column(String(255))
	phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
	avatar_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now)


class ItemReport(Base):
	__tablename__ = "item_reports"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
	item_type: Mapped[ReportType] = mapped_column(Enum(ReportType), index=True)
	title: Mapped[str] = mapped_column(String(255), index=True)
	description: Mapped[str] = mapped_column(Text)
	category: Mapped[str] = mapped_column(String(120), default="other")
	location: Mapped[str] = mapped_column(String(255), default="unknown")
	event_date: Mapped[str] = mapped_column(String(64), default="")
	status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.ACTIVE, index=True)
	image_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now, index=True)


class MatchCandidate(Base):
	__tablename__ = "match_candidates"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	lost_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("item_reports.id"), index=True)
	found_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("item_reports.id"), index=True)
	text_score: Mapped[float] = mapped_column(Float, default=0.0)
	image_score: Mapped[float] = mapped_column(Float, default=0.0)
	confidence: Mapped[float] = mapped_column(Float, index=True)
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now)


class MatchDecision(Base):
	__tablename__ = "match_decisions"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	lost_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("item_reports.id"), index=True)
	found_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("item_reports.id"), index=True)
	status: Mapped[MatchDecisionStatus] = mapped_column(Enum(MatchDecisionStatus), default=MatchDecisionStatus.PENDING)
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now)


class MatchEvent(Base):
	__tablename__ = "outbox_events"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	lost_item_id: Mapped[str] = mapped_column(String(36), index=True)
	found_item_id: Mapped[str] = mapped_column(String(36), index=True)
	event_type: Mapped[MatchEventType] = mapped_column(Enum(MatchEventType), default=MatchEventType.DECISION)
	payload: Mapped[str] = mapped_column(Text, default="")
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now)


class DeviceToken(Base):
	__tablename__ = "device_tokens"

	id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
	user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
	token: Mapped[str] = mapped_column(String(512), unique=True)
	platform: Mapped[str] = mapped_column(String(32), default="expo")
	created_at: Mapped[str] = mapped_column(String(64), default=_utc_now)
