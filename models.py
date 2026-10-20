"""Normalized SQLAlchemy models for Event Time / Activity Workbench V0.4.1."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text,
    UniqueConstraint, Table, Column, BigInteger
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


work_package_sessions = Table(
    "work_package_sessions", Base.metadata,
    Column("work_package_id", String(36), ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
    Column("session_id", String(36), ForeignKey("event_sessions.id", ondelete="CASCADE"), primary_key=True),
)

task_requirements = Table(
    "task_requirements", Base.metadata,
    Column("task_id", String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("requirement_id", String(36), ForeignKey("requirement_items.id", ondelete="CASCADE"), primary_key=True),
)


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    aliases: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    contacts: Mapped[list["Contact"]] = relationship(back_populates="client", cascade="all, delete-orphan")


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    service_category: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    contacts: Mapped[list["Contact"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    work_packages: Mapped[list["WorkPackage"]] = relationship(back_populates="supplier")


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    supplier: Mapped[Supplier | None] = relationship(back_populates="contacts")
    client: Mapped[Client | None] = relationship(back_populates="contacts")


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_status: Mapped[str] = mapped_column(String(60), default="待核实", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    spaces: Mapped[list["VenueSpace"]] = relationship(back_populates="venue", cascade="all, delete-orphan")


class VenueSpace(Base):
    __tablename__ = "venue_spaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    space_type: Mapped[str] = mapped_column(String(80), default="厅室", nullable=False)
    floor_label: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_status: Mapped[str] = mapped_column(String(60), default="待核实", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    venue: Mapped[Venue] = relationship(back_populates="spaces")
    parent: Mapped["VenueSpace | None"] = relationship(remote_side="VenueSpace.id", back_populates="children")
    children: Mapped[list["VenueSpace"]] = relationship(back_populates="parent")
    equipment: Mapped[list["VenueEquipment"]] = relationship(back_populates="space", cascade="all, delete-orphan")


class VenueEquipment(Base):
    __tablename__ = "venue_equipment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    ownership: Mapped[str] = mapped_column(String(80), default="场地固定", nullable=False)
    physical_dimensions: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    resolution: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    pixel_pitch: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    loading_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    power_audio_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_status: Mapped[str] = mapped_column(String(60), default="待核实", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    space: Mapped[VenueSpace | None] = relationship(back_populates="equipment")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    client_snapshot: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phase: Mapped[str] = mapped_column(String(60), default="新登记", nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_document_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    client: Mapped[Client | None] = relationship()
    sessions: Mapped[list["EventSession"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="EventSession.starts_at")
    time_nodes: Mapped[list["TimeNode"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    work_packages: Mapped[list["WorkPackage"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    requirements: Mapped[list["RequirementItem"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class EventSession(Base):
    __tablename__ = "event_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_mode: Mapped[str] = mapped_column(String(40), default="undated", nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    venue_space_id: Mapped[str | None] = mapped_column(ForeignKey("venue_spaces.id", ondelete="SET NULL"), nullable=True, index=True)
    location_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="待排期", nullable=False)
    cover_document_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    project: Mapped[Project] = relationship(back_populates="sessions")
    venue_space: Mapped[VenueSpace | None] = relationship()
    time_nodes: Mapped[list["TimeNode"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    work_packages: Mapped[list["WorkPackage"]] = relationship(secondary=work_package_sessions, back_populates="sessions")


class TimeNode(Base):
    __tablename__ = "time_nodes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("event_sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    work_package_id: Mapped[str | None] = mapped_column(ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(60), default="截止", nullable=False)
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_status: Mapped[str] = mapped_column(String(40), default="待确认", nullable=False)
    move_rule: Mapped[str] = mapped_column(String(40), default="follow_session", nullable=False)
    responsible: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="待办", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    project: Mapped[Project] = relationship(back_populates="time_nodes")
    session: Mapped[EventSession | None] = relationship(back_populates="time_nodes")


class WorkPackage(Base):
    __tablename__ = "work_packages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="待指派", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    contact_snapshot: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    responsibility: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="", nullable=False)
    planned_entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_strike_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    project: Mapped[Project] = relationship(back_populates="work_packages")
    supplier: Mapped[Supplier | None] = relationship(back_populates="work_packages")
    sessions: Mapped[list[EventSession]] = relationship(secondary=work_package_sessions, back_populates="work_packages")
    requirements: Mapped[list["RequirementItem"]] = relationship(back_populates="work_package")
    tasks: Mapped[list["Task"]] = relationship(back_populates="work_package")


class RequirementItem(Base):
    __tablename__ = "requirement_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id: Mapped[str | None] = mapped_column(ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    specification: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dimensions: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    dimension_unit: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    quantity_text: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    intended_use: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="", nullable=False)
    delivered_quantity_text: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="待澄清", nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    project: Mapped[Project] = relationship(back_populates="requirements")
    work_package: Mapped[WorkPackage | None] = relationship(back_populates="requirements")
    tasks: Mapped[list["Task"]] = relationship(secondary=task_requirements, back_populates="requirements")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    work_package_id: Mapped[str | None] = mapped_column(ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="待办", nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    responsible_party: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    actual_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_document_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    project: Mapped[Project] = relationship(back_populates="tasks")
    work_package: Mapped[WorkPackage | None] = relationship(back_populates="tasks")
    requirements: Mapped[list[RequirementItem]] = relationship(secondary=task_requirements, back_populates="tasks")
    dependencies: Mapped[list["TaskDependency"]] = relationship(foreign_keys="TaskDependency.task_id", back_populates="task", cascade="all, delete-orphan")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(40), default="blocks", nullable=False)
    task: Mapped[Task] = relationship(foreign_keys=[task_id], back_populates="dependencies")
    depends_on: Mapped[Task] = relationship(foreign_keys=[depends_on_task_id])


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    series_id: Mapped[str] = mapped_column(String(36), default=new_id, nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_document_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    original_name: Mapped[str] = mapped_column(String(300), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="其他", nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    optimized_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stored_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(60), default="ready", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    links: Mapped[list["DocumentLink"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    shares: Mapped[list["ShareLink"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("series_id", "version_no", name="uq_document_series_version"),)


class DocumentLink(Base):
    __tablename__ = "document_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    link_role: Mapped[str] = mapped_column(String(80), default="attachment", nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    document: Mapped[Document] = relationship(back_populates="links")
    __table_args__ = (UniqueConstraint("document_id", "entity_type", "entity_id", "link_role", name="uq_document_link"),)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    field_path: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[object] = mapped_column(JSON, nullable=True)
    new_value: Mapped[object] = mapped_column(JSON, nullable=True)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    confirmed_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FieldRevision(Base):
    __tablename__ = "field_revisions"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    field_path: Mapped[str] = mapped_column(String(120), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    value_json: Mapped[object] = mapped_column(JSON, nullable=True)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (Index("idx_field_revision_lookup", "entity_type", "entity_id", "field_path", "revision"),)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    before_json: Mapped[object] = mapped_column(JSON, nullable=True)
    after_json: Mapped[object] = mapped_column(JSON, nullable=True)
    source_ref: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class ShareLink(Base):
    __tablename__ = "share_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allow_download: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    document: Mapped[Document] = relationship(back_populates="shares")


class SchemaMeta(Base):
    __tablename__ = "schema_meta"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(String(240), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
