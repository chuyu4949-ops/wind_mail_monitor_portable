from __future__ import annotations

import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile
import base64
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from src.app_constants import APP_VERSION, PRODUCT_CODE
from src.attachment_downloader import save_attachments
from src.database import Database
from src.licensing import LicenseCheckPoint, LicenseRequirement, require_valid_license
from src.licensing.audit_log import append_license_audit_event
import src.licensing.license_manager as license_manager
from src.licensing.ed25519_core import publickey, sign, verify
from src.licensing.license_canonical import canonical_payload
from src.licensing.license_request import build_license_change_request, build_license_request, export_license_request
from src.licensing.machine_fingerprint import get_machine_fingerprint
from src.licensing.license_validator import validate_signed_license
from src.licensing.license_watermark import watermark_text
from src.licensing.machine_fingerprint import MachineFingerprint, _normalize, _short_machine_code
from src.licensing.time_guard import check_and_update_time_state
from src.mail_client import _fetch_once, _imap_date, _mailboxes_to_scan, _message_matches, _search_before_date
from src.mail_provider import apply_mail_provider_defaults, provider_for_account
from src.mast_parser import is_supported_wind_filename, parse_attachment, payload_has_stat_date
from src.models import AttachmentRecord, DailyStatusRow, MailMessage
from src.report_generator import generate_html_report, generate_xlsx_report
from src.rules import calculate_daily_status


def _test_keypair() -> dict[str, str]:
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    return {
        "private_seed_b64": base64.b64encode(seed).decode("ascii"),
        "public_key_b64": base64.b64encode(publickey(seed)).decode("ascii"),
    }


def _issue_test_license(
    private_seed_b64: str,
    license_id: str,
    customer_code: str,
    customer_name: str,
    machine_hash: str,
    machine_code: str,
    issue_date: date,
    effective_date: date,
    expiry_date: date,
    features: list[str] | None = None,
) -> dict:
    payload = {
        "license_id": license_id,
        "customer_code": customer_code,
        "customer_name": customer_name,
        "product_code": PRODUCT_CODE,
        "edition": "standard",
        "max_mailboxes": 1,
        "features": features or ["mail_monitor", "excel_report", "html_report", "email_report"],
        "machine_hash": machine_hash,
        "machine_code": machine_code,
        "issue_date": issue_date.isoformat(),
        "effective_date": effective_date.isoformat(),
        "expiry_date": expiry_date.isoformat(),
    }
    seed = base64.b64decode(private_seed_b64)
    signature = base64.b64encode(sign(seed, canonical_payload(payload))).decode("ascii")
    return {
        "format_version": 1,
        "signature_algorithm": "Ed25519",
        "payload": payload,
        "signature": signature,
    }


class SilentLogger:
    def info(self, *args, **kwargs):
        pass


class CoreTests(unittest.TestCase):
    def test_parse_rld_and_molas_zip_name(self) -> None:
        rld = parse_attachment("006688_2025-04-25_00.00_000933.rld")
        self.assertEqual(rld["raw_device_code"], "006688")
        self.assertEqual(rld["normalized_mast_id"], "6688")
        self.assertEqual(rld["data_date"], "2025-04-25")

        molas = parse_attachment("Molas B300-3243-20260707-2.zip")
        self.assertEqual(molas["raw_device_code"], "3243")
        self.assertEqual(molas["attachment_date"], "2026-07-07")

    def test_parse_supported_sample_filename_formats(self) -> None:
        cases = {
            "009357_2024-12-20_00.00_000628.rld": ("9357", "2024-12-20"),
            "0908820260716m10.swift": ("9088", "2026-07-16"),
            "745420170402213.RWD": ("7454", "2017-04-02"),
            "8002202607100328.dat": ("8002", "2026-07-10"),
            "Molas B300-3243WindSpeedAverage20250719.txt": ("3243", "2025-07-19"),
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                parsed = parse_attachment(filename)
                self.assertEqual(parsed["normalized_mast_id"], expected[0])
                self.assertEqual(parsed["data_date"], expected[1])
                self.assertTrue(is_supported_wind_filename(filename))

        zip_name = "Molas B300-3242-20260717-2.zip"
        parsed_zip = parse_attachment(zip_name)
        self.assertEqual(parsed_zip["normalized_mast_id"], "3242")
        self.assertEqual(parsed_zip["attachment_date"], "2026-07-17")
        self.assertTrue(is_supported_wind_filename(zip_name))

    def test_zip_payload_uses_inner_molas_data_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("Molas B300-3243WindSpeedAverage20260716.txt", "2026-07-16 00:00")
            self.assertTrue(payload_has_stat_date(archive_path.read_bytes(), date(2026, 7, 16)))

    def test_parse_subject_prefers_mast_id_over_height(self) -> None:
        parsed = parse_attachment("data.rar", subject="hu nan yi yang yuan jiang 160m 6690")
        self.assertEqual(parsed["normalized_mast_id"], "6690")

        parsed = parse_attachment("data.zip", subject="hu nan zhu zhou lu kou 140m 26115")
        self.assertEqual(parsed["normalized_mast_id"], "26115")

    def test_parse_six_digit_attachment_prefix_as_mast_data(self) -> None:
        parsed = parse_attachment("006690_20260710.txt", subject="ordinary subject", default_year=2026)
        self.assertEqual(parsed["raw_device_code"], "006690")
        self.assertEqual(parsed["normalized_mast_id"], "6690")
        self.assertEqual(parsed["data_date"], "2026-07-10")
        self.assertEqual(parsed["display_name"], "6690#测风塔")

    def test_parse_historical_month_day_without_year(self) -> None:
        parsed = parse_attachment("006690_0531.txt", subject="ordinary subject", default_year=2026)
        self.assertEqual(parsed["normalized_mast_id"], "6690")
        self.assertEqual(parsed["data_date"], "2026-05-31")

        parsed = parse_attachment("data.rar", subject="hu nan yi yang 160m 6690 5月31日", default_year=2026)
        self.assertEqual(parsed["normalized_mast_id"], "6690")
        self.assertEqual(parsed["data_date"], "2026-05-31")

    def test_parse_historical_date_from_attachment_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "006690_data.txt"
            path.write_text("Time,Speed\n2026/05/31 00:10,5.2\n", encoding="utf-8")
            parsed = parse_attachment("006690_data.txt", path, subject="ordinary subject", default_year=2026)
            self.assertEqual(parsed["normalized_mast_id"], "6690")
            self.assertEqual(parsed["data_date"], "2026-05-31")

    def test_message_matches_six_digit_attachment_prefix_without_keyword(self) -> None:
        mail = MailMessage(
            email_uid="u1",
            subject="ordinary subject",
            sender_name="",
            sender_email="nrgdata4@nrg.com.cn",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("006690_20260710.txt", b"data")],
        )
        config = {
            "filter": {
                "allowed_senders": ["nrgdata4@nrg.com.cn"],
                "subject_keywords": ["6690"],
            }
        }
        self.assertTrue(_message_matches(mail, config))

    def test_sent_folder_mail_bypasses_inbox_sender_filter(self) -> None:
        mail = MailMessage(
            email_uid="Sent Messages:1",
            subject="ordinary subject",
            sender_name="",
            sender_email="monitor@qq.com",
            received_time=datetime(2026, 7, 16, 8, 0, 0),
            attachments=[("0908820260716m10.swift", b"data")],
            source_folder="Sent Messages",
        )
        config = {
            "filter": {
                "allowed_senders": ["source@example.com"],
                "subject_keywords": ["unrelated keyword"],
            }
        }
        self.assertTrue(_message_matches(mail, config, date(2026, 7, 16)))

    def test_placeholder_filter_examples_do_not_block_mail(self) -> None:
        mail = MailMessage(
            email_uid="u1",
            subject="0010-HN-data",
            sender_name="",
            sender_email="adata@hsrxsteel.com",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("000010_20260712.rld", b"data")],
        )
        config = {
            "filter": {
                "allowed_senders": ["******@***.com"],
                "subject_keywords": ["塔号", "邮箱主题关键词"],
            }
        }
        self.assertTrue(_message_matches(mail, config, date(2026, 7, 12)))

    def test_mail_provider_defaults_for_supported_domains(self) -> None:
        cases = {
            "user@qq.com": ("imap.qq.com", "smtp.qq.com", 465, False),
            "user@foxmail.com": ("imap.qq.com", "smtp.qq.com", 465, False),
            "user@163.com": ("imap.163.com", "smtp.163.com", 465, False),
            "user@126.com": ("imap.126.com", "smtp.126.com", 465, False),
            "user@gmail.com": ("imap.gmail.com", "smtp.gmail.com", 465, False),
            "user@outlook.com": ("outlook.office365.com", "smtp-mail.outlook.com", 587, True),
        }
        for account, expected in cases.items():
            with self.subTest(account=account):
                mail_cfg = {"email_account": account, "imap_server": "old", "smtp_server": "old"}
                apply_mail_provider_defaults(mail_cfg)
                self.assertEqual(mail_cfg["imap_server"], expected[0])
                self.assertEqual(mail_cfg["smtp_server"], expected[1])
                self.assertEqual(mail_cfg["smtp_port"], expected[2])
                self.assertEqual(mail_cfg["smtp_starttls"], expected[3])
                self.assertIsNotNone(provider_for_account(account))

    def test_config_example_keeps_mail_credentials_blank(self) -> None:
        text = Path("config/config.example.yaml").read_text(encoding="utf-8")
        self.assertIn('email_account: ""', text)
        self.assertIn('email_auth_code: ""', text)
        self.assertIn('type: "auto"', text)
        self.assertNotIn("15274958341", text)
        self.assertNotIn("secret-auth-code", text)

    @patch("src.mail_client.imaplib.IMAP4_SSL")
    def test_imap_search_passes_date_criteria_as_separate_arguments(self, imap_ssl: MagicMock) -> None:
        client = imap_ssl.return_value
        client.login.return_value = ("OK", [])
        client.select.return_value = ("OK", [b"1"])
        client.search.return_value = ("OK", [b""])
        client.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "Sent Messages"',
            ],
        )
        client._simple_command.return_value = ("OK", [])
        client.logout.return_value = ("BYE", [])
        config = {
            "mail": {
                "email_account": "user@qq.com",
                "email_auth_code": "auth-code",
            },
            "filter": {"allowed_senders": [], "subject_keywords": [], "attachment_extensions": []},
        }

        run_date = date.today() - timedelta(days=1)
        _fetch_once(config, run_date, MagicMock())

        self.assertEqual(client.search.call_count, 2)
        client.search.assert_any_call(
            None,
            "SINCE",
            _imap_date(run_date),
            "BEFORE",
            _imap_date(run_date + timedelta(days=2)),
        )
        client.select.assert_any_call("INBOX", readonly=True)
        client.select.assert_any_call("Sent Messages", readonly=True)
        imap_ssl.assert_called_once_with("imap.qq.com", 993, timeout=60)

    def test_sent_mailbox_discovery_uses_flag_and_common_names(self) -> None:
        client = MagicMock()
        client.list.return_value = (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Sent) "/" "Sent Items"',
            ],
        )
        self.assertEqual(_mailboxes_to_scan(client, MagicMock()), ["INBOX", "Sent Items"])

    def test_late_historical_mail_requires_explicit_stat_date(self) -> None:
        config = {
            "filter": {
                "allowed_senders": ["nrgdata4@nrg.com.cn"],
                "subject_keywords": ["6690"],
            }
        }
        dated_mail = MailMessage(
            email_uid="u1",
            subject="ordinary subject",
            sender_name="",
            sender_email="nrgdata4@nrg.com.cn",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("006690_20260601.txt", b"data")],
        )
        undated_mail = MailMessage(
            email_uid="u2",
            subject="ordinary subject",
            sender_name="",
            sender_email="nrgdata4@nrg.com.cn",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("006690_data.txt", b"data")],
        )
        self.assertTrue(_message_matches(dated_mail, config, date(2026, 6, 1)))
        self.assertFalse(_message_matches(undated_mail, config, date(2026, 6, 1)))

        month_day_mail = MailMessage(
            email_uid="u3",
            subject="hu nan yi yang 160m 6690 5月31日",
            sender_name="",
            sender_email="nrgdata4@nrg.com.cn",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("006690_data.txt", b"data")],
        )
        self.assertTrue(_message_matches(month_day_mail, config, date(2026, 5, 31)))

        content_dated_mail = MailMessage(
            email_uid="u4",
            subject="ordinary subject",
            sender_name="",
            sender_email="nrgdata4@nrg.com.cn",
            received_time=datetime(2026, 7, 12, 8, 0, 0),
            attachments=[("006690_data.txt", b"Time,Speed\n2026/04/30 00:10,5.2\n")],
        )
        self.assertTrue(_message_matches(content_dated_mail, config, date(2026, 4, 30)))

    def test_historical_stat_date_searches_until_today(self) -> None:
        self.assertEqual(
            _search_before_date(date(2026, 6, 1), today=date(2026, 7, 12)),
            date(2026, 7, 13),
        )
        self.assertEqual(
            _search_before_date(date(2026, 7, 11), today=date(2026, 7, 12)),
            date(2026, 7, 13),
        )

    def test_continuous_missing_days_increment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            db.upsert_daily_status([
                DailyStatusRow("2026-04-15", "6691", "6691", 0, 0, 0, 0, 1, 1, "missing 1 day", 0)
            ])
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 4, 16),
                SilentLogger(),
            )
            self.assertEqual(result.missing_rows[0]["continuous_missing_days"], 2)
            self.assertEqual(len(result.continuous_missing_rows), 1)

    def test_missing_data_uses_historical_masts_on_first_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            conn = db.connect()
            try:
                conn.execute(
                    """
                    insert into attachment_records (
                        email_uid, subject, sender_email, raw_device_code, normalized_mast_id, display_name,
                        filename, file_path, file_extension, file_size_bytes, file_size_kb, email_received_date,
                        attachment_date, data_date, size_status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "u1",
                        "0010-HN-data",
                        "adata@hsrxsteel.com",
                        "0010",
                        "10",
                        "10#测风塔",
                        "000010_20260711.rld",
                        str(Path(tmp) / "data" / "2026-07-11" / "10" / "000010_20260711.rld"),
                        ".rld",
                        249169,
                        243.33,
                        "2026-07-11",
                        "",
                        "2026-07-11",
                        "正常",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            first = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 12),
                SilentLogger(),
            )
            second = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 12),
                SilentLogger(),
            )
            self.assertEqual([row["normalized_mast_id"] for row in first.missing_rows], ["10"])
            self.assertEqual(first.missing_rows, second.missing_rows)

    def test_attachment_rows_include_next_day_generic_mail_for_stat_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            conn = db.connect()
            try:
                conn.execute(
                    """
                    insert into attachment_records (
                        email_uid, subject, sender_email, raw_device_code, normalized_mast_id, display_name,
                        filename, file_path, file_extension, file_size_bytes, file_size_kb, email_received_date,
                        attachment_date, data_date, size_status
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "u1",
                        "hu nan yi yang yuan jiang 160m 6690",
                        "nrgdata4@nrg.com.cn",
                        "6690",
                        "6690",
                        "6690",
                        "data.rar",
                        str(Path(tmp) / "data.rar"),
                        ".rar",
                        40960,
                        40.0,
                        "2026-07-11",
                        "",
                        "",
                        "姝ｅ父",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            rows = db.attachment_rows_for_date("2026-07-10")
            self.assertEqual([row["normalized_mast_id"] for row in rows], ["6690"])
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 10),
                SilentLogger(),
            )
            self.assertEqual([row["normalized_mast_id"] for row in result.received_rows], ["6690"])

    def test_attachment_rows_deduplicate_repeated_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            conn = db.connect()
            try:
                for index in range(3):
                    conn.execute(
                        """
                        insert into attachment_records (
                            email_uid, subject, sender_email, raw_device_code, normalized_mast_id, display_name,
                            filename, file_path, file_extension, file_size_bytes, file_size_kb, email_received_date,
                            attachment_date, data_date, size_status
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"u{index}",
                            "0010-HN-data",
                            "adata@hsrxsteel.com",
                            "0010",
                            "10",
                            "10#测风塔",
                            "000010_20260711.rld",
                            str(Path(tmp) / "data" / "2026-07-11" / "10" / f"000010_20260711_{index}.rld"),
                            ".rld",
                            249169,
                            243.33,
                            "2026-07-11",
                            "",
                            "2026-07-11",
                            "正常",
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            rows = db.attachment_rows_for_date("2026-07-11")
            self.assertEqual(len(rows), 1)
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 11),
                SilentLogger(),
            )
            self.assertEqual(result.received_rows[0]["attachment_count"], 1)

    def test_save_attachments_reuses_existing_same_content_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = {
                "storage": {"data_dir": "data"},
                "rules": {"file_size_warning_kb": 1},
            }
            mail = MailMessage(
                email_uid="u1",
                subject="0010-HN-data",
                sender_name="",
                sender_email="adata@hsrxsteel.com",
                received_time=datetime(2026, 7, 11, 8, 0, 0),
                attachments=[("000010_20260711.rld", b"same-content")],
            )

            first = save_attachments(base, config, [mail], date(2026, 7, 11), SilentLogger())
            second = save_attachments(base, config, [mail], date(2026, 7, 11), SilentLogger())

            self.assertEqual(first[0].attachment.file_path, second[0].attachment.file_path)
            self.assertEqual(len(list((base / "data" / "2026-07-11" / "10").glob("*.rld"))), 1)

    def test_invalid_mast_attachment_is_not_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = {
                "storage": {"data_dir": "data"},
                "rules": {"file_size_warning_kb": 20},
                "filter": {"invalid_mast_ids": ["009357"]},
            }
            mail = MailMessage(
                email_uid="u1",
                subject="9357 wind data",
                sender_name="",
                sender_email="source@example.com",
                received_time=datetime(2026, 7, 16, 8, 0, 0),
                attachments=[("009357_2026-07-16_00.00_1.rld", b"wind-data")],
            )

            saved = save_attachments(base, config, [mail], date(2026, 7, 16), SilentLogger())

            self.assertEqual(saved, [])
            self.assertFalse((base / "data" / "2026-07-16" / "9357").exists())

    def test_invalid_mast_is_excluded_from_all_daily_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()

            def attachment(uid: str, stat: str, mast_id: str, size_kb: float) -> AttachmentRecord:
                raw_code = mast_id.zfill(6)
                filename = f"{raw_code}_{stat}_00.00_1.rld"
                return AttachmentRecord(
                    uid,
                    "wind data",
                    "source@example.com",
                    raw_code,
                    mast_id,
                    f"{mast_id}#测风塔",
                    filename,
                    str(Path(tmp) / stat / filename),
                    ".rld",
                    int(size_kb * 1024),
                    size_kb,
                    stat,
                    "",
                    stat,
                    "正常" if size_kb >= 20 else "文件小于 20 KB",
                )

            db.upsert_attachment_records(
                [
                    attachment("old-invalid", "2026-07-15", "9357", 100),
                    attachment("today-invalid", "2026-07-16", "9357", 10),
                    attachment("today-valid", "2026-07-16", "9088", 40),
                ]
            )

            result = calculate_daily_status(
                db,
                {
                    "filter": {"invalid_mast_ids": ["009357"]},
                    "rules": {
                        "file_size_warning_kb": 20,
                        "historical_size_warning_ratio": 0.8,
                        "continuous_missing_warning_days": 2,
                    },
                },
                date(2026, 7, 16),
                SilentLogger(),
            )

            self.assertEqual([row["normalized_mast_id"] for row in result.received_rows], ["9088"])
            self.assertEqual(result.missing_rows, [])
            self.assertEqual(result.continuous_missing_rows, [])
            self.assertEqual(result.size_warning_rows, [])
            self.assertNotIn("9357", {row.get("normalized_mast_id") for row in result.attachment_rows})

    def test_size_warning_uses_fixed_threshold_and_historical_average(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()

            def attachment(uid: str, stat: str, size_kb: float, filename: str) -> AttachmentRecord:
                return AttachmentRecord(
                    uid,
                    "wind data",
                    "source@example.com",
                    "009357",
                    "9357",
                    "9357#测风塔",
                    filename,
                    str(Path(tmp) / stat / filename),
                    ".rld",
                    int(size_kb * 1024),
                    size_kb,
                    stat,
                    "",
                    stat,
                    "正常" if size_kb >= 20 else "文件小于 20 KB",
                )

            db.upsert_attachment_records(
                [
                    attachment("h1", "2026-07-14", 100, "009357_2026-07-14_00.00_1.rld"),
                    attachment("h2", "2026-07-15", 120, "009357_2026-07-15_00.00_1.rld"),
                    attachment("bad-history", "2026-07-15", 10, "009357_2026-07-15_00.00_2.rld"),
                    attachment("today", "2026-07-16", 80, "009357_2026-07-16_00.00_1.rld"),
                ]
            )

            result = calculate_daily_status(
                db,
                {
                    "rules": {
                        "file_size_warning_kb": 20,
                        "historical_size_warning_ratio": 0.8,
                        "continuous_missing_warning_days": 2,
                    }
                },
                date(2026, 7, 16),
                SilentLogger(),
            )

            self.assertEqual(len(result.size_warning_rows), 1)
            warning = result.size_warning_rows[0]
            self.assertEqual(warning["historical_average_size_kb"], 110.0)
            self.assertEqual(warning["historical_size_threshold_kb"], 88.0)
            self.assertIn("80%", warning["size_status"])

    def test_generate_xlsx_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 6),
                SilentLogger(),
            )
            xlsx = generate_xlsx_report(Path(tmp), date(2026, 7, 6), result, SilentLogger())
            with zipfile.ZipFile(xlsx) as archive:
                self.assertIn("xl/workbook.xml", archive.namelist())
                self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())

    def test_reports_include_license_watermark_without_machine_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 7, 6),
                SilentLogger(),
            )
            payload = {
                "customer_name": "Customer A",
                "license_id": "WM-2026-0001",
                "edition": "standard",
                "machine_hash": "8e32285c" + "0" * 56,
            }
            xlsx = generate_xlsx_report(Path(tmp), date(2026, 7, 6), result, SilentLogger(), license_payload=payload)
            html = generate_html_report(Path(tmp), date(2026, 7, 6), result, SilentLogger(), license_payload=payload)

            html_text = html.read_text(encoding="utf-8")
            self.assertIn("Customer A", html_text)
            self.assertIn("WM-2026-0001", html_text)
            self.assertNotIn(payload["machine_hash"], html_text)

            with zipfile.ZipFile(xlsx) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("Customer A", sheet)
            self.assertIn("WM-2026-0001", sheet)
            self.assertNotIn(payload["machine_hash"], sheet)

    def test_email_watermark_text_omits_sensitive_machine_fields(self) -> None:
        payload = {
            "customer_name": "Customer A",
            "license_id": "WM-2026-0001",
            "edition": "standard",
            "machine_hash": "secret-machine-hash",
            "email_auth_code": "secret-auth-code",
        }
        text = watermark_text(payload)
        self.assertIn("Customer A", text)
        self.assertIn("WM-2026-0001", text)
        self.assertNotIn("secret-machine-hash", text)
        self.assertNotIn("secret-auth-code", text)

    def test_license_baseline_contract(self) -> None:
        self.assertEqual(APP_VERSION, "1.4.0")
        self.assertEqual(PRODUCT_CODE, "wind_mail_monitor")
        requirement = LicenseRequirement(LicenseCheckPoint.GUI_STARTUP, "mail_monitor")
        self.assertIsNone(require_valid_license(requirement))

    def test_license_audit_log_omits_sensitive_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            append_license_audit_event(
                root,
                "license_check_failed",
                {
                    "license_id": "WM-2026-0001",
                    "machine_hash": "secret-machine-hash",
                    "email_auth_code": "secret-auth-code",
                },
            )
            text = (root / "logs" / "license_audit.log").read_text(encoding="utf-8")
            self.assertIn("WM-2026-0001", text)
            self.assertNotIn("secret-machine-hash", text)
            self.assertNotIn("secret-auth-code", text)

    def test_machine_code_is_stable_from_hash(self) -> None:
        digest = "8e32285cabcd" + "0" * 52
        self.assertEqual(_short_machine_code(digest), "WMPC-8E32-285C")
        self.assertEqual(_normalize(" to be filled by o.e.m. "), "")
        self.assertEqual(_normalize(" abc-123 "), "ABC-123")

    def test_build_and_export_license_request(self) -> None:
        fingerprint = MachineFingerprint(
            machine_hash="8e32285c" + "0" * 56,
            machine_code="WMPC-8E32-285C",
            components={"machine_guid": "A", "bios_uuid": "B"},
            device_name="DESKTOP-TEST",
            windows_version="Windows Test",
        )
        request = build_license_request("娴嬭瘯瀹㈡埛", fingerprint)
        self.assertEqual(request["product_code"], PRODUCT_CODE)
        self.assertEqual(request["machine_code"], "WMPC-8E32-285C")
        self.assertEqual(request["fingerprint_components"], ["bios_uuid", "machine_guid"])
        self.assertNotIn("email_auth_code", request)

        with tempfile.TemporaryDirectory() as tmp:
            path = export_license_request("娴嬭瘯瀹㈡埛", Path(tmp), fingerprint)
            self.assertEqual(path.suffix, ".req")
            self.assertIn("WMPC-8E32-285C", path.name)
            self.assertIn("娴嬭瘯瀹㈡埛", path.read_text(encoding="utf-8"))

    def test_build_license_change_request_carries_previous_license_fields(self) -> None:
        fingerprint = MachineFingerprint(
            machine_hash="8e32285c" + "0" * 56,
            machine_code="WMPC-8E32-285C",
            components={"machine_guid": "A", "bios_uuid": "B"},
            device_name="DESKTOP-TEST",
            windows_version="Windows Test",
        )
        payload = {
            "license_id": "WM-2026-0001",
            "customer_code": "CUS-2026-0001",
            "edition": "standard",
            "max_mailboxes": 1,
            "effective_date": "2026-07-11",
            "expiry_date": "2027-07-10",
        }
        request = build_license_change_request("Customer A", "upgrade", payload, fingerprint)
        self.assertEqual(request["request_type"], "upgrade")
        self.assertEqual(request["previous_license_id"], "WM-2026-0001")
        self.assertEqual(request["previous_edition"], "standard")
        self.assertEqual(request["previous_expiry_date"], "2027-07-10")
        self.assertNotIn("email_auth_code", request)

    def test_ed25519_rfc8032_test_vector_1(self) -> None:
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        expected_public = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        expected_signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a"
            "84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46b"
            "d25bf5f0595bbe24655141438e7a100b"
        )
        self.assertEqual(publickey(seed), expected_public)
        self.assertEqual(sign(seed, b""), expected_signature)
        self.assertTrue(verify(expected_public, b"", expected_signature))
        self.assertFalse(verify(expected_public, b"x", expected_signature))

    def test_issue_license_and_validate_signature(self) -> None:
        keys = _test_keypair()
        license_data = _issue_test_license(
            private_seed_b64=keys["private_seed_b64"],
            license_id="WM-2026-0001",
            customer_code="CUS-2026-0001",
            customer_name="娴嬭瘯瀹㈡埛",
            machine_hash="8e32285c" + "0" * 56,
            machine_code="WMPC-8E32-285C",
            issue_date=date(2026, 7, 11),
            effective_date=date(2026, 7, 11),
            expiry_date=date(2027, 7, 10),
        )
        payload = validate_signed_license(license_data, keys["public_key_b64"])
        self.assertEqual(payload["license_id"], "WM-2026-0001")

        tampered = dict(license_data)
        tampered["payload"] = dict(license_data["payload"])
        tampered["payload"]["customer_name"] = "绡℃敼瀹㈡埛"
        with self.assertRaises(Exception):
            validate_signed_license(tampered, keys["public_key_b64"])

        bad_signature = dict(license_data)
        raw_signature = bytearray(base64.b64decode(bad_signature["signature"]))
        raw_signature[0] ^= 1
        bad_signature["signature"] = base64.b64encode(raw_signature).decode("ascii")
        with self.assertRaises(Exception):
            validate_signed_license(bad_signature, keys["public_key_b64"])

    def test_license_manager_blocks_without_license(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_path = os.environ.get("WIND_MAIL_LICENSE_PATH")
            os.environ["WIND_MAIL_LICENSE_PATH"] = str(Path(tmp) / "missing.lic")
            try:
                with self.assertRaises(Exception):
                    require_valid_license(LicenseRequirement(LicenseCheckPoint.CLI_STARTUP, "mail_monitor"), Path(tmp))
            finally:
                if old_path is None:
                    os.environ.pop("WIND_MAIL_LICENSE_PATH", None)
                else:
                    os.environ["WIND_MAIL_LICENSE_PATH"] = old_path

    def test_imported_license_allows_required_feature_and_blocks_missing_feature(self) -> None:
        keys = _test_keypair()
        old_public = license_manager.PUBLIC_KEY_B64
        old_path = os.environ.get("WIND_MAIL_LICENSE_PATH")
        fp = get_machine_fingerprint()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["WIND_MAIL_LICENSE_PATH"] = str(root / "installed.lic")
            license_data = _issue_test_license(
                private_seed_b64=keys["private_seed_b64"],
                license_id="WM-2026-0002",
                customer_code="CUS-2026-0002",
                customer_name="娴嬭瘯瀹㈡埛",
                machine_hash=fp.machine_hash,
                machine_code=fp.machine_code,
                issue_date=date(2026, 7, 11),
                effective_date=date(2026, 7, 11),
                expiry_date=date(2027, 7, 10),
                features=["mail_monitor"],
            )
            source = root / "source.lic"
            source.write_text(json.dumps(license_data, ensure_ascii=False), encoding="utf-8")
            try:
                license_manager.PUBLIC_KEY_B64 = keys["public_key_b64"]
                status = license_manager.import_and_validate_license(source, root)
                self.assertTrue(status.ok)
                require_valid_license(LicenseRequirement(LicenseCheckPoint.MAIL_READ, "mail_monitor"), root)
                require_valid_license(LicenseRequirement(LicenseCheckPoint.CLI_STARTUP, PRODUCT_CODE), root)
                with self.assertRaises(Exception):
                    require_valid_license(LicenseRequirement(LicenseCheckPoint.EMAIL_REPORT, "email_report"), root)
            finally:
                license_manager.PUBLIC_KEY_B64 = old_public
                if old_path is None:
                    os.environ.pop("WIND_MAIL_LICENSE_PATH", None)
                else:
                    os.environ["WIND_MAIL_LICENSE_PATH"] = old_path

    def test_time_guard_warns_and_blocks_rollback(self) -> None:
        payload = {"license_id": "WM-2026-0001", "machine_hash": "abc"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = datetime(2026, 7, 11, 12, 0, 0)
            self.assertEqual(check_and_update_time_state(root, payload, first).warning, "")
            warning = check_and_update_time_state(root, payload, first - timedelta(hours=13))
            self.assertTrue(warning.warning)
            with self.assertRaises(Exception):
                check_and_update_time_state(root, payload, first - timedelta(hours=25))

    def test_license_status_warns_before_expiry(self) -> None:
        keys = _test_keypair()
        old_public = license_manager.PUBLIC_KEY_B64
        old_path = os.environ.get("WIND_MAIL_LICENSE_PATH")
        fp = get_machine_fingerprint()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["WIND_MAIL_LICENSE_PATH"] = str(root / "installed.lic")
            license_data = _issue_test_license(
                private_seed_b64=keys["private_seed_b64"],
                license_id="WM-2026-0003",
                customer_code="CUS-2026-0003",
                customer_name="Customer A",
                machine_hash=fp.machine_hash,
                machine_code=fp.machine_code,
                issue_date=date.today(),
                effective_date=date.today(),
                expiry_date=date.today() + timedelta(days=6),
            )
            source = root / "source.lic"
            source.write_text(json.dumps(license_data, ensure_ascii=False), encoding="utf-8")
            try:
                license_manager.PUBLIC_KEY_B64 = keys["public_key_b64"]
                status = license_manager.import_and_validate_license(source, root)
                self.assertTrue(status.ok)
                self.assertEqual(status.days_remaining, 6)
                self.assertTrue(status.warning)
            finally:
                license_manager.PUBLIC_KEY_B64 = old_public
                if old_path is None:
                    os.environ.pop("WIND_MAIL_LICENSE_PATH", None)
                else:
                    os.environ["WIND_MAIL_LICENSE_PATH"] = old_path


if __name__ == "__main__":
    unittest.main()
