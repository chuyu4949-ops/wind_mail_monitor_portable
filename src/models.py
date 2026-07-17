from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MailMessage:
    email_uid: str
    subject: str
    sender_name: str
    sender_email: str
    received_time: datetime
    attachments: list[tuple[str, bytes]]
    source_folder: str = "INBOX"


@dataclass(frozen=True)
class EmailRecord:
    email_uid: str
    subject: str
    sender_name: str
    sender_email: str
    received_time: str
    has_attachment: int


@dataclass(frozen=True)
class AttachmentRecord:
    email_uid: str
    subject: str
    sender_email: str
    raw_device_code: str
    normalized_mast_id: str
    display_name: str
    filename: str
    file_path: str
    file_extension: str
    file_size_bytes: int
    file_size_kb: float
    email_received_date: str
    attachment_date: str
    data_date: str
    size_status: str


@dataclass(frozen=True)
class SavedAttachment:
    email: EmailRecord
    attachment: AttachmentRecord


@dataclass(frozen=True)
class DailyStatusRow:
    stat_date: str
    normalized_mast_id: str
    display_name: str
    received: int
    attachment_count: int
    min_file_size_kb: float
    has_size_warning: int
    missing_today: int
    continuous_missing_days: int
    missing_status: str
    recovered_today: int


@dataclass(frozen=True)
class DailyResult:
    stat_date: str
    received_rows: list[dict]
    missing_rows: list[dict]
    continuous_missing_rows: list[dict]
    size_warning_rows: list[dict]
    attachment_rows: list[dict]
    unknown_rows: list[dict]
    status_rows: list[DailyStatusRow]
