from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from src.attachment_downloader import save_attachments
from src.app_constants import PRODUCT_CODE, PRODUCT_NAME
from src.config_loader import load_config
from src.database import Database
from src.email_sender import send_report_email
from src.licensing import LicenseCheckPoint, LicenseRequirement, get_license_status, require_valid_license
from src.logger import setup_logger
from src.mail_client import fetch_messages
from src.report_generator import generate_html_report, generate_xlsx_report
from src.rules import calculate_daily_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=PRODUCT_NAME)
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--date", help="统计日期，格式 YYYY-MM-DD；默认取运行日前一天")
    parser.add_argument("--no-send", action="store_true", help="只生成本地日报，不发送邮件")
    parser.add_argument("--skip-mail", action="store_true", help="不连接邮箱，仅基于数据库生成日报")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    require_valid_license(
        LicenseRequirement(
            LicenseCheckPoint.CLI_STARTUP,
            required_feature=PRODUCT_CODE,
        ),
        base_dir,
    )
    license_payload = get_license_status(base_dir, PRODUCT_CODE).payload or {}
    config = load_config(base_dir / args.config)
    stat_date = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)

    storage = config["storage"]
    logger = setup_logger(base_dir / storage["log_dir"])
    logger.info("程序启动，统计日期：%s", stat_date.isoformat())

    for key in ("data_dir", "report_dir", "log_dir"):
        (base_dir / storage[key]).mkdir(parents=True, exist_ok=True)
    (base_dir / Path(storage["database_path"]).parent).mkdir(parents=True, exist_ok=True)

    db = Database(base_dir / storage["database_path"])
    db.initialize()

    if not args.skip_mail:
        require_valid_license(LicenseRequirement(LicenseCheckPoint.MAIL_READ, "mail_monitor"), base_dir)
        messages = fetch_messages(config, stat_date, logger)
        require_valid_license(LicenseRequirement(LicenseCheckPoint.ATTACHMENT_DOWNLOAD, "mail_monitor"), base_dir)
        records = save_attachments(base_dir, config, messages, stat_date, logger)
        db.upsert_email_records([record.email for record in records])
        db.upsert_attachment_records([record.attachment for record in records])
        logger.info("下载并记录附件 %s 个", len(records))
    else:
        logger.info("已跳过邮箱读取，仅生成数据库日报")

    daily_result = calculate_daily_status(db, config, stat_date, logger)
    db.upsert_daily_status(daily_result.status_rows)

    report_dir = base_dir / storage["report_dir"]
    require_valid_license(LicenseRequirement(LicenseCheckPoint.EXCEL_REPORT, "excel_report"), base_dir)
    xlsx_path = generate_xlsx_report(report_dir, stat_date, daily_result, logger, license_payload=license_payload)
    require_valid_license(LicenseRequirement(LicenseCheckPoint.HTML_REPORT, "html_report"), base_dir)
    html_path = generate_html_report(report_dir, stat_date, daily_result, logger, license_payload=license_payload)

    should_send = bool(config["report"].get("send_email", True)) and not args.no_send
    if should_send:
        require_valid_license(LicenseRequirement(LicenseCheckPoint.EMAIL_REPORT, "email_report"), base_dir)
        send_report_email(config, stat_date, html_path, xlsx_path, logger, license_payload=license_payload)
    else:
        logger.info("已跳过日报邮件发送")

    _write_runtime_status(
        base_dir,
        {
            "ok": True,
            "stat_date": stat_date.isoformat(),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "has_alert": bool(daily_result.missing_rows or daily_result.continuous_missing_rows or daily_result.size_warning_rows or daily_result.unknown_rows),
            "missing_count": len(daily_result.missing_rows),
            "continuous_missing_count": len(daily_result.continuous_missing_rows),
            "size_warning_count": len(daily_result.size_warning_rows),
            "unknown_count": len(daily_result.unknown_rows),
            "xlsx_path": str(xlsx_path),
            "html_path": str(html_path),
            "message": "任务完成",
        },
    )

    logger.info("任务完成，Excel：%s，HTML：%s", xlsx_path, html_path)
    print(f"任务完成：{stat_date.isoformat()}")
    print(f"Excel 日报：{xlsx_path}")
    print(f"HTML 日报：{html_path}")
    return 0


def _write_runtime_status(base_dir: Path, payload: dict) -> None:
    (base_dir / "runtime_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        _write_runtime_status(
            base,
            {
                "ok": False,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "has_alert": True,
                "message": str(exc),
            },
        )
        raise
