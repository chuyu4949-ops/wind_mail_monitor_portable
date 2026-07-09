from __future__ import annotations

import sqlite3
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path

from src.database import Database
from src.mast_parser import parse_attachment
from src.models import DailyStatusRow
from src.report_generator import generate_xlsx_report
from src.rules import calculate_daily_status


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

    def test_continuous_missing_days_increment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.initialize()
            db.upsert_daily_status([
                DailyStatusRow("2026-04-15", "6691", "6691#测风塔", 0, 0, 0, 0, 1, 1, "缺失 1 天", 0)
            ])
            result = calculate_daily_status(
                db,
                {"rules": {"continuous_missing_warning_days": 2}},
                date(2026, 4, 16),
                SilentLogger(),
            )
            self.assertEqual(result.missing_rows[0]["continuous_missing_days"], 2)
            self.assertEqual(result.continuous_missing_rows[0]["missing_status"], "连续缺失 2 天")

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


if __name__ == "__main__":
    unittest.main()
