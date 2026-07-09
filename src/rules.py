from __future__ import annotations

from datetime import date, timedelta
from logging import Logger

from .database import Database
from .models import DailyResult, DailyStatusRow


def calculate_daily_status(db: Database, config: dict, stat_date: date, logger: Logger) -> DailyResult:
    stat = stat_date.isoformat()
    previous = (stat_date - timedelta(days=1)).isoformat()
    today_attachments = db.attachment_rows_for_date(stat)
    yesterday_status = db.daily_rows_for_date(previous)

    warning_text_prefix = "文件小于"
    known_today = [r for r in today_attachments if r.get("normalized_mast_id")]
    unknown_rows = [r for r in today_attachments if not r.get("normalized_mast_id")]
    size_warning_rows = [r for r in today_attachments if r["size_status"] != "正常"]

    grouped: dict[str, list[dict]] = {}
    for row in known_today:
        grouped.setdefault(row["normalized_mast_id"], []).append(row)

    yesterday_map = {r["normalized_mast_id"]: r for r in yesterday_status if r.get("normalized_mast_id")}
    today_ids = set(grouped)
    carry_missing_ids = {
        mast_id for mast_id, row in yesterday_map.items()
        if int(row.get("missing_today") or 0) == 1 and mast_id not in today_ids
    }
    yesterday_received_ids = {
        mast_id for mast_id, row in yesterday_map.items()
        if int(row.get("received") or 0) == 1 and mast_id not in today_ids
    }
    missing_ids = yesterday_received_ids | carry_missing_ids

    status_rows: list[DailyStatusRow] = []
    received_rows: list[dict] = []
    for mast_id, rows in grouped.items():
        min_size = min(float(r["file_size_kb"]) for r in rows)
        has_warning = any(r["size_status"].startswith(warning_text_prefix) or r["size_status"] == "空文件异常" for r in rows)
        display_name = rows[0]["display_name"] or mast_id
        recovered = 1 if int(yesterday_map.get(mast_id, {}).get("missing_today") or 0) == 1 else 0
        status = "已恢复" if recovered else "正常"
        status_rows.append(DailyStatusRow(stat, mast_id, display_name, 1, len(rows), min_size, int(has_warning), 0, 0, status, recovered))
        received_rows.append({"normalized_mast_id": mast_id, "display_name": display_name, "attachment_count": len(rows), "min_file_size_kb": min_size})

    missing_rows: list[dict] = []
    continuous_missing_rows: list[dict] = []
    for mast_id in sorted(missing_ids):
        previous_row = yesterday_map.get(mast_id, {})
        days = int(previous_row.get("continuous_missing_days") or 0) + 1
        display_name = previous_row.get("display_name") or mast_id
        status = _missing_status(days)
        row = {
            "normalized_mast_id": mast_id,
            "display_name": display_name,
            "continuous_missing_days": days,
            "missing_status": status,
        }
        missing_rows.append(row)
        if days >= int(config["rules"].get("continuous_missing_warning_days", 2)):
            continuous_missing_rows.append(row)
        status_rows.append(DailyStatusRow(stat, mast_id, display_name, 0, 0, 0, 0, 1, days, status, 0))

    logger.info("识别测风塔 %s 座，今日缺失 %s 座，小文件异常 %s 个，未识别 %s 个", len(received_rows), len(missing_rows), len(size_warning_rows), len(unknown_rows))
    return DailyResult(stat, received_rows, missing_rows, continuous_missing_rows, size_warning_rows, today_attachments, unknown_rows, status_rows)


def _missing_status(days: int) -> str:
    if days <= 1:
        return "缺失 1 天"
    if days == 2:
        return "连续缺失 2 天"
    return f"连续缺失 {days} 天"
