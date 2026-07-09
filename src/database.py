from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import AttachmentRecord, DailyStatusRow, EmailRecord


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(
                """
                create table if not exists email_records (
                    id integer primary key autoincrement,
                    email_uid text unique,
                    subject text,
                    sender_name text,
                    sender_email text,
                    received_time text,
                    has_attachment integer,
                    created_at text default current_timestamp
                );
                create table if not exists attachment_records (
                    id integer primary key autoincrement,
                    email_uid text,
                    subject text,
                    sender_email text,
                    raw_device_code text,
                    normalized_mast_id text,
                    display_name text,
                    filename text,
                    file_path text unique,
                    file_extension text,
                    file_size_bytes integer,
                    file_size_kb real,
                    email_received_date text,
                    attachment_date text,
                    data_date text,
                    size_status text,
                    created_at text default current_timestamp
                );
                create table if not exists daily_mast_status (
                    id integer primary key autoincrement,
                    stat_date text,
                    normalized_mast_id text,
                    display_name text,
                    received integer,
                    attachment_count integer,
                    min_file_size_kb real,
                    has_size_warning integer,
                    missing_today integer,
                    continuous_missing_days integer,
                    missing_status text,
                    recovered_today integer,
                    created_at text default current_timestamp,
                    unique(stat_date, normalized_mast_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_email_records(self, rows: Iterable[EmailRecord]) -> None:
        conn = self.connect()
        try:
            conn.executemany(
                """
                insert into email_records (email_uid, subject, sender_name, sender_email, received_time, has_attachment)
                values (?, ?, ?, ?, ?, ?)
                on conflict(email_uid) do update set
                    subject=excluded.subject,
                    sender_name=excluded.sender_name,
                    sender_email=excluded.sender_email,
                    received_time=excluded.received_time,
                    has_attachment=excluded.has_attachment
                """,
                [(r.email_uid, r.subject, r.sender_name, r.sender_email, r.received_time, r.has_attachment) for r in rows],
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_attachment_records(self, rows: Iterable[AttachmentRecord]) -> None:
        conn = self.connect()
        try:
            conn.executemany(
                """
                insert into attachment_records (
                    email_uid, subject, sender_email, raw_device_code, normalized_mast_id, display_name,
                    filename, file_path, file_extension, file_size_bytes, file_size_kb, email_received_date,
                    attachment_date, data_date, size_status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(file_path) do nothing
                """,
                [
                    (
                        r.email_uid, r.subject, r.sender_email, r.raw_device_code, r.normalized_mast_id,
                        r.display_name, r.filename, r.file_path, r.file_extension, r.file_size_bytes,
                        r.file_size_kb, r.email_received_date, r.attachment_date, r.data_date, r.size_status
                    )
                    for r in rows
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def attachment_rows_for_date(self, stat_date: str) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "select * from attachment_records where email_received_date = ? order by normalized_mast_id, filename",
                (stat_date,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def daily_rows_for_date(self, stat_date: str) -> list[dict]:
        conn = self.connect()
        try:
            rows = conn.execute("select * from daily_mast_status where stat_date = ?", (stat_date,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def upsert_daily_status(self, rows: Iterable[DailyStatusRow]) -> None:
        conn = self.connect()
        try:
            conn.executemany(
                """
                insert into daily_mast_status (
                    stat_date, normalized_mast_id, display_name, received, attachment_count, min_file_size_kb,
                    has_size_warning, missing_today, continuous_missing_days, missing_status, recovered_today
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(stat_date, normalized_mast_id) do update set
                    display_name=excluded.display_name,
                    received=excluded.received,
                    attachment_count=excluded.attachment_count,
                    min_file_size_kb=excluded.min_file_size_kb,
                    has_size_warning=excluded.has_size_warning,
                    missing_today=excluded.missing_today,
                    continuous_missing_days=excluded.continuous_missing_days,
                    missing_status=excluded.missing_status,
                    recovered_today=excluded.recovered_today
                """,
                [
                    (
                        r.stat_date, r.normalized_mast_id, r.display_name, r.received, r.attachment_count,
                        r.min_file_size_kb, r.has_size_warning, r.missing_today, r.continuous_missing_days,
                        r.missing_status, r.recovered_today
                    )
                    for r in rows
                ],
            )
            conn.commit()
        finally:
            conn.close()
