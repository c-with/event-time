#!/usr/bin/env python3
"""Event Time / 活动执行工作台 V0.4.1.

PostgreSQL is the production source of truth. SQLite is supported only for local tests.
All structured business writes go to normalized entity tables; there is no state-document write path.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import json
import mimetypes
import os
import secrets
import shutil
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, request, send_file, session, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, or_, select, text, func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException

from models import (
    Base, AppUser, Client, Contact, Supplier, Venue, VenueSpace, VenueEquipment,
    Project, EventSession, TimeNode, WorkPackage, RequirementItem, Task,
    TaskDependency, Document, DocumentLink, ChangeRequest, FieldRevision,
    AuditLog, ShareLink, SchemaMeta, new_id, utcnow, work_package_sessions,
    task_requirements,
)

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
except Exception:  # pragma: no cover - dependency errors are reported during init
    Image = ImageOps = None
    UnidentifiedImageError = Exception

try:
    from pypdf import PdfReader, PdfWriter
except Exception:  # pragma: no cover
    PdfReader = PdfWriter = None

TZ = ZoneInfo(os.environ.get("APP_TIMEZONE", "Asia/Shanghai"))
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ACTIVITY_DATA_DIR", str(ROOT / "data"))).resolve()
FILES_DIR = DATA_DIR / "files"
THUMB_DIR = DATA_DIR / "thumbnails"
TMP_DIR = DATA_DIR / "tmp"
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_BATCH_BYTES = 250 * 1024 * 1024
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".pdf"}
CRITICAL_FIELDS = {
    "projects": {"name", "client_id", "phase"},
    "sessions": {"starts_at", "ends_at", "date_mode", "venue_space_id", "location_text", "status"},
    "time_nodes": {"planned_start", "planned_end", "confirmed_start", "confirmed_end", "actual_start", "actual_end", "date_status"},
    "work_packages": {"supplier_id", "status", "acceptance_criteria"},
    "requirements": {"specification", "dimensions", "quantity_text", "quantity_unit", "status"},
    "tasks": {"due_at", "owner", "status"},
}
ENTITY_MODELS = {
    "projects": Project,
    "sessions": EventSession,
    "time_nodes": TimeNode,
    "work_packages": WorkPackage,
    "requirements": RequirementItem,
    "tasks": Task,
    "clients": Client,
    "suppliers": Supplier,
    "contacts": Contact,
    "venues": Venue,
    "venue_spaces": VenueSpace,
    "equipment": VenueEquipment,
}
FIELD_ALLOWLIST = {
    "projects": {"name", "client_id", "client_snapshot", "owner", "phase", "description", "cover_document_id"},
    "sessions": {"title", "starts_at", "ends_at", "date_mode", "window_start", "window_end", "venue_space_id", "location_text", "status", "cover_document_id", "notes"},
    "time_nodes": {"session_id", "work_package_id", "node_type", "label", "planned_start", "planned_end", "confirmed_start", "confirmed_end", "actual_start", "actual_end", "date_status", "move_rule", "responsible", "source_text", "status", "notes"},
    "work_packages": {"supplier_id", "name", "status", "description", "contact_snapshot", "responsibility", "acceptance_criteria", "planned_entry_at", "planned_strike_at"},
    "requirements": {"work_package_id", "name", "source_text", "specification", "dimensions", "dimension_unit", "quantity_text", "quantity_unit", "intended_use", "location_text", "acceptance_criteria", "delivered_quantity_text", "owner", "status"},
    "tasks": {"work_package_id", "name", "source_text", "status", "owner", "responsible_party", "planned_start", "due_at", "actual_completed_at", "duration_days", "notes", "evidence_document_id", "needs_review"},
    "clients": {"name", "aliases", "notes"},
    "suppliers": {"name", "service_category", "notes"},
    "contacts": {"name", "supplier_id", "client_id", "role", "phone", "email", "notes", "source_text"},
    "venues": {"name", "address", "notes", "verified_status", "verified_by"},
    "venue_spaces": {"venue_id", "parent_space_id", "name", "space_type", "floor_label", "details", "verified_status", "verified_by"},
    "equipment": {"space_id", "name", "category", "ownership", "physical_dimensions", "resolution", "pixel_pitch", "loading_notes", "power_audio_notes", "source_text", "verified_status", "verified_by"},
}
DATETIME_FIELDS = {
    "starts_at", "ends_at", "window_start", "window_end", "planned_start", "planned_end",
    "confirmed_start", "confirmed_end", "actual_start", "actual_end", "planned_entry_at",
    "planned_strike_at", "due_at", "actual_completed_at", "verified_at", "expires_at",
}
BOOL_FIELDS = {"needs_review", "is_official", "allow_download", "active"}
INT_FIELDS = {"duration_days", "version_no", "original_size", "stored_size", "revision"}
FK_FIELDS = {"client_id", "supplier_id", "venue_space_id", "space_id", "parent_space_id", "work_package_id", "session_id", "cover_document_id", "evidence_document_id"}


def database_url_from_env() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "activity_workbench")
    user = quote_plus(os.environ.get("DB_USER", "activity_workbench_app"))
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


db = SQLAlchemy(model_class=Base, session_options={"expire_on_commit": False})


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        SECRET_KEY=os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=database_url_from_env(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        MAX_CONTENT_LENGTH=MAX_BATCH_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"check_same_thread": False}}
    db.init_app(app)

    @app.before_request
    def enforce_same_origin_and_csrf():
        if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.path == "/api/login":
                return None
            origin = request.headers.get("Origin")
            if origin:
                expected = request.host_url.rstrip("/")
                if origin.rstrip("/") != expected:
                    return jsonify(error="跨站请求被拒绝"), 403
            expected_csrf = session.get("csrf_token")
            got_csrf = request.headers.get("X-CSRF-Token", "")
            if not expected_csrf or not hmac.compare_digest(expected_csrf, got_csrf):
                return jsonify(error="CSRF 校验失败，请刷新页面后重试"), 403
        return None

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="上传文件总量超过 250MB 限制"), 413

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="资源不存在"), 404
        return "Not Found", 404

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        return jsonify(error="数据约束冲突；请刷新数据后重试", detail=str(error.orig)[:240]), 409

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description or "请求失败"), error.code
        return error

    @app.errorhandler(Exception)
    def unhandled(error):
        if app.testing:
            raise error
        app.logger.exception("Unhandled request error")
        return jsonify(error="服务器处理失败，请稍后重试"), 500

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return jsonify(error="请先登录"), 401
            user = db.session.get(AppUser, user_id)
            if not user or not user.active:
                session.clear()
                return jsonify(error="登录状态已失效，请重新登录"), 401
            return fn(*args, **kwargs)
        return wrapped

    def operator_name(required: bool = True) -> str:
        raw_name = (request.headers.get("X-Operator-Name") or request.headers.get("X-Operator") or "").strip()
        # 前端對中文姓名做 encodeURIComponent；兼容未編碼的舊值
        try:
            from urllib.parse import unquote
            if "%" in raw_name:
                raw_name = unquote(raw_name)
        except Exception:
            pass
        name = raw_name
        if not name and not required:
            return "系统"
        if not name:
            abort(make_response(jsonify(error="请先选择本机操作人姓名"), 400))
        return name[:160]

    def as_iso(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=TZ)
            return value.isoformat(timespec="minutes")
        if isinstance(value, date):
            return value.isoformat()
        return value

    def parse_dt(value):
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            result = value
        else:
            raw = str(value).strip().replace("Z", "+00:00")
            try:
                result = datetime.fromisoformat(raw)
            except ValueError:
                try:
                    result = datetime.combine(date.fromisoformat(raw[:10]), time.min)
                except ValueError:
                    raise ValueError(f"无法识别日期时间：{value}")
        if result.tzinfo is None:
            result = result.replace(tzinfo=TZ)
        return result

    def normalize_value(value):
        if isinstance(value, datetime):
            return as_iso(value)
        if isinstance(value, date):
            return value.isoformat()
        return value

    def entity_value(entity, field):
        return normalize_value(getattr(entity, field, None))

    def parse_field(field, value):
        if field in DATETIME_FIELDS:
            return parse_dt(value)
        if field in INT_FIELDS and value not in (None, ""):
            return int(value)
        if field in BOOL_FIELDS:
            if isinstance(value, str):
                return value.lower() in {"1", "true", "yes", "on"}
            return bool(value)
        if field in FK_FIELDS and value in ("", None):
            return None if field not in {"cover_document_id", "evidence_document_id"} else ""
        return value

    def serialize_project(project: Project, compact=False):
        sessions = sorted(project.sessions, key=lambda s: (s.starts_at is None, aware(s.starts_at) or datetime.max.replace(tzinfo=TZ)))
        tasks = list(project.tasks)
        now = datetime.now(TZ)
        overdue = [t for t in tasks if t.due_at and aware(t.due_at) < now and t.status not in {"已完成", "取消", "已取消"}]
        next_session = next((s for s in sessions if s.starts_at and aware(s.ends_at or s.starts_at) >= now and s.status not in {"已取消", "取消"}), None)
        pending_count = db.session.scalar(select(func.count(ChangeRequest.id)).where(
            ChangeRequest.entity_type == "projects", ChangeRequest.entity_id == project.id, ChangeRequest.status == "pending")) or 0
        pending_count += db.session.scalar(select(func.count(ChangeRequest.id)).where(
            ChangeRequest.entity_type.in_(["sessions", "time_nodes", "work_packages", "requirements", "tasks"]),
            ChangeRequest.entity_id.in_([s.id for s in sessions] + [x.id for x in project.time_nodes] + [x.id for x in project.work_packages] + [x.id for x in project.requirements] + [x.id for x in tasks]),
            ChangeRequest.status == "pending")) or 0
        risks = []
        if overdue:
            risks.append({"code": "overdue", "label": f"{len(overdue)} 项逾期", "count": len(overdue)})
        if pending_count:
            risks.append({"code": "pending_change", "label": f"{pending_count} 项变更待确认", "count": pending_count})
        missing = sum(1 for x in tasks if x.status not in {"已完成", "取消", "已取消"} and (not x.owner or not x.due_at))
        if missing:
            risks.append({"code": "missing_info", "label": f"{missing} 项任务待补信息", "count": missing})
        if compact:
            return {
                "id": project.id, "name": project.name, "client_id": project.client_id,
                "client": project.client.name if project.client else project.client_snapshot,
                "owner": project.owner, "phase": project.phase, "description": project.description,
                "cover_document_id": project.cover_document_id,
                "cover_url": document_url(project.cover_document_id), "revision": project.revision,
                "created_at": as_iso(project.created_at), "updated_at": as_iso(project.updated_at),
                "session_count": len(sessions), "next_session": serialize_session(next_session, include_project=False) if next_session else None,
                "next_action": next_action(project), "risk_count": len(risks), "risks": risks,
                "archived_at": as_iso(project.archived_at),
            }
        return {
            **serialize_project(project, compact=True),
            "sessions": [serialize_session(s, include_project=False) for s in sessions],
            "time_nodes": [serialize_time_node(x) for x in project.time_nodes],
            "work_packages": [serialize_package(x) for x in project.work_packages],
            "requirements": [serialize_requirement(x) for x in project.requirements],
            "tasks": [serialize_task(x) for x in project.tasks],
            "documents": list_documents_for_project(project.id),
            "change_requests": [serialize_change(c) for c in db.session.scalars(select(ChangeRequest).where(
                ChangeRequest.status.in_(["pending", "conflict"])).order_by(ChangeRequest.created_at.desc())).all()
                if change_belongs_to_project(c, project)],
            "audit": [serialize_audit(a) for a in db.session.scalars(select(AuditLog).where(
                or_(and_(AuditLog.entity_type == "projects", AuditLog.entity_id == project.id),
                    and_(AuditLog.entity_type == "sessions", AuditLog.entity_id.in_([s.id for s in sessions] or [""])),
                    and_(AuditLog.entity_type == "work_packages", AuditLog.entity_id.in_([x.id for x in project.work_packages] or [""])),
                    and_(AuditLog.entity_type == "requirements", AuditLog.entity_id.in_([x.id for x in project.requirements] or [""])),
                    and_(AuditLog.entity_type == "tasks", AuditLog.entity_id.in_([x.id for x in project.tasks] or [""]))))
                .order_by(AuditLog.created_at.desc()).limit(100)).all()],
        }

    def aware(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)

    def next_action(project):
        now = datetime.now(TZ)
        open_tasks = [t for t in project.tasks if t.status not in {"已完成", "取消", "已取消"}]
        overdue = sorted([t for t in open_tasks if t.due_at and aware(t.due_at) < now], key=lambda t: aware(t.due_at))
        if overdue:
            return {"type": "task", "id": overdue[0].id, "label": overdue[0].name, "due_at": as_iso(overdue[0].due_at), "reason": "逾期"}
        upcoming = sorted([t for t in open_tasks if t.due_at], key=lambda t: aware(t.due_at))
        if upcoming:
            return {"type": "task", "id": upcoming[0].id, "label": upcoming[0].name, "due_at": as_iso(upcoming[0].due_at), "reason": "最近期限"}
        pending = db.session.scalar(select(ChangeRequest).where(ChangeRequest.entity_type == "projects", ChangeRequest.entity_id == project.id, ChangeRequest.status == "pending").order_by(ChangeRequest.created_at).limit(1))
        if pending:
            return {"type": "change", "id": pending.id, "label": "确认项目变更", "due_at": None, "reason": "待确认"}
        return {"type": "project", "id": project.id, "label": "补充项目执行信息", "due_at": None, "reason": "待推进"}

    def serialize_session(s: EventSession | None, include_project=True):
        if not s:
            return None
        data = {
            "id": s.id, "project_id": s.project_id, "title": s.title,
            "starts_at": as_iso(s.starts_at), "ends_at": as_iso(s.ends_at), "date_mode": s.date_mode,
            "window_start": as_iso(s.window_start), "window_end": as_iso(s.window_end),
            "venue_space_id": s.venue_space_id, "location_text": s.location_text, "status": s.status,
            "cover_document_id": s.cover_document_id, "cover_url": document_url(s.cover_document_id),
            "notes": s.notes, "revision": s.revision,
            "time_nodes": [serialize_time_node(n) for n in s.time_nodes],
        }
        if include_project:
            data["project"] = {"id": s.project.id, "name": s.project.name, "cover_document_id": s.project.cover_document_id,
                               "cover_url": document_url(s.project.cover_document_id), "phase": s.project.phase}
        if s.venue_space:
            data["venue"] = venue_space_label(s.venue_space)
        return data

    def serialize_time_node(n: TimeNode):
        return {"id": n.id, "project_id": n.project_id, "session_id": n.session_id, "work_package_id": n.work_package_id,
                "node_type": n.node_type, "label": n.label, "planned_start": as_iso(n.planned_start), "planned_end": as_iso(n.planned_end),
                "confirmed_start": as_iso(n.confirmed_start), "confirmed_end": as_iso(n.confirmed_end),
                "actual_start": as_iso(n.actual_start), "actual_end": as_iso(n.actual_end), "date_status": n.date_status,
                "move_rule": n.move_rule, "responsible": n.responsible, "source_text": n.source_text, "status": n.status,
                "notes": n.notes, "revision": n.revision}

    def serialize_package(p: WorkPackage):
        return {"id": p.id, "project_id": p.project_id, "supplier_id": p.supplier_id,
                "supplier": p.supplier.name if p.supplier else "", "name": p.name, "status": p.status,
                "description": p.description, "contact_snapshot": p.contact_snapshot, "responsibility": p.responsibility,
                "acceptance_criteria": p.acceptance_criteria, "planned_entry_at": as_iso(p.planned_entry_at),
                "planned_strike_at": as_iso(p.planned_strike_at), "session_ids": [s.id for s in p.sessions],
                "revision": p.revision, "updated_at": as_iso(p.updated_at)}

    def serialize_requirement(r: RequirementItem):
        return {"id": r.id, "project_id": r.project_id, "work_package_id": r.work_package_id,
                "work_package": r.work_package.name if r.work_package else "", "name": r.name, "source_text": r.source_text,
                "specification": r.specification, "dimensions": r.dimensions, "dimension_unit": r.dimension_unit,
                "quantity_text": r.quantity_text, "quantity_unit": r.quantity_unit, "intended_use": r.intended_use,
                "location_text": r.location_text, "acceptance_criteria": r.acceptance_criteria,
                "delivered_quantity_text": r.delivered_quantity_text, "owner": r.owner, "status": r.status,
                "task_ids": [t.id for t in r.tasks], "revision": r.revision, "updated_at": as_iso(r.updated_at)}

    def serialize_task(t: Task):
        return {"id": t.id, "project_id": t.project_id, "work_package_id": t.work_package_id,
                "work_package": t.work_package.name if t.work_package else "", "name": t.name, "source_text": t.source_text,
                "status": t.status, "owner": t.owner, "responsible_party": t.responsible_party,
                "planned_start": as_iso(t.planned_start), "due_at": as_iso(t.due_at),
                "actual_completed_at": as_iso(t.actual_completed_at), "duration_days": t.duration_days, "notes": t.notes,
                "evidence_document_id": t.evidence_document_id, "needs_review": t.needs_review,
                "requirement_ids": [r.id for r in t.requirements],
                "dependencies": [{"task_id": d.task_id, "depends_on_task_id": d.depends_on_task_id,
                                  "depends_on_name": d.depends_on.name if d.depends_on else "", "description": d.description,
                                  "dependency_type": d.dependency_type} for d in t.dependencies],
                "is_overdue": bool(t.due_at and aware(t.due_at) < datetime.now(TZ) and t.status not in {"已完成", "取消", "已取消"}),
                "revision": t.revision, "updated_at": as_iso(t.updated_at)}

    def serialize_change(c: ChangeRequest):
        return {"id": c.id, "entity_type": c.entity_type, "entity_id": c.entity_id, "field_path": c.field_path,
                "old_value": c.old_value, "new_value": c.new_value, "base_revision": c.base_revision,
                "source_ref": c.source_ref, "source_text": c.source_text, "proposed_by": c.proposed_by,
                "status": c.status, "confirmed_by": c.confirmed_by, "confirmed_at": as_iso(c.confirmed_at),
                "resolution_note": c.resolution_note, "created_at": as_iso(c.created_at),
                "entity_label": entity_label(c.entity_type, c.entity_id)}

    def serialize_audit(a: AuditLog):
        return {"id": a.id, "actor": a.actor, "action": a.action, "entity_type": a.entity_type,
                "entity_id": a.entity_id, "before": a.before_json, "after": a.after_json,
                "source_ref": a.source_ref, "created_at": as_iso(a.created_at)}

    def serialize_document(d: Document, with_links=True):
        result = {"id": d.id, "series_id": d.series_id, "version_no": d.version_no,
                  "previous_document_id": d.previous_document_id, "original_name": d.original_name,
                  "mime_type": d.mime_type, "category": d.category, "sha256": d.sha256,
                  "original_size": d.original_size, "stored_size": d.stored_size, "is_official": d.is_official,
                  "processing_status": d.processing_status, "notes": d.notes, "uploaded_by": d.uploaded_by,
                  "created_at": as_iso(d.created_at), "preview_url": f"/api/documents/{d.id}/content?variant=preview",
                  "download_url": f"/api/documents/{d.id}/content?variant=download",
                  "thumbnail_url": f"/api/documents/{d.id}/content?variant=thumbnail" if d.thumbnail_path else ""}
        if with_links:
            result["links"] = [{"entity_type": x.entity_type, "entity_id": x.entity_id, "link_role": x.link_role} for x in d.links]
        return result

    def serialize_resource(kind, obj):
        common = {"id": obj.id}
        if kind == "clients":
            return {**common, "name": obj.name, "aliases": obj.aliases, "notes": obj.notes,
                    "contacts": [serialize_resource("contacts", x) for x in obj.contacts], "revision": obj.revision, "updated_at": as_iso(obj.updated_at)}
        if kind == "suppliers":
            return {**common, "name": obj.name, "service_category": obj.service_category, "notes": obj.notes,
                    "verified_at": as_iso(obj.verified_at), "contacts": [serialize_resource("contacts", x) for x in obj.contacts], "revision": obj.revision, "updated_at": as_iso(obj.updated_at)}
        if kind == "contacts":
            return {**common, "name": obj.name, "supplier_id": obj.supplier_id, "client_id": obj.client_id,
                    "role": obj.role, "phone": obj.phone, "email": obj.email, "notes": obj.notes, "source_text": obj.source_text,
                    "supplier": obj.supplier.name if obj.supplier else "", "client": obj.client.name if obj.client else "", "revision": obj.revision, "updated_at": as_iso(obj.updated_at)}
        if kind == "venues":
            return {**common, "name": obj.name, "address": obj.address, "notes": obj.notes,
                    "verified_status": obj.verified_status, "verified_at": as_iso(obj.verified_at), "verified_by": obj.verified_by, "revision": obj.revision, "updated_at": as_iso(obj.updated_at),
                    "spaces": [serialize_resource("venue_spaces", x) for x in obj.spaces]}
        if kind == "venue_spaces":
            return {**common, "venue_id": obj.venue_id, "venue": obj.venue.name if obj.venue else "",
                    "parent_space_id": obj.parent_space_id, "name": obj.name, "space_type": obj.space_type,
                    "floor_label": obj.floor_label, "details": obj.details, "verified_status": obj.verified_status,
                    "equipment": [serialize_resource("equipment", x) for x in obj.equipment], "revision": obj.revision, "updated_at": as_iso(obj.updated_at)}
        if kind == "equipment":
            return {**common, "space_id": obj.space_id, "space": venue_space_label(obj.space) if obj.space else "",
                    "name": obj.name, "category": obj.category, "ownership": obj.ownership,
                    "physical_dimensions": obj.physical_dimensions, "resolution": obj.resolution,
                    "pixel_pitch": obj.pixel_pitch, "loading_notes": obj.loading_notes,
                    "power_audio_notes": obj.power_audio_notes, "source_text": obj.source_text,
                    "verified_status": obj.verified_status, "verified_by": obj.verified_by, "revision": obj.revision, "updated_at": as_iso(obj.updated_at)}
        return common

    def venue_space_label(space):
        parts = []
        cursor = space
        seen = set()
        while cursor and cursor.id not in seen:
            seen.add(cursor.id)
            parts.append(cursor.name)
            cursor = cursor.parent
        return (space.venue.name + " / " if space.venue else "") + " / ".join(reversed(parts))

    def document_url(document_id):
        if not document_id:
            return ""
        doc = db.session.get(Document, document_id)
        return f"/api/documents/{doc.id}/content?variant=thumbnail" if doc and doc.thumbnail_path else (f"/api/documents/{doc.id}/content?variant=preview" if doc else "")

    def list_documents_for_project(project_id):
        project = db.session.get(Project, project_id)
        if not project:
            return []
        ids = {("projects", project_id)}
        ids.update(("sessions", x.id) for x in project.sessions)
        ids.update(("work_packages", x.id) for x in project.work_packages)
        ids.update(("requirements", x.id) for x in project.requirements)
        ids.update(("tasks", x.id) for x in project.tasks)
        ids.update(("time_nodes", x.id) for x in project.time_nodes)
        if not ids:
            return []
        conditions = [and_(DocumentLink.entity_type == typ, DocumentLink.entity_id == eid) for typ, eid in ids]
        docs = db.session.scalars(select(Document).join(DocumentLink).where(or_(*conditions)).order_by(Document.created_at.desc()).distinct()).all()
        return [serialize_document(d) for d in docs]

    def change_belongs_to_project(change, project):
        if change.entity_type == "projects":
            return change.entity_id == project.id
        if change.entity_type == "sessions":
            return any(x.id == change.entity_id for x in project.sessions)
        if change.entity_type == "time_nodes":
            return any(x.id == change.entity_id for x in project.time_nodes)
        if change.entity_type == "work_packages":
            return any(x.id == change.entity_id for x in project.work_packages)
        if change.entity_type == "requirements":
            return any(x.id == change.entity_id for x in project.requirements)
        if change.entity_type == "tasks":
            return any(x.id == change.entity_id for x in project.tasks)
        return False

    def entity_label(entity_type, entity_id):
        model = ENTITY_MODELS.get(entity_type)
        obj = db.session.get(model, entity_id) if model else None
        if not obj:
            return f"{entity_type}/{entity_id[:8]}"
        return getattr(obj, "name", None) or getattr(obj, "title", None) or getattr(obj, "label", None) or entity_id[:8]

    def write_audit(actor, action, entity_type="", entity_id="", before=None, after=None, source_ref=""):
        db.session.add(AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                                before_json=before, after_json=after, source_ref=source_ref or ""))

    def entity_revision(obj):
        return int(getattr(obj, "revision", 1))

    def get_entity(entity_type, entity_id):
        model = ENTITY_MODELS.get(entity_type)
        if not model:
            abort(400, description="不支持的实体类型")
        obj = db.session.get(model, entity_id)
        if not obj:
            abort(404, description="实体不存在")
        return obj

    def apply_entity_changes(entity_type, entity_id, changes, actor, source_ref="", critical_confirmed=False, expected_revision=None, commit=True):
        obj = get_entity(entity_type, entity_id)
        allowed = FIELD_ALLOWLIST.get(entity_type, set())
        clean = {k: v for k, v in changes.items() if k in allowed}
        unknown = set(changes) - allowed - {"_revision", "source_ref", "source_text", "confirm_critical", "force_create"}
        if unknown:
            return {"error": "包含不允许修改的字段", "fields": sorted(unknown)}, 400
        if entity_type != "projects":
            project_id = getattr(obj, "project_id", None)
            for ref_field, ref_model in (("work_package_id", WorkPackage), ("session_id", EventSession)):
                ref_id = clean.get(ref_field)
                if ref_id:
                    ref_obj = db.session.get(ref_model, ref_id)
                    if not ref_obj or (project_id and getattr(ref_obj, "project_id", None) != project_id):
                        return {"error": f"{ref_field} 必须引用同一项目内的记录"}, 400
        if entity_type == "work_packages" and clean.get("supplier_id") and not db.session.get(Supplier, clean["supplier_id"]):
            return {"error": "所选供应商不存在"}, 400
        if entity_type == "projects" and clean.get("client_id") and not db.session.get(Client, clean["client_id"]):
            return {"error": "所选客户不存在"}, 400
        current_revision = entity_revision(obj)
        expected_revision = expected_revision if expected_revision is not None else changes.get("_revision")
        conflicts = []
        if expected_revision is not None and int(expected_revision) != current_revision:
            for field, incoming in clean.items():
                later = db.session.scalar(select(FieldRevision.id).where(
                    FieldRevision.entity_type == entity_type, FieldRevision.entity_id == entity_id,
                    FieldRevision.field_path == field, FieldRevision.revision > int(expected_revision)).limit(1))
                current = entity_value(obj, field)
                if later and current != normalize_value(incoming):
                    conflicts.append({"field": field, "current": current, "incoming": incoming})
        if conflicts:
            return {"error": "同字段并发冲突，请选择保留值后重试", "conflicts": conflicts, "revision": current_revision}, 409
        source_ref = str(source_ref or changes.get("source_ref") or "")[:2000]
        source_text = str(changes.get("source_text") or "")[:10000]
        before_direct, after_direct, proposed = {}, {}, []
        for field, incoming in clean.items():
            try:
                value = parse_field(field, incoming)
            except (ValueError, TypeError) as exc:
                return {"error": str(exc), "field": field}, 400
            old = getattr(obj, field, None)
            if normalize_value(old) == normalize_value(value):
                continue
            if field in CRITICAL_FIELDS.get(entity_type, set()) and not critical_confirmed:
                change = ChangeRequest(entity_type=entity_type, entity_id=entity_id, field_path=field,
                    old_value=normalize_value(old), new_value=normalize_value(value), base_revision=current_revision,
                    source_ref=source_ref, source_text=source_text, proposed_by=actor, status="pending")
                db.session.add(change)
                db.session.flush()
                proposed.append(serialize_change(change))
                write_audit(actor, "propose_critical_change", entity_type, entity_id,
                            before={field: normalize_value(old)}, after={field: normalize_value(value)}, source_ref=source_ref)
            else:
                before_direct[field] = normalize_value(old)
                setattr(obj, field, value)
                after_direct[field] = normalize_value(value)
        if before_direct:
            if hasattr(obj, "revision"):
                obj.revision = current_revision + 1
                current_revision = obj.revision
            if hasattr(obj, "updated_at"):
                obj.updated_at = utcnow()
            for field, value in after_direct.items():
                db.session.add(FieldRevision(entity_type=entity_type, entity_id=entity_id, field_path=field,
                    revision=current_revision, value_json=value, actor=actor))
            write_audit(actor, "update", entity_type, entity_id, before=before_direct, after=after_direct, source_ref=source_ref)
        db.session.flush()
        result = {"entity": serialize_entity(entity_type, get_entity(entity_type, entity_id)),
                  "proposed_changes": proposed, "revision": current_revision}
        if commit:
            db.session.commit()
        return result, 200

    def serialize_entity(entity_type, obj):
        if entity_type == "projects": return serialize_project(obj, compact=True)
        if entity_type == "sessions": return serialize_session(obj)
        if entity_type == "time_nodes": return serialize_time_node(obj)
        if entity_type == "work_packages": return serialize_package(obj)
        if entity_type == "requirements": return serialize_requirement(obj)
        if entity_type == "tasks": return serialize_task(obj)
        if entity_type in {"clients", "suppliers", "contacts", "venues", "venue_spaces", "equipment"}:
            return serialize_resource(entity_type, obj)
        return {"id": getattr(obj, "id", "")}

    def make_child(entity_type, project_id, payload, actor):
        project = db.session.get(Project, project_id)
        if not project:
            return {"error": "项目不存在"}, 404
        model = ENTITY_MODELS[entity_type]
        allowed = FIELD_ALLOWLIST[entity_type]
        fields = {k: v for k, v in payload.items() if k in allowed}
        fields = {k: parse_field(k, v) for k, v in fields.items()}
        for ref_field, ref_model in (("work_package_id", WorkPackage), ("session_id", EventSession)):
            ref_id = fields.get(ref_field)
            if ref_id:
                ref_obj = db.session.get(ref_model, ref_id)
                if not ref_obj or getattr(ref_obj, "project_id", None) != project_id:
                    return {"error": f"{ref_field} 必须引用当前项目内的记录"}, 400
        if entity_type == "work_packages" and fields.get("supplier_id") and not db.session.get(Supplier, fields["supplier_id"]):
            return {"error": "所选供应商不存在"}, 400
        if entity_type == "requirements" and fields.get("work_package_id"):
            package = db.session.get(WorkPackage, fields["work_package_id"])
            if not package or package.project_id != project_id:
                return {"error": "需求项工作包必须属于当前项目"}, 400
        if entity_type == "tasks" and fields.get("work_package_id"):
            package = db.session.get(WorkPackage, fields["work_package_id"])
            if not package or package.project_id != project_id:
                return {"error": "任务工作包必须属于当前项目"}, 400
        if entity_type == "sessions" and fields.get("venue_space_id") and not db.session.get(VenueSpace, fields["venue_space_id"]):
            return {"error": "所选场地空间不存在"}, 400
        if entity_type == "sessions":
            fields.setdefault("date_mode", "fixed" if fields.get("starts_at") else "undated")
            fields.setdefault("status", "已确认" if fields.get("starts_at") else "待排期")
            fields.setdefault("title", project.name)
        if entity_type == "time_nodes":
            fields.setdefault("node_type", "截止")
            fields.setdefault("label", fields.get("node_type", "截止"))
        if entity_type == "work_packages":
            fields.setdefault("status", "待指派")
        if entity_type == "requirements":
            fields.setdefault("status", "待澄清")
        if entity_type == "tasks":
            fields.setdefault("status", "待办")
        required_field = {"sessions": "title", "time_nodes": "label", "work_packages": "name", "requirements": "name", "tasks": "name"}.get(entity_type)
        if required_field and not str(fields.get(required_field, "")).strip():
            return {"error": f"{required_field} 不能为空"}, 400
        fields["project_id"] = project_id
        obj = model(**fields)
        db.session.add(obj)
        db.session.flush()
        if entity_type == "work_packages" and payload.get("session_ids"):
            for sid in payload["session_ids"]:
                s = db.session.get(EventSession, sid)
                if not s or s.project_id != project_id:
                    db.session.rollback()
                    return {"error": "工作包关联的场次不属于当前项目"}, 400
                obj.sessions.append(s)
        if entity_type == "tasks":
            for rid in payload.get("requirement_ids", []):
                r = db.session.get(RequirementItem, rid)
                if not r or r.project_id != project_id:
                    db.session.rollback()
                    return {"error": "关联需求项不属于当前项目"}, 400
                obj.requirements.append(r)
            for dependency_id in payload.get("dependency_ids", []):
                dep = db.session.get(Task, dependency_id)
                if not dep or dep.project_id != project_id or dep.id == obj.id:
                    db.session.rollback()
                    return {"error": "依赖任务无效"}, 400
                obj.dependencies.append(TaskDependency(depends_on=dep, description="", dependency_type="blocks"))
        write_audit(actor, "create", entity_type, obj.id, before=None, after=serialize_entity(entity_type, obj), source_ref=payload.get("source_ref", ""))
        db.session.commit()
        return serialize_entity(entity_type, obj), 201

    @app.get("/")
    def index():
        return send_file(ROOT / "static" / "index.html")

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            database = "postgresql" if "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"] else "sqlite-test"
            return jsonify(ok=True, database=database, version="0.4.1")
        except Exception as exc:
            db.session.rollback()
            return jsonify(ok=False, error=str(exc)[:200]), 503

    @app.post("/api/login")
    def login():
        payload = request.get_json(silent=True) or {}
        username, password = str(payload.get("username", "")), str(payload.get("password", ""))
        user = db.session.scalar(select(AppUser).where(AppUser.username == username, AppUser.active.is_(True)))
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify(error="账号或密码不正确"), 401
        session.clear()
        session["user_id"] = user.id
        session["csrf_token"] = secrets.token_urlsafe(32)
        response = jsonify(ok=True, username=user.username, display_name=user.display_name, csrf_token=session["csrf_token"])
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        user_id = session.get("user_id")
        user = db.session.get(AppUser, user_id) if user_id else None
        if not user or not user.active:
            return jsonify(authenticated=False)
        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(authenticated=True, username=user.username, display_name=user.display_name, csrf_token=session["csrf_token"])

    @app.get("/api/dashboard")
    @login_required
    def dashboard():
        today = datetime.now(TZ).date()
        projects = db.session.scalars(select(Project).where(Project.phase != "已归档").order_by(Project.updated_at.desc())).all()
        summaries = [serialize_project(p, compact=True) for p in projects]
        summaries.sort(key=lambda p: project_priority(p, today))
        open_tasks = db.session.scalars(select(Task).where(Task.status.notin_(["已完成", "取消", "已取消"]))).all()
        overdue_tasks = [serialize_task(t) for t in open_tasks if t.due_at and aware(t.due_at).date() < today]
        pending = db.session.scalars(select(ChangeRequest).where(ChangeRequest.status.in_(["pending", "conflict"])).order_by(ChangeRequest.created_at.desc()).limit(30)).all()
        nodes = db.session.scalars(select(TimeNode).where(TimeNode.planned_start.is_not(None)).order_by(TimeNode.planned_start).limit(300)).all()
        upcoming_nodes = [serialize_time_node(n) | {"project_name": n.project.name, "session_title": n.session.title if n.session else ""}
                          for n in nodes if aware(n.planned_start).date() <= today + timedelta(days=7) and aware(n.planned_start).date() >= today - timedelta(days=1)]
        return jsonify(today=today.isoformat(), counts={"projects": len(projects), "today_nodes": sum(1 for n in upcoming_nodes if str(n.get("planned_start", ""))[:10] == today.isoformat()),
            "overdue_tasks": len(overdue_tasks), "pending_changes": len(pending)}, projects=summaries[:12], overdue_tasks=overdue_tasks[:20],
            pending_changes=[serialize_change(c) for c in pending], upcoming_nodes=upcoming_nodes)

    @app.get("/api/projects")
    @login_required
    def list_projects():
        search = (request.args.get("q") or "").strip().lower()
        phase = request.args.get("phase")
        include_archived = request.args.get("archived") == "1"
        query = select(Project)
        if not include_archived:
            query = query.where(Project.phase != "已归档")
        if phase:
            query = query.where(Project.phase == phase)
        projects = db.session.scalars(query.order_by(Project.updated_at.desc())).all()
        rows = [serialize_project(p, compact=True) for p in projects]
        if search:
            rows = [r for r in rows if search in (r["name"] or "").lower() or search in (r["client"] or "").lower() or search in (r["owner"] or "").lower()]
        sort = request.args.get("sort", "priority")
        today = datetime.now(TZ).date()
        if sort == "name": rows.sort(key=lambda r: r["name"].lower())
        elif sort == "client": rows.sort(key=lambda r: (r["client"] or "").lower())
        elif sort == "owner": rows.sort(key=lambda r: (r["owner"] or "").lower())
        elif sort == "phase": rows.sort(key=lambda r: r["phase"])
        elif sort == "updated": rows.sort(key=lambda r: r["updated_at"] or "", reverse=True)
        elif sort == "date": rows.sort(key=lambda r: (r["next_session"] or {}).get("starts_at") or "9999")
        else: rows.sort(key=lambda r: project_priority(r, today))
        return jsonify(projects=rows, total=len(rows), sort=sort)

    def project_priority(row, today):
        next_session = row.get("next_session") or {}
        when = (next_session.get("starts_at") or "")[:10]
        days = 999
        try: days = (date.fromisoformat(when) - today).days
        except ValueError: pass
        if row.get("risk_count", 0): group = 0
        elif days == 0: group = 1
        elif days == 1: group = 2
        elif 0 <= days <= 7: group = 3
        elif row.get("phase") == "收尾": group = 4
        elif row.get("phase") in {"已完成", "已取消", "已归档"}: group = 8
        elif days == 999: group = 6
        else: group = 5
        return (group, days if days >= 0 else -1, row.get("updated_at") or "")

    @app.post("/api/projects")
    @login_required
    def create_project():
        actor = operator_name()
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        if not name:
            return jsonify(error="项目名称不能为空"), 400
        normalized = name.casefold()
        candidates = db.session.scalars(select(Project).where(Project.name.ilike(name))).all()
        if not payload.get("force_create") and candidates:
            return jsonify(error="发现名称相同的项目，请确认是否继续新建", duplicate_candidates=[serialize_project(p, compact=True) for p in candidates[:8]]), 409
        fields = {k: payload[k] for k in ("name", "client_id", "client_snapshot", "owner", "phase", "description", "cover_document_id") if k in payload}
        if fields.get("client_id") == "":
            # 前端「暂不指定客户」送空字符串；外键要求 NULL 而非空串
            fields["client_id"] = None
        if fields.get("client_id") and not db.session.get(Client, fields["client_id"]):
            return jsonify(error="所选客户不存在"), 400
        if not fields.get("client_snapshot") and fields.get("client_id"):
            client = db.session.get(Client, fields["client_id"])
            fields["client_snapshot"] = client.name if client else ""
        project = Project(**fields)
        db.session.add(project)
        db.session.flush()
        write_audit(actor, "create", "projects", project.id, after={"name": project.name, "phase": project.phase}, source_ref=payload.get("source_ref", ""))
        db.session.commit()
        return jsonify(project=serialize_project(project, compact=True)), 201

    @app.get("/api/projects/<project_id>")
    @login_required
    def get_project(project_id):
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify(error="项目不存在"), 404
        return jsonify(project=serialize_project(project))

    @app.patch("/api/projects/<project_id>")
    @login_required
    def patch_project(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = apply_entity_changes("projects", project_id, payload, operator_name(), payload.get("source_ref", ""),
                                              critical_confirmed=bool(payload.get("confirm_critical")), expected_revision=payload.get("_revision"))
        return jsonify(result), status

    @app.post("/api/projects/<project_id>/archive")
    @login_required
    def archive_project(project_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True:
            return jsonify(error="归档需要显式确认"), 400
        actor = operator_name()
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify(error="项目不存在"), 404
        before = {"phase": project.phase, "archived_at": as_iso(project.archived_at)}
        project.phase, project.archived_at = "已归档", utcnow()
        project.revision += 1
        project.updated_at = utcnow()
        db.session.add(FieldRevision(entity_type="projects", entity_id=project.id, field_path="phase", revision=project.revision, value_json=project.phase, actor=actor))
        write_audit(actor, "archive", "projects", project.id, before=before, after={"phase": project.phase, "archived_at": as_iso(project.archived_at)})
        db.session.commit()
        return jsonify(project=serialize_project(project, compact=True))

    @app.post("/api/projects/<project_id>/sessions")
    @login_required
    def create_session(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = make_child("sessions", project_id, payload, operator_name())
        return jsonify(session=result) if status == 201 else (jsonify(result), status)

    @app.post("/api/projects/<project_id>/time-nodes")
    @login_required
    def create_time_node(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = make_child("time_nodes", project_id, payload, operator_name())
        return jsonify(time_node=result) if status == 201 else (jsonify(result), status)

    @app.post("/api/projects/<project_id>/work-packages")
    @login_required
    def create_work_package(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = make_child("work_packages", project_id, payload, operator_name())
        return jsonify(work_package=result) if status == 201 else (jsonify(result), status)

    @app.post("/api/projects/<project_id>/requirements")
    @login_required
    def create_requirement(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = make_child("requirements", project_id, payload, operator_name())
        return jsonify(requirement=result) if status == 201 else (jsonify(result), status)

    @app.post("/api/projects/<project_id>/tasks")
    @login_required
    def create_task(project_id):
        payload = request.get_json(silent=True) or {}
        result, status = make_child("tasks", project_id, payload, operator_name())
        return jsonify(task=result) if status == 201 else (jsonify(result), status)

    @app.patch("/api/sessions/<entity_id>")
    @login_required
    def patch_session(entity_id):
        payload = request.get_json(silent=True) or {}
        result, status = apply_entity_changes("sessions", entity_id, payload, operator_name(), payload.get("source_ref", ""),
                                              critical_confirmed=bool(payload.get("confirm_critical")), expected_revision=payload.get("_revision"))
        return jsonify(result), status

    @app.post("/api/sessions/<entity_id>/reschedule-preview")
    @login_required
    def session_reschedule_preview(entity_id):
        payload = request.get_json(silent=True) or {}
        s = db.session.get(EventSession, entity_id)
        if not s: return jsonify(error="场次不存在"), 404
        try:
            new_start, new_end = parse_dt(payload.get("starts_at")), parse_dt(payload.get("ends_at"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if new_start and new_end and new_end < new_start:
            return jsonify(error="结束时间不能早于开始时间"), 400
        following, fixed = [], []
        for node in s.time_nodes:
            target = following if node.move_rule == "follow_session" else fixed
            target.append({"id": node.id, "label": node.label, "type": node.node_type,
                           "planned_start": as_iso(node.planned_start), "planned_end": as_iso(node.planned_end), "status": node.date_status})
        tasks = [t for t in s.project.tasks if t.work_package_id and any(p.id == t.work_package_id for p in s.work_packages)]
        supplier_promises = [{"work_package": p.name, "supplier": p.supplier.name if p.supplier else p.contact_snapshot,
                              "entry": as_iso(p.planned_entry_at), "strike": as_iso(p.planned_strike_at)} for p in s.work_packages
                             if p.planned_entry_at or p.planned_strike_at]
        return jsonify(preview={"session_id": s.id, "project_id": s.project_id, "project_name": s.project.name,
            "old": {"starts_at": as_iso(s.starts_at), "ends_at": as_iso(s.ends_at)},
            "new": {"starts_at": as_iso(new_start), "ends_at": as_iso(new_end)},
            "following_nodes": following, "fixed_nodes_to_review": fixed,
            "tasks_to_review": [{"id": t.id, "name": t.name, "due_at": as_iso(t.due_at)} for t in tasks],
            "supplier_commitments": supplier_promises, "requires_confirmation": True})

    @app.post("/api/sessions/<entity_id>/reschedule")
    @login_required
    def session_reschedule(entity_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True:
            return jsonify(error="改期必须先预览并显式确认"), 400
        actor = operator_name()
        s = db.session.get(EventSession, entity_id)
        if not s: return jsonify(error="场次不存在"), 404
        try:
            new_start, new_end = parse_dt(payload.get("starts_at")), parse_dt(payload.get("ends_at"))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if new_start and new_end and new_end < new_start:
            return jsonify(error="结束时间不能早于开始时间"), 400
        expected = payload.get("_revision")
        if expected is not None and int(expected) != s.revision:
            return jsonify(error="场次已被其他设备修改，请刷新后重新预览", revision=s.revision), 409
        before = {"starts_at": as_iso(s.starts_at), "ends_at": as_iso(s.ends_at)}
        s.starts_at, s.ends_at = new_start, new_end
        s.date_mode = "fixed" if new_start else "undated"
        s.status = "暂定" if payload.get("tentative") else "已确认"
        s.revision += 1
        s.updated_at = utcnow()
        for field, value in {"starts_at": as_iso(new_start), "ends_at": as_iso(new_end), "date_mode": s.date_mode, "status": s.status}.items():
            db.session.add(FieldRevision(entity_type="sessions", entity_id=s.id, field_path=field, revision=s.revision, value_json=value, actor=actor))
        for node in s.time_nodes:
            if node.move_rule != "follow_session" or not node.planned_start or not before.get("starts_at") or not payload.get("starts_at"):
                continue
            old_start = aware(node.planned_start)
            old_session_start = aware(parse_dt(before["starts_at"]))
            new_session_start = aware(new_start)
            delta = new_session_start - old_session_start
            node.planned_start = old_start + delta
            if node.planned_end:
                node.planned_end = aware(node.planned_end) + delta
            node.revision += 1
            node.updated_at = utcnow()
            db.session.add(FieldRevision(entity_type="time_nodes", entity_id=node.id, field_path="planned_start", revision=node.revision, value_json=as_iso(node.planned_start), actor=actor))
            db.session.add(FieldRevision(entity_type="time_nodes", entity_id=node.id, field_path="planned_end", revision=node.revision, value_json=as_iso(node.planned_end), actor=actor))
            node.status = "待复核" if node.status not in {"已完成", "取消", "已取消"} else node.status
        session_package_ids = {p.id for p in s.work_packages}
        for task in s.project.tasks:
            if task.work_package_id in session_package_ids and task.status not in {"已完成", "取消", "已取消"}:
                task.needs_review = True
        write_audit(actor, "reschedule_confirmed", "sessions", s.id, before=before,
                    after={"starts_at": as_iso(s.starts_at), "ends_at": as_iso(s.ends_at)}, source_ref=payload.get("source_ref", "calendar-drag"))
        db.session.commit()
        return jsonify(session=serialize_session(s), warning="关联任务已标记需要复核；固定交期与供应商承诺未自动覆盖")

    @app.patch("/api/time-nodes/<entity_id>")
    @login_required
    def patch_time_node(entity_id):
        payload = request.get_json(silent=True) or {}
        result, status = apply_entity_changes("time_nodes", entity_id, payload, operator_name(), payload.get("source_ref", ""),
                                              critical_confirmed=bool(payload.get("confirm_critical")), expected_revision=payload.get("_revision"))
        return jsonify(result), status

    def patch_with_links(entity_type, entity_id, payload, actor, link_field, related_model):
        """Validate all relationships before any write; commit fields, links and audit together."""
        obj = get_entity(entity_type, entity_id)
        # The task editor also submits requirement_ids. Validate both relationship collections.
        relation_fields = {"tasks": {"dependency_ids", "requirement_ids"},
                           "work_packages": {"session_ids"},
                           "requirements": {"task_ids"}}[entity_type]
        scalars = {k: v for k, v in payload.items() if k not in relation_fields}
        links = {}
        if any(name in payload for name in relation_fields):
            # Relationships do not support field-granular rebasing yet.
            # Prevent a stale browser form from overwriting concurrent link edits.
            expected = payload.get("_revision")
            if expected is None:
                return {"error": "修改关联关系时必须提供 _revision"}, 400
            try:
                expected = int(expected)
            except (ValueError, TypeError):
                return {"error": "无效的 _revision"}, 400
            if expected != obj.revision:
                return {"error": "关联关系可能已被其他设备修改，请刷新后重试",
                        "revision": obj.revision}, 409
        for name in relation_fields:
            if name not in payload:
                continue
            raw = payload[name]
            if not isinstance(raw, list):
                return {"error": f"{name} 必须是列表"}, 400
            ids = list(dict.fromkeys(raw))
            if any(not isinstance(x, str) or not x for x in ids):
                return {"error": f"{name} 中包含无效 ID"}, 400
            objects = [db.session.get({"dependency_ids": Task, "requirement_ids": RequirementItem,
                                       "session_ids": EventSession, "task_ids": Task}[name], x) for x in ids]
            if any(x is None or x.project_id != obj.project_id for x in objects):
                return {"error": f"{name} 包含其他项目或不存在的记录"}, 400
            if name == "dependency_ids":
                if obj.id in ids or any(dependency_would_cycle(obj.id, dep) for dep in ids):
                    return {"error": "依赖关系会形成循环，未保存"}, 400
            links[name] = objects
        try:
            result, status = apply_entity_changes(entity_type, entity_id, scalars, actor,
                payload.get("source_ref", ""), critical_confirmed=bool(payload.get("confirm_critical")),
                expected_revision=payload.get("_revision"), commit=False)
            if status != 200:
                db.session.rollback()
                return result, status
            changed = {}
            if "session_ids" in links:
                before = [x.id for x in obj.sessions]
                obj.sessions = links["session_ids"]
                changed["session_ids"] = {"before": before, "after": [x.id for x in obj.sessions]}
            if "task_ids" in links:
                before = [x.id for x in obj.tasks]
                obj.tasks = links["task_ids"]
                changed["task_ids"] = {"before": before, "after": [x.id for x in obj.tasks]}
            if "requirement_ids" in links:
                before = [x.id for x in obj.requirements]
                obj.requirements = links["requirement_ids"]
                changed["requirement_ids"] = {"before": before, "after": [x.id for x in obj.requirements]}
            if "dependency_ids" in links:
                before = [x.depends_on_task_id for x in obj.dependencies]
                obj.dependencies.clear()
                db.session.flush()
                for dep in links["dependency_ids"]:
                    obj.dependencies.append(TaskDependency(depends_on=dep, description="", dependency_type="blocks"))
                changed["dependency_ids"] = {"before": before, "after": [x.id for x in links["dependency_ids"]]}
            effective = {k: v for k, v in changed.items() if v["before"] != v["after"]}
            if effective:
                obj.revision += 1
                if hasattr(obj, "updated_at"):
                    obj.updated_at = utcnow()
                for relation_name, item in effective.items():
                    db.session.add(FieldRevision(
                        entity_type=entity_type, entity_id=obj.id,
                        field_path=relation_name, revision=obj.revision,
                        value_json=item["after"], actor=actor))
                write_audit(actor, "update_links", entity_type, obj.id,
                            before={k:v["before"] for k,v in effective.items()},
                            after={k:v["after"] for k,v in effective.items()},
                            source_ref=payload.get("source_ref", ""))
            db.session.flush()
            result["entity"] = serialize_entity(entity_type, obj)
            result["revision"] = obj.revision
            db.session.commit()
            return result, 200
        except Exception:
            db.session.rollback()
            raise

    @app.patch("/api/work-packages/<entity_id>")
    @login_required
    def patch_work_package(entity_id):
        result, status = patch_with_links("work_packages", entity_id, request.get_json(silent=True) or {},
                                          operator_name(), "session_ids", EventSession)
        return jsonify(result), status

    @app.patch("/api/requirements/<entity_id>")
    @login_required
    def patch_requirement(entity_id):
        result, status = patch_with_links("requirements", entity_id, request.get_json(silent=True) or {},
                                          operator_name(), "task_ids", Task)
        return jsonify(result), status

    @app.patch("/api/tasks/<entity_id>")
    @login_required
    def patch_task(entity_id):
        result, status = patch_with_links("tasks", entity_id, request.get_json(silent=True) or {},
                                          operator_name(), "dependency_ids", Task)
        return jsonify(result), status

    def dependency_would_cycle(task_id, dependency_id):
        # task depends on dependency. A cycle exists if dependency already depends (directly/transitively) on task.
        stack, seen = [dependency_id], set()
        while stack:
            current = stack.pop()
            if current == task_id: return True
            if current in seen: continue
            seen.add(current)
            rows = db.session.scalars(select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == current)).all()
            stack.extend(rows)
        return False

    @app.get("/api/calendar")
    @login_required
    def calendar():
        try:
            start = parse_dt(request.args.get("from") or datetime.now(TZ).replace(day=1).isoformat()).date()
            end = parse_dt(request.args.get("to") or (datetime.now(TZ) + timedelta(days=40)).isoformat()).date()
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        sessions = db.session.scalars(select(EventSession).where(
            or_(and_(EventSession.starts_at.is_not(None), EventSession.starts_at <= datetime.combine(end, time.max, TZ),
                     or_(EventSession.ends_at.is_(None), EventSession.ends_at >= datetime.combine(start, time.min, TZ))),
                and_(EventSession.date_mode == "window", EventSession.window_start <= datetime.combine(end, time.max, TZ), EventSession.window_end >= datetime.combine(start, time.min, TZ))))
            .order_by(EventSession.starts_at)).all()
        nodes = db.session.scalars(select(TimeNode).where(TimeNode.planned_start >= datetime.combine(start, time.min, TZ),
            TimeNode.planned_start <= datetime.combine(end, time.max, TZ)).order_by(TimeNode.planned_start)).all()
        result = []
        for s in sessions:
            data = serialize_session(s)
            data["item_type"] = "window" if s.date_mode == "window" else "session"
            data["is_past"] = bool(s.ends_at and aware(s.ends_at) < datetime.now(TZ))
            data["has_risk"] = any(t["is_overdue"] for t in [serialize_task(x) for x in s.project.tasks]) or any(n.date_status == "冲突" for n in s.time_nodes)
            result.append(data)
        return jsonify(from_date=start.isoformat(), to_date=end.isoformat(), sessions=result,
                       time_nodes=[serialize_time_node(n) | {"project_name": n.project.name, "project_phase": n.project.phase,
                           "session_title": n.session.title if n.session else ""} for n in nodes])

    @app.get("/api/change-requests")
    @login_required
    def list_change_requests():
        status = request.args.get("status")
        query = select(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(300)
        if status:
            query = query.where(ChangeRequest.status == status)
        else:
            query = query.where(ChangeRequest.status.in_(["pending", "conflict"]))
        return jsonify(changes=[serialize_change(c) for c in db.session.scalars(query).all()])

    def resolve_change(change_id, actor, action, note=""):
        change = db.session.get(ChangeRequest, change_id)
        if not change: return {"error": "变更请求不存在"}, 404
        if change.status not in {"pending", "conflict"}: return {"error": "该变更已处理", "status": change.status}, 409
        if action == "reject":
            change.status, change.confirmed_by, change.confirmed_at = "rejected", actor, utcnow()
            change.resolution_note = note[:2000]
            write_audit(actor, "reject_change", change.entity_type, change.entity_id,
                        before={change.field_path: change.old_value}, after={change.field_path: change.new_value}, source_ref=change.source_ref)
            db.session.commit()
            return {"change": serialize_change(change)}, 200
        obj = get_entity(change.entity_type, change.entity_id)
        current = entity_value(obj, change.field_path)
        later_revision = db.session.scalar(select(FieldRevision.id).where(
            FieldRevision.entity_type == change.entity_type, FieldRevision.entity_id == change.entity_id,
            FieldRevision.field_path == change.field_path, FieldRevision.revision > change.base_revision).limit(1))
        if current != change.old_value and current != change.new_value or (later_revision and current != change.new_value):
            change.status = "conflict"
            change.resolution_note = f"冲突：当前值为 {current!r}，申请旧值为 {change.old_value!r}。请重新提出变更。"
            db.session.commit()
            return {"error": "该字段在提案后已发生变化，未覆盖当前值", "change": serialize_change(change),
                    "current_value": current, "proposed_value": change.new_value}, 409
        before = {change.field_path: current}
        if current != change.new_value:
            try:
                setattr(obj, change.field_path, parse_field(change.field_path, change.new_value))
            except (ValueError, TypeError) as exc:
                return {"error": str(exc)}, 400
            if hasattr(obj, "revision"):
                obj.revision += 1
                obj.updated_at = utcnow()
                rev = obj.revision
            else:
                rev = 1
            db.session.add(FieldRevision(entity_type=change.entity_type, entity_id=change.entity_id,
                field_path=change.field_path, revision=rev, value_json=normalize_value(getattr(obj, change.field_path)), actor=actor))
        change.status, change.confirmed_by, change.confirmed_at = "confirmed", actor, utcnow()
        change.resolution_note = note[:2000]
        write_audit(actor, "confirm_change", change.entity_type, change.entity_id, before=before,
                    after={change.field_path: normalize_value(getattr(obj, change.field_path))}, source_ref=change.source_ref)
        db.session.commit()
        return {"change": serialize_change(change), "entity": serialize_entity(change.entity_type, obj)}, 200

    @app.post("/api/change-requests/<change_id>/confirm")
    @login_required
    def confirm_change(change_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True:
            return jsonify(error="重要变更需要显式确认"), 400
        result, status = resolve_change(change_id, operator_name(), "confirm", payload.get("note", ""))
        return jsonify(result), status

    @app.post("/api/change-requests/<change_id>/reject")
    @login_required
    def reject_change(change_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True:
            return jsonify(error="驳回操作需要显式确认"), 400
        result, status = resolve_change(change_id, operator_name(), "reject", payload.get("note", ""))
        return jsonify(result), status

    @app.get("/api/audit")
    @login_required
    def list_audit():
        query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(300)
        entity_type, entity_id = request.args.get("entity_type"), request.args.get("entity_id")
        if entity_type: query = query.where(AuditLog.entity_type == entity_type)
        if entity_id: query = query.where(AuditLog.entity_id == entity_id)
        return jsonify(entries=[serialize_audit(x) for x in db.session.scalars(query).all()])

    @app.post("/api/audit/<int:audit_id>/restore")
    @login_required
    def restore_audit(audit_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True: return jsonify(error="恢复历史需要显式确认"), 400
        entry = db.session.get(AuditLog, audit_id)
        if not entry or not entry.before_json or not entry.entity_type or not entry.entity_id:
            return jsonify(error="该历史记录没有可恢复的字段快照"), 400
        result, status = apply_entity_changes(entry.entity_type, entry.entity_id, entry.before_json, operator_name(),
            source_ref=f"restore:audit:{entry.id}", critical_confirmed=False)
        return jsonify(result), status

    RESOURCE_MODELS = {"clients": Client, "suppliers": Supplier, "contacts": Contact, "venues": Venue,
                       "venue_spaces": VenueSpace, "equipment": VenueEquipment}

    @app.get("/api/resources/<kind>")
    @login_required
    def list_resources(kind):
        if kind not in RESOURCE_MODELS: return jsonify(error="不支持的资源类型"), 404
        query = select(RESOURCE_MODELS[kind])
        q = (request.args.get("q") or "").strip()
        if q and hasattr(RESOURCE_MODELS[kind], "name"):
            query = query.where(RESOURCE_MODELS[kind].name.ilike(f"%{q}%"))
        rows = db.session.scalars(query.order_by(RESOURCE_MODELS[kind].id).limit(500)).all()
        return jsonify(resources=[serialize_resource(kind, x) for x in rows])

    @app.post("/api/resources/<kind>")
    @login_required
    def create_resource(kind):
        if kind not in RESOURCE_MODELS: return jsonify(error="不支持的资源类型"), 404
        payload = request.get_json(silent=True) or {}
        actor = operator_name()
        fields = {k: parse_field(k, v) for k, v in payload.items() if k in FIELD_ALLOWLIST[kind]}
        model = RESOURCE_MODELS[kind]
        required = "name"
        if kind == "venue_spaces": required = "name"
        if not str(fields.get(required, "")).strip(): return jsonify(error="名称不能为空"), 400
        if kind == "contacts" and not fields.get("supplier_id") and not fields.get("client_id") and not fields.get("source_text"):
            # A free-standing contact is allowed when original source text is retained.
            return jsonify(error="联系人尚未关联客户/供应商时，请保留来源原文"), 400
        obj = model(**fields)
        db.session.add(obj)
        db.session.flush()
        write_audit(actor, "create", kind, obj.id, after=serialize_resource(kind, obj), source_ref=payload.get("source_ref", ""))
        db.session.commit()
        return jsonify(resource=serialize_resource(kind, obj)), 201

    @app.patch("/api/resources/<kind>/<entity_id>")
    @login_required
    def patch_resource(kind, entity_id):
        if kind not in RESOURCE_MODELS: return jsonify(error="不支持的资源类型"), 404
        payload = request.get_json(silent=True) or {}
        result, status = apply_entity_changes(kind, entity_id, payload, operator_name(), payload.get("source_ref", ""),
            critical_confirmed=bool(payload.get("confirm_critical")), expected_revision=payload.get("_revision"))
        return jsonify(resource=result.get("entity") if status == 200 else None, **({k: v for k, v in result.items() if k != "entity"})), status

    def process_upload(raw: bytes, original_name: str, ext: str):
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("单个文件不能超过 100MB")
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        suffix = ext.lower()
        if suffix not in ALLOWED_EXT:
            raise ValueError("仅支持 JPG、PNG、WebP、HEIC/HEIF 和 PDF")
        file_id = new_id()
        if suffix == ".pdf":
            if not raw.startswith(b"%PDF"):
                raise ValueError("文件扩展名为 PDF，但内容校验失败")
            path = FILES_DIR / f"{file_id}.pdf"
            tmp = TMP_DIR / f"{file_id}.tmp"
            tmp.write_bytes(raw)
            os.replace(tmp, path)
            optimized_path = ""
            if PdfReader and PdfWriter:
                try:
                    reader = PdfReader(io.BytesIO(raw), strict=False)
                    writer = PdfWriter()
                    for page in reader.pages:
                        try: page.compress_content_streams()
                        except Exception: pass
                        writer.add_page(page)
                    out = io.BytesIO()
                    writer.write(out)
                    optimized = out.getvalue()
                    if optimized and len(optimized) < len(raw) * 0.97:
                        opath = FILES_DIR / f"{file_id}.optimized.pdf"
                        otmp = TMP_DIR / f"{file_id}.optimized.tmp"
                        otmp.write_bytes(optimized)
                        os.replace(otmp, opath)
                        optimized_path = str(opath)
                except Exception:
                    optimized_path = ""
            return {"stored_name": path.name, "mime_type": "application/pdf", "storage_path": str(path),
                    "optimized_path": optimized_path, "thumbnail_path": "", "stored_bytes": raw,
                    "original_size": len(raw), "stored_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if Image is None:
            raise ValueError("图片处理组件未安装")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im = ImageOps.exif_transpose(im)
                im.load()
                has_alpha = "A" in im.getbands() or "transparency" in im.info
                if has_alpha:
                    converted = im.convert("RGBA")
                    buf = io.BytesIO()
                    converted.save(buf, format="PNG", optimize=True, compress_level=8)
                    stored = buf.getvalue()
                    out_ext, mime = ".png", "image/png"
                else:
                    converted = im.convert("RGB")
                    buf = io.BytesIO()
                    converted.save(buf, format="JPEG", quality=87, optimize=True, progressive=True)
                    stored = buf.getvalue()
                    out_ext, mime = ".jpg", "image/jpeg"
                # Save a thumbnail only after successful compression.
                thumb = converted.copy()
                thumb.thumbnail((480, 360))
                tbuf = io.BytesIO()
                thumb.save(tbuf, format="PNG" if has_alpha else "JPEG", optimize=True, quality=80)
                thumb_ext = ".png" if has_alpha else ".jpg"
                stored_path = FILES_DIR / f"{file_id}{out_ext}"
                stored_tmp = TMP_DIR / f"{file_id}.tmp"
                stored_tmp.write_bytes(stored)
                os.replace(stored_tmp, stored_path)
                thumb_path = THUMB_DIR / f"{file_id}{thumb_ext}"
                thumb_tmp = TMP_DIR / f"{file_id}.thumb.tmp"
                thumb_tmp.write_bytes(tbuf.getvalue())
                os.replace(thumb_tmp, thumb_path)
                return {"stored_name": stored_path.name, "mime_type": mime, "storage_path": str(stored_path),
                        "optimized_path": "", "thumbnail_path": str(thumb_path), "stored_bytes": stored,
                        "original_size": len(raw), "stored_size": len(stored), "sha256": hashlib.sha256(stored).hexdigest()}
        except Exception as exc:
            if isinstance(exc, ValueError): raise
            raise ValueError(f"图片处理失败，未清理原始内容：{str(exc)[:160]}")

    def validate_link_target(entity_type, entity_id):
        if not entity_type or not entity_id:
            return True
        if entity_type not in ENTITY_MODELS:
            return False
        return db.session.get(ENTITY_MODELS[entity_type], entity_id) is not None

    @app.get("/api/documents")
    @login_required
    def list_documents():
        entity_type, entity_id = request.args.get("entity_type"), request.args.get("entity_id")
        if entity_type and entity_id:
            ids = db.session.scalars(select(DocumentLink.document_id).where(DocumentLink.entity_type == entity_type, DocumentLink.entity_id == entity_id)).all()
            docs = db.session.scalars(select(Document).where(Document.id.in_(ids)).order_by(Document.created_at.desc())).all() if ids else []
        else:
            docs = db.session.scalars(select(Document).order_by(Document.created_at.desc()).limit(300)).all()
        return jsonify(documents=[serialize_document(d) for d in docs])

    @app.post("/api/documents")
    @login_required
    def upload_documents():
        actor = operator_name()
        files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
        if not files:
            return jsonify(error="请选择至少一个文件"), 400
        total = sum(len(f.read()) for f in files)
        for f in files: f.stream.seek(0)
        if total > MAX_BATCH_BYTES:
            return jsonify(error="批量上传总量不能超过 250MB"), 413
        entity_type, entity_id = request.form.get("entity_type", ""), request.form.get("entity_id", "")
        if entity_type and entity_id and not validate_link_target(entity_type, entity_id):
            return jsonify(error="附件关联对象不存在"), 400
        category = (request.form.get("category") or "其他")[:100]
        series_id = (request.form.get("series_id") or "").strip()
        is_official = request.form.get("is_official") == "1"
        created, failures = [], []
        for file in files:
            try:
                original_name = secure_filename(file.filename or "upload") or "upload"
                ext = Path(original_name).suffix.lower()
                raw = file.read()
                processed = process_upload(raw, original_name, ext)
                if series_id:
                    max_version = db.session.scalar(select(func.max(Document.version_no)).where(Document.series_id == series_id)) or 0
                    version_no = max_version + 1
                    prev = db.session.scalar(select(Document.id).where(Document.series_id == series_id).order_by(Document.version_no.desc()).limit(1)) or ""
                else:
                    series_id, version_no, prev = new_id(), 1, ""
                doc = Document(series_id=series_id, version_no=version_no, previous_document_id=prev,
                    original_name=(file.filename or original_name)[:300], stored_name=processed["stored_name"],
                    mime_type=processed["mime_type"], category=category, sha256=processed["sha256"],
                    storage_path=processed["storage_path"], optimized_path=processed["optimized_path"],
                    thumbnail_path=processed["thumbnail_path"], original_size=processed["original_size"],
                    stored_size=processed["stored_size"], is_official=is_official, uploaded_by=actor,
                    notes=(request.form.get("notes") or "")[:4000])
                db.session.add(doc)
                db.session.flush()
                if entity_type and entity_id:
                    db.session.add(DocumentLink(document_id=doc.id, entity_type=entity_type, entity_id=entity_id,
                        link_role=(request.form.get("link_role") or "attachment")[:80], created_by=actor))
                write_audit(actor, "upload_document", entity_type, entity_id, after={"document_id": doc.id, "name": doc.original_name,
                    "sha256": doc.sha256, "version_no": doc.version_no}, source_ref=request.form.get("source_ref", ""))
                db.session.commit()
                created.append(serialize_document(doc))
                series_id = ""  # each selected file is its own series unless explicitly uploading a replacement
            except Exception as exc:
                db.session.rollback()
                failures.append({"filename": file.filename or "upload", "error": str(exc)[:300]})
        return jsonify(documents=created, failures=failures), (207 if failures and created else (400 if failures else 201))

    @app.get("/api/documents/<document_id>/content")
    @login_required
    def document_content(document_id):
        doc = db.session.get(Document, document_id)
        if not doc: return jsonify(error="文件不存在"), 404
        variant = request.args.get("variant", "preview")
        path = doc.storage_path
        if variant == "thumbnail" and doc.thumbnail_path:
            path = doc.thumbnail_path
        elif variant == "preview" and doc.optimized_path:
            path = doc.optimized_path
        p = Path(path).resolve()
        if not p.is_file() or (DATA_DIR not in p.parents): return jsonify(error="文件内容不存在"), 404
        as_attachment = variant == "download"
        return send_file(p, mimetype=doc.mime_type, as_attachment=as_attachment,
                         download_name=doc.original_name if as_attachment else None, conditional=True)

    @app.post("/api/documents/<document_id>/shares")
    @login_required
    def create_share(document_id):
        payload = request.get_json(silent=True) or {}
        actor = operator_name()
        doc = db.session.get(Document, document_id)
        if not doc: return jsonify(error="文件不存在"), 404
        try: days = int(payload.get("days", 7))
        except (ValueError, TypeError): days = 7
        if days < 1 or days > 30: return jsonify(error="分享有效期只能设置 1–30 天"), 400
        token = secrets.token_urlsafe(32)
        link = ShareLink(document_id=doc.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=utcnow() + timedelta(days=days), allow_download=bool(payload.get("allow_download", True)), created_by=actor)
        db.session.add(link)
        write_audit(actor, "create_share", "documents", doc.id, after={"share_id": link.id, "expires_at": as_iso(link.expires_at)})
        db.session.commit()
        return jsonify(share={"id": link.id, "url": f"/share/{token}", "expires_at": as_iso(link.expires_at), "allow_download": link.allow_download}), 201

    @app.post("/api/shares/<share_id>/revoke")
    @login_required
    def revoke_share(share_id):
        payload = request.get_json(silent=True) or {}
        if payload.get("confirm") is not True: return jsonify(error="撤销分享需要显式确认"), 400
        actor = operator_name()
        link = db.session.get(ShareLink, share_id)
        if not link: return jsonify(error="分享链接不存在"), 404
        link.revoked_at = utcnow()
        write_audit(actor, "revoke_share", "documents", link.document_id, after={"share_id": link.id, "revoked_at": as_iso(link.revoked_at)})
        db.session.commit()
        return jsonify(ok=True, revoked_at=as_iso(link.revoked_at))

    @app.get("/share/<token>")
    def public_share(token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        link = db.session.scalar(select(ShareLink).where(ShareLink.token_hash == digest))
        if not link or link.revoked_at or aware(link.expires_at) < datetime.now(TZ):
            return jsonify(error="分享链接已失效或已撤销"), 410
        doc = link.document
        path = Path(doc.optimized_path or doc.storage_path).resolve()
        if not path.is_file() or DATA_DIR not in path.parents: return jsonify(error="文件不存在"), 404
        download = request.args.get("download") == "1" and link.allow_download
        return send_file(path, mimetype=doc.mime_type, as_attachment=download,
                         download_name=doc.original_name if download else None, conditional=True)

    @app.get("/api/shares")
    @login_required
    def list_shares():
        links = db.session.scalars(select(ShareLink).order_by(ShareLink.created_at.desc()).limit(300)).all()
        return jsonify(shares=[{"id": x.id, "document_id": x.document_id, "document_name": x.document.original_name,
            "expires_at": as_iso(x.expires_at), "allow_download": x.allow_download, "revoked_at": as_iso(x.revoked_at),
            "created_by": x.created_by, "created_at": as_iso(x.created_at)} for x in links])

    @app.get("/api/search")
    @login_required
    def global_search():
        q = (request.args.get("q") or "").strip()
        if len(q) < 2: return jsonify(results=[])
        pattern = f"%{q}%"
        results = []
        for p in db.session.scalars(select(Project).where(or_(Project.name.ilike(pattern), Project.client_snapshot.ilike(pattern), Project.owner.ilike(pattern))).limit(20)).all():
            results.append({"type": "project", "id": p.id, "title": p.name, "subtitle": (p.client.name if p.client else p.client_snapshot) or p.owner, "url": f"#/projects/{p.id}"})
        for t in db.session.scalars(select(Task).where(or_(Task.name.ilike(pattern), Task.source_text.ilike(pattern), Task.owner.ilike(pattern))).limit(20)).all():
            results.append({"type": "task", "id": t.id, "title": t.name, "subtitle": t.project.name + " · " + t.status, "url": f"#/projects/{t.project_id}?tab=tasks"})
        for r in db.session.scalars(select(RequirementItem).where(or_(RequirementItem.name.ilike(pattern), RequirementItem.specification.ilike(pattern), RequirementItem.source_text.ilike(pattern))).limit(20)).all():
            results.append({"type": "requirement", "id": r.id, "title": r.name, "subtitle": r.project.name + " · 需求清单", "url": f"#/projects/{r.project_id}?tab=requirements"})
        return jsonify(results=results[:50])

    return app


def init_database(app: Flask, seed_demo: bool = False):
    with app.app_context():
        db.create_all()
        db.session.merge(SchemaMeta(key="schema_version", value="0.4.1"))
        username = os.environ.get("SHARED_USERNAME", "activity")
        display_name = os.environ.get("SHARED_DISPLAY_NAME", "活动工作台共享账号")
        password = os.environ.get("SHARED_PASSWORD", "")
        user = db.session.scalar(select(AppUser).where(AppUser.username == username))
        if not user:
            if len(password) < 14:
                raise RuntimeError("首次初始化必须设置至少 14 位 SHARED_PASSWORD；不要使用默认密码")
            db.session.add(AppUser(username=username, display_name=display_name, password_hash=generate_password_hash(password)))
        elif password and not check_password_hash(user.password_hash, password):
            raise RuntimeError("数据库已有共享账号，但密码与当前环境变量不一致。请人工核对，不自动覆盖")
        if seed_demo and db.session.scalar(select(Project.id).limit(1)) is None:
            seed_demo_data()
        db.session.commit()


def seed_demo_data():
    """Create explicitly requested demo data; never called by init-db by default."""
    from models import Client
    client = Client(name="示例客户", aliases="Demo", notes="仅用于本地演示；不是生产数据")
    db.session.add(client)
    db.session.flush()
    project = Project(name="示例活动执行项目", client_id=client.id, client_snapshot=client.name, owner="演示操作人",
                      phase="筹备执行", description="演示项目：包含多场次、工作包、需求项和执行任务。")
    db.session.add(project)
    db.session.flush()
    s = EventSession(project_id=project.id, title="示例活动场次", starts_at=datetime.now(TZ) + timedelta(days=3),
                     ends_at=datetime.now(TZ) + timedelta(days=3, hours=2), date_mode="fixed", location_text="待核实场地", status="暂定")
    db.session.add(s)
    db.session.flush()
    package = WorkPackage(project_id=project.id, name="舞台与背景板", status="准备中", responsibility="舞台搭建、背景板安装")
    db.session.add(package)
    db.session.flush()
    package.sessions.append(s)
    req = RequirementItem(project_id=project.id, work_package_id=package.id, name="主题背景板", specification="规格待确认", quantity_text="1", quantity_unit="块", status="待确认")
    task = Task(project_id=project.id, work_package_id=package.id, name="确认背景板最终尺寸", owner="演示操作人", status="待办", needs_review=True)
    db.session.add_all([req, task])
    db.session.flush()
    node = TimeNode(project_id=project.id, session_id=s.id, node_type="布场", label="布场进场", planned_start=s.starts_at - timedelta(hours=6),
                    date_status="待确认", move_rule="follow_session", responsible="供应商待定", source_text="演示数据，时间仅供体验")
    db.session.add(node)
    write_audit("system-demo", "seed_demo", "projects", project.id, after={"name": project.name})


def main():
    parser = argparse.ArgumentParser(description="活动执行工作台 V0.4.1")
    parser.add_argument("command", choices=["serve", "init-db", "seed-demo"], nargs="?", default="serve")
    args = parser.parse_args()
    app = create_app()
    if args.command == "init-db":
        init_database(app, seed_demo=False)
        print("数据库初始化完成（未写入样例项目）。")
        return
    if args.command == "seed-demo":
        init_database(app, seed_demo=True)
        print("演示数据初始化完成。")
        return
    host = os.environ.get("ACTIVITY_HOST", "0.0.0.0")
    port = int(os.environ.get("ACTIVITY_PORT", "8097"))
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
