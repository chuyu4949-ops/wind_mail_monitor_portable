from __future__ import annotations

from datetime import date, timedelta
from logging import Logger

from .database import Database
from .mast_parser import normalized_mast_id_set
from .models import DailyResult, DailyStatusRow


def calculate_daily_status(db: Database, config: dict, stat_date: date, logger: Logger) -> DailyResult:
    stat = stat_date.isoformat()
    previous = (stat_date - timedelta(days=1)).isoformat()
    invalid_mast_ids = normalized_mast_id_set(config.get("filter", {}).get("invalid_mast_ids", []))
    today_attachments = [
        row
        for row in db.attachment_rows_for_date(stat)
        if str(row.get("normalized_mast_id") or "") not in invalid_mast_ids
    ]
    fixed_warning_kb = float(config["rules"].get("file_size_warning_kb", 20))
    historical_ratio = float(config["rules"].get("historical_size_warning_ratio", 0.8))
    historical_averages = db.historical_average_sizes_before_date(stat, fixed_warning_kb)
    today_attachments = _apply_historical_size_warnings(
        today_attachments,
        historical_averages,
        fixed_warning_kb,
        historical_ratio,
    )
    yesterday_status = [
        row
        for row in db.daily_rows_for_date(previous)
        if str(row.get("normalized_mast_id") or "") not in invalid_mast_ids
    ]
    known_before_today = [
        row
        for row in db.known_masts_before_date(stat)
        if str(row.get("normalized_mast_id") or "") not in invalid_mast_ids
    ]

    normal_statuses = {"正常", "姝ｅ父"}
    warning_prefixes = ("文件小于", "鏂囦欢灏忎簬")
    empty_file_statuses = {"空文件异常", "绌烘枃浠跺紓甯?"}

    known_today = [r for r in today_attachments if r.get("normalized_mast_id")]
    unknown_rows = [r for r in today_attachments if not r.get("normalized_mast_id")]
    size_warning_rows = [r for r in today_attachments if r.get("size_status") not in normal_statuses]

    grouped: dict[str, list[dict]] = {}
    for row in known_today:
        grouped.setdefault(row["normalized_mast_id"], []).append(row)

    yesterday_map = {r["normalized_mast_id"]: r for r in yesterday_status if r.get("normalized_mast_id")}
    expected_display_names = {
        str(r["normalized_mast_id"]): (r.get("display_name") or str(r["normalized_mast_id"]))
        for r in known_before_today
        if r.get("normalized_mast_id")
    }
    for mast_id, row in yesterday_map.items():
        expected_display_names.setdefault(mast_id, row.get("display_name") or mast_id)

    today_ids = set(grouped)
    missing_ids = set(expected_display_names) - today_ids

    status_rows: list[DailyStatusRow] = []
    received_rows: list[dict] = []
    for mast_id, rows in grouped.items():
        min_size = min(float(r["file_size_kb"]) for r in rows)
        has_warning = any(
            str(r.get("size_status", "")).startswith(warning_prefixes) or r.get("size_status") in empty_file_statuses
            for r in rows
        )
        display_name = rows[0]["display_name"] or mast_id
        recovered = 1 if int(yesterday_map.get(mast_id, {}).get("missing_today") or 0) == 1 else 0
        status = "已恢复" if recovered else "正常"
        status_rows.append(DailyStatusRow(stat, mast_id, display_name, 1, len(rows), min_size, int(has_warning), 0, 0, status, recovered))
        received_rows.append({"normalized_mast_id": mast_id, "display_name": display_name, "attachment_count": len(rows), "min_file_size_kb": min_size})

    missing_rows: list[dict] = []
    continuous_missing_rows: list[dict] = []
    for mast_id in sorted(missing_ids):
        previous_row = yesterday_map.get(mast_id, {})
        previous_missing = int(previous_row.get("missing_today") or 0) == 1
        days = int(previous_row.get("continuous_missing_days") or 0) + 1 if previous_missing else 1
        display_name = previous_row.get("display_name") or expected_display_names.get(mast_id) or mast_id
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

    logger.info(
        "识别测风塔 %s 座，今日缺失 %s 座，文件大小异常 %s 个，未识别 %s 个，无效塔号 %s 个",
        len(received_rows),
        len(missing_rows),
        len(size_warning_rows),
        len(unknown_rows),
        len(invalid_mast_ids),
    )
    return DailyResult(stat, received_rows, missing_rows, continuous_missing_rows, size_warning_rows, today_attachments, unknown_rows, status_rows)


def _apply_historical_size_warnings(
    rows: list[dict],
    historical_averages: dict[str, float],
    fixed_warning_kb: float,
    ratio: float,
) -> list[dict]:
    updated: list[dict] = []
    ratio_percent = ratio * 100
    for original in rows:
        row = dict(original)
        mast_id = str(row.get("normalized_mast_id") or "")
        current_size = float(row.get("file_size_kb") or 0)
        average_size = historical_averages.get(mast_id)
        if average_size is not None:
            threshold = average_size * ratio
            row["historical_average_size_kb"] = round(average_size, 2)
            row["historical_size_threshold_kb"] = round(threshold, 2)
            if current_size >= fixed_warning_kb and current_size < threshold:
                row["size_status"] = (
                    f"低于历史平均值的 {ratio_percent:g}%"
                    f"（历史均值 {average_size:.2f} KB，阈值 {threshold:.2f} KB）"
                )
        updated.append(row)
    return updated


def _missing_status(days: int) -> str:
    if days <= 1:
        return "缺失 1 天"
    if days == 2:
        return "连续缺失 2 天"
    return f"连续缺失 {days} 天"
