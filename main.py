from concurrent import futures
from datetime import datetime, timezone
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import grpc
from sqlalchemy import and_, func, inspect, or_, select, text

from app.core.config import settings
from app.core.security import hash_password, issue_access_token, verify_password
from app.domain.entities.user import (
    Base,
    DeviceToken,
    ItemReport,
    MatchCandidate,
    MatchDecision,
    MatchDecisionStatus,
    MatchEvent,
    MatchEventType,
    ReportType,
    ReportStatus,
    User,
)
from app.infrastructure.db.session import SessionLocal, engine
from users import user_pb2, user_pb2_grpc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(value: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in value)
    stop_words = {"the", "a", "an", "of", "for", "to", "in", "on", "and", "is", "was"}
    return {token for token in normalized.split() if token and token not in stop_words}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _image_score(image_paths_left: list[str], image_paths_right: list[str]) -> float:
    if not image_paths_left or not image_paths_right:
        return 0.0
    left_tokens = _tokenize(" ".join(image_paths_left))
    right_tokens = _tokenize(" ".join(image_paths_right))
    return _jaccard(left_tokens, right_tokens)


def _combined_score(text_score: float, image_score: float, has_images: bool) -> float:
    if has_images:
        return text_score * 0.65 + image_score * 0.35
    return text_score


def _item_to_response(item: ItemReport, text_score: float = 0.0, image_score: float = 0.0, confidence: float = 0.0) -> user_pb2.ItemResponse:
    return user_pb2.ItemResponse(
        id=item.id,
        user_id=item.user_id,
        item_type=item.item_type.value,
        title=item.title,
        description=item.description,
        category=item.category,
        location=item.location,
        event_date=item.event_date,
        status=item.status.value,
        image_paths=item.image_paths or [],
        text_score=text_score,
        image_score=image_score,
        confidence=confidence,
        created_at=item.created_at,
    )


def _ensure_default_data() -> None:
    Base.metadata.create_all(bind=engine)


def _upsert_device_token(session, user_id: str, token: str, platform: str = "expo") -> None:
    existing = session.scalar(select(DeviceToken).where(DeviceToken.token == token))
    if existing:
        existing.user_id = user_id
        existing.platform = platform
        return

    session.add(DeviceToken(user_id=user_id, token=token, platform=platform))


def _format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _load_tables_data(limit_per_table: int = 200) -> dict[str, list[dict[str, str]]]:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    output: dict[str, list[dict[str, str]]] = {}

    with engine.connect() as connection:
        for table_name in table_names:
            rows = connection.execute(text(f'SELECT * FROM "{table_name}" LIMIT {limit_per_table}')).mappings().all()
            output[table_name] = [
                {column: _format_cell(value) for column, value in row.items()}
                for row in rows
            ]

    return output


def _build_dashboard_html(selected_table: str | None = None) -> str:
    tables_data = _load_tables_data()
    table_names = sorted(tables_data.keys())
    active = selected_table if selected_table in tables_data else (table_names[0] if table_names else "")
    rows = tables_data.get(active, [])
    columns = list(rows[0].keys()) if rows else []

    tabs = "".join(
        (
            f'<a class="tab {"active" if name == active else ""}" href="/?table={html.escape(name)}">'
            f'{html.escape(name)} <span class="count">{len(tables_data.get(name, []))}</span></a>'
        )
        for name in table_names
    )

    if rows and columns:
        header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(row.get(column, ''))}</td>" for column in columns) + "</tr>"
            for row in rows
        )
        table_markup = f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
    else:
        table_markup = '<div class="empty">No rows in this table.</div>'

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Loss & Found DB Studio</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; margin: 0; background: #f7f8fb; color: #0f172a; }}
    .wrap {{ padding: 24px; }}
    .title {{ font-size: 20px; font-weight: 700; margin: 0 0 12px; }}
    .muted {{ color: #64748b; margin: 0 0 20px; }}
    .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
    .tab {{ text-decoration: none; color: #334155; background: white; border: 1px solid #e2e8f0; padding: 8px 12px; border-radius: 10px; font-size: 13px; }}
    .tab.active {{ border-color: #2563eb; color: #1d4ed8; background: #eff6ff; }}
    .count {{ background: #e2e8f0; color: #334155; border-radius: 10px; padding: 2px 7px; margin-left: 6px; font-size: 12px; }}
    .tab.active .count {{ background: #dbeafe; color: #1d4ed8; }}
    .panel {{ background: white; border: 1px solid #e2e8f0; border-radius: 14px; overflow: auto; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 900px; }}
    th, td {{ text-align: left; font-size: 12px; padding: 10px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #f8fafc; z-index: 1; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: #475569; }}
    .empty {{ padding: 20px; color: #64748b; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="title">Loss & Found DB Studio</h1>
    <p class="muted">Prisma-style read-only table browser for backend data</p>
    <div class="tabs">{tabs or '<span class="muted">No tables found.</span>'}</div>
    <div class="panel">{table_markup}</div>
  </div>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/tables":
            payload = _load_tables_data()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        query = parse_qs(parsed.query)
        selected_table = query.get("table", [None])[0]
        body = _build_dashboard_html(selected_table).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def _run_dashboard_server() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", settings.dashboard_port), DashboardHandler)
    print(f"[{_now_iso()}] DB dashboard available on http://0.0.0.0:{settings.dashboard_port}")
    server.serve_forever()


def _build_matches_for_item(session, item: ItemReport) -> None:
    opposite = ReportType.FOUND if item.item_type == ReportType.LOST else ReportType.LOST
    candidates = session.scalars(
        select(ItemReport).where(
            and_(
                ItemReport.item_type == opposite,
                ItemReport.status == ReportStatus.ACTIVE,
            )
        )
    ).all()

    for other in candidates:
        text_score = _jaccard(_tokenize(f"{item.title} {item.description}"), _tokenize(f"{other.title} {other.description}"))
        image_score = _image_score(item.image_paths or [], other.image_paths or [])
        confidence = _combined_score(text_score, image_score, bool(item.image_paths and other.image_paths))
        if confidence < settings.match_threshold:
            continue

        lost_id = item.id if item.item_type == ReportType.LOST else other.id
        found_id = item.id if item.item_type == ReportType.FOUND else other.id
        candidate = MatchCandidate(
            lost_item_id=lost_id,
            found_item_id=found_id,
            text_score=text_score,
            image_score=image_score,
            confidence=confidence,
        )
        decision = MatchDecision(
            lost_item_id=lost_id,
            found_item_id=found_id,
            status=MatchDecisionStatus.PENDING,
        )
        session.add(candidate)
        session.add(decision)


class AuthService(user_pb2_grpc.AuthServiceServicer):
    def Signup(self, request, context):
        with SessionLocal() as session:
            exists = session.scalar(select(User).where(User.email == request.email))
            if exists:
                context.set_code(grpc.StatusCode.ALREADY_EXISTS)
                context.set_details("Email already registered")
                return user_pb2.AuthResponse()

            user = User(
                email=request.email,
                full_name=request.full_name,
                password_hash=hash_password(request.password),
            )
            session.add(user)
            session.flush()
            _upsert_device_token(session, user.id, f"session:{user.id}")
            session.commit()
            token = issue_access_token(user.id, user.email)
            return user_pb2.AuthResponse(user_id=user.id, email=user.email, full_name=user.full_name, token=token)

    def Login(self, request, context):
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == request.email))
            if not user or not verify_password(request.password, user.password_hash):
                context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                context.set_details("Invalid credentials")
                return user_pb2.AuthResponse()

            _upsert_device_token(session, user.id, f"session:{user.id}")
            session.commit()
            token = issue_access_token(user.id, user.email)
            return user_pb2.AuthResponse(user_id=user.id, email=user.email, full_name=user.full_name, token=token)

    def ForgotPassword(self, request, context):
        return user_pb2.OperationResult(success=True, message=f"Password reset OTP sent to {request.email}")

    def ResetPassword(self, request, context):
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == request.email))
            if not user:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("User not found")
                return user_pb2.OperationResult(success=False, message="User not found")

            user.password_hash = hash_password(request.new_password)
            session.commit()
            return user_pb2.OperationResult(success=True, message="Password has been reset")


class ItemService(user_pb2_grpc.ItemServiceServicer):
    def _create(self, request, item_type: ReportType):
        with SessionLocal() as session:
            item = ItemReport(
                user_id=request.user_id,
                item_type=item_type,
                title=request.title,
                description=request.description,
                category=request.category,
                location=request.location,
                event_date=request.event_date,
                status=ReportStatus.ACTIVE,
                image_paths=list(request.image_paths),
            )
            session.add(item)
            session.flush()
            _build_matches_for_item(session, item)
            session.commit()
            return _item_to_response(item)

    def CreateLostItem(self, request, context):
        return self._create(request, ReportType.LOST)

    def CreateFoundItem(self, request, context):
        return self._create(request, ReportType.FOUND)

    def ListLostItems(self, request, context):
        return self._list_by_type(ReportType.LOST, request)

    def ListFoundItems(self, request, context):
        return self._list_by_type(ReportType.FOUND, request)

    def _list_by_type(self, item_type: ReportType, request):
        limit = request.limit if request.limit > 0 else 50
        offset = request.offset if request.offset >= 0 else 0
        with SessionLocal() as session:
            query = select(ItemReport).where(ItemReport.item_type == item_type).order_by(ItemReport.created_at.desc())
            total = session.scalar(select(func.count()).select_from(ItemReport).where(ItemReport.item_type == item_type)) or 0
            items = session.scalars(query.offset(offset).limit(limit)).all()
            return user_pb2.ListItemsResponse(items=[_item_to_response(item) for item in items], total=total)

    def GetItem(self, request, context):
        with SessionLocal() as session:
            item = session.scalar(select(ItemReport).where(ItemReport.id == request.id))
            if not item:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Item not found")
                return user_pb2.ItemResponse()
            return _item_to_response(item)


class MatchService(user_pb2_grpc.MatchServiceServicer):
    def ListOwnerAlerts(self, request, context):
        with SessionLocal() as session:
            rows = session.execute(
                select(MatchCandidate, MatchDecision, ItemReport)
                .join(MatchDecision, and_(
                    MatchDecision.lost_item_id == MatchCandidate.lost_item_id,
                    MatchDecision.found_item_id == MatchCandidate.found_item_id,
                ))
                .join(ItemReport, ItemReport.id == MatchCandidate.lost_item_id)
                .where(ItemReport.user_id == request.owner_user_id)
                .order_by(MatchCandidate.confidence.desc())
            ).all()

            alerts = [
                user_pb2.OwnerAlert(
                    lost_item_id=candidate.lost_item_id,
                    found_item_id=candidate.found_item_id,
                    text_score=candidate.text_score,
                    image_score=candidate.image_score,
                    confidence=candidate.confidence,
                    status=decision.status.value,
                )
                for candidate, decision, _ in rows
            ]
            return user_pb2.ListOwnerAlertsResponse(alerts=alerts)

    def _update_decision(self, request, status: MatchDecisionStatus):
        with SessionLocal() as session:
            decision = session.scalar(
                select(MatchDecision).where(
                    and_(
                        MatchDecision.lost_item_id == request.lost_item_id,
                        MatchDecision.found_item_id == request.found_item_id,
                    )
                )
            )
            if not decision:
                return user_pb2.OperationResult(success=False, message="Match decision not found")

            decision.status = status
            session.add(MatchEvent(
                lost_item_id=request.lost_item_id,
                found_item_id=request.found_item_id,
                event_type=MatchEventType.DECISION,
                payload=f"{request.decided_by_user_id}:{status.value}",
            ))

            if status == MatchDecisionStatus.CLAIMED:
                lost = session.scalar(select(ItemReport).where(ItemReport.id == request.lost_item_id))
                found = session.scalar(select(ItemReport).where(ItemReport.id == request.found_item_id))
                if lost:
                    lost.status = ReportStatus.CLOSED
                if found:
                    found.status = ReportStatus.CLOSED
            session.commit()
            return user_pb2.OperationResult(success=True, message=f"Match {status.value}")

    def AcceptMatch(self, request, context):
        return self._update_decision(request, MatchDecisionStatus.ACCEPTED)

    def RejectMatch(self, request, context):
        return self._update_decision(request, MatchDecisionStatus.REJECTED)

    def MarkClaimed(self, request, context):
        return self._update_decision(request, MatchDecisionStatus.CLAIMED)


class ProfileService(user_pb2_grpc.ProfileServiceServicer):
    def GetProfile(self, request, context):
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.id == request.user_id))
            if not user:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Profile not found")
                return user_pb2.ProfileResponse()
            return user_pb2.ProfileResponse(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone or "",
                avatar_path=user.avatar_path or "",
            )

    def UpdateProfile(self, request, context):
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.id == request.user_id))
            if not user:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Profile not found")
                return user_pb2.ProfileResponse()

            if request.full_name:
                user.full_name = request.full_name
            if request.phone:
                user.phone = request.phone
            if request.avatar_path:
                user.avatar_path = request.avatar_path
            session.commit()

            return user_pb2.ProfileResponse(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone or "",
                avatar_path=user.avatar_path or "",
            )


def serve() -> None:
    _ensure_default_data()
    dashboard_thread = Thread(target=_run_dashboard_server, daemon=True)
    dashboard_thread.start()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    user_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(), server)
    user_pb2_grpc.add_ItemServiceServicer_to_server(ItemService(), server)
    user_pb2_grpc.add_MatchServiceServicer_to_server(MatchService(), server)
    user_pb2_grpc.add_ProfileServiceServicer_to_server(ProfileService(), server)
    server.add_insecure_port(f"[::]:{settings.grpc_port}")
    print(f"[{_now_iso()}] gRPC backend listening on :{settings.grpc_port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()