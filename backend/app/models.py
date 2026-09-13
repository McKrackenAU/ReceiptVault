from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def uuid_pk() -> mapped_column:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def utcnow() -> mapped_column:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = utcnow()
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="Australia/Melbourne", nullable=False)

    sessions: Mapped[list[Session]] = relationship(back_populates="user")
    recovery_codes: Mapped[list[RecoveryCode]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = utcnow()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = utcnow()
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = utcnow()

    user: Mapped[User] = relationship(back_populates="recovery_codes")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = utcnow()


class MailboxAccount(Base):
    __tablename__ = "mailbox_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    masked_address: Mapped[str] = mapped_column(String(320), nullable=False)
    address_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, default="personal")
    ms_user_id: Mapped[str | None] = mapped_column(String(128))
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime] = utcnow()
    last_token_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_status: Mapped[str] = mapped_column(String(32), default="idle", nullable=False)
    emails_examined: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mock_identity: Mapped[str | None] = mapped_column(String(64))


class MailFolder(Base):
    __tablename__ = "mail_folders"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailbox_accounts.id"), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    well_known: Mapped[str | None] = mapped_column(String(64))


class MailMessage(Base):
    __tablename__ = "mail_messages"
    __table_args__ = (UniqueConstraint("account_id", "provider_id", name="uq_mail_message_provider"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailbox_accounts.id"), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mail_folders.id"))
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False)
    internet_message_id: Mapped[str | None] = mapped_column(String(512))
    subject: Mapped[str | None] = mapped_column(String(998))
    sender: Mapped[str | None] = mapped_column(String(512))
    recipients: Mapped[dict | None] = mapped_column(JSONB)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = utcnow()
    sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    candidate_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    software_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)


class ScanCheckpoint(Base):
    __tablename__ = "scan_checkpoints"

    id: Mapped[uuid.UUID] = uuid_pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mailbox_accounts.id"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id"))
    folder_provider_id: Mapped[str | None] = mapped_column(String(128))
    cursor: Mapped[str | None] = mapped_column(Text)
    high_water_mark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_token: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = utcnow()


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = utcnow()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id: Mapped[uuid.UUID] = uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id"), nullable=False)
    started_at: Mapped[datetime] = utcnow()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EvidenceObject(Base):
    __tablename__ = "evidence_objects"

    id: Mapped[uuid.UUID] = uuid_pk()
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    display_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    detected_type: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_relpath: Mapped[str] = mapped_column(String(512), nullable=False)
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mailbox_accounts.id"))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mail_messages.id"))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ingested_at: Mapped[datetime] = utcnow()
    processing_history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ocr_version: Mapped[str | None] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_objects.id"))
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_objects.id"))
    is_original: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unsupported_label: Mapped[str | None] = mapped_column(String(128))
    financial_year: Mapped[str | None] = mapped_column(String(16), index=True)
    fy_source: Mapped[str | None] = mapped_column(String(32))


class EvidenceRelationship(Base):
    __tablename__ = "evidence_relationships"

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    abn: Mapped[str | None] = mapped_column(String(16))
    address: Mapped[str | None] = mapped_column(Text)


class ExtractedDocument(Base):
    __tablename__ = "extracted_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"), nullable=False, unique=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    doc_type: Mapped[str | None] = mapped_column(String(64))
    document_number: Mapped[str | None] = mapped_column(String(128))
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_time: Mapped[str | None] = mapped_column(String(16))
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    discounts: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    shipping: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    tip: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    total: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    payment_method: Mapped[str | None] = mapped_column(String(64))
    payment_masked: Mapped[str | None] = mapped_column(String(64))
    reimbursement_indicator: Mapped[str | None] = mapped_column(String(64))
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    engine_version: Mapped[str | None] = mapped_column(String(64))
    validation_flags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    fields_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = utcnow()


class ExtractedPage(Base):
    __tablename__ = "extracted_pages"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_documents.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)


class TextBlock(Base):
    __tablename__ = "text_blocks"

    id: Mapped[uuid.UUID] = uuid_pk()
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_pages.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    y: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    width: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    height: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_documents.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text)
    current_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    page_number: Mapped[int | None] = mapped_column(Integer)
    history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_documents.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    suggested_status: Mapped[str] = mapped_column(String(32), default="needs_review", nullable=False)
    suggested_category: Mapped[str | None] = mapped_column(String(64))
    suggestion_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    paid_personally: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    reimbursed: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    work_related: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    work_use_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    work_purpose: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(16), default="undecided", nullable=False)
    adviser_note: Mapped[str | None] = mapped_column(Text)
    history: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class FinancialYear(Base):
    __tablename__ = "financial_years"

    id: Mapped[uuid.UUID] = uuid_pk()
    label: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    starts_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TaxpayerProfile(Base):
    __tablename__ = "taxpayer_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    adviser_notes: Mapped[str | None] = mapped_column(Text)
    common_equipment: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reimbursement_rules: Mapped[str | None] = mapped_column(Text)
    audit_years: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = utcnow()


class TaxpayerPeriod(Base):
    __tablename__ = "taxpayer_periods"

    id: Mapped[uuid.UUID] = uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("taxpayer_profiles.id"), nullable=False)
    role_title: Mapped[str] = mapped_column(String(160), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(160))
    employer: Mapped[str | None] = mapped_column(String(160))
    duties: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(160))
    started_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_objects.id"))
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = utcnow()


class DuplicateMember(Base):
    __tablename__ = "duplicate_members"

    id: Mapped[uuid.UUID] = uuid_pk()
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duplicate_groups.id"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)


class VirtualFolder(Base):
    __tablename__ = "virtual_folders"

    id: Mapped[uuid.UUID] = uuid_pk()
    path: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    parent_path: Mapped[str | None] = mapped_column(String(512))


class FolderMembership(Base):
    __tablename__ = "folder_memberships"
    __table_args__ = (UniqueConstraint("folder_id", "evidence_id", name="uq_folder_member"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    folder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("virtual_folders.id"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"), nullable=False)


class TransferSession(Base):
    __tablename__ = "transfer_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    relative_path: Mapped[str | None] = mapped_column(String(512))
    mime_hint: Mapped[str | None] = mapped_column(String(128))
    total_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_sha256: Mapped[str | None] = mapped_column(String(64))
    uploaded_parts: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = utcnow()


class TransferChunk(Base):
    __tablename__ = "transfer_chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfer_sessions.id"), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = utcnow()


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    archive_relpath: Mapped[str | None] = mapped_column(String(512))
    manifest: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = utcnow()


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    financial_year: Mapped[str | None] = mapped_column(String(16))
    selection: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("packages.id"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processing_jobs.id"))
    created_at: Mapped[datetime] = utcnow()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    created_at: Mapped[datetime] = utcnow()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str | None] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)


class OauthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[uuid.UUID] = uuid_pk()
    state: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    mock_identity: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = utcnow()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
