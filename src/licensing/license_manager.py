from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path

from .audit_log import append_license_audit_event
from .errors import LicensingError
from .license_storage import import_license_file, load_license_data
from .license_validator import validate_license_for_machine
from .public_key import PUBLIC_KEY_B64
from .time_guard import check_and_update_time_state


class LicenseCheckPoint(str, Enum):
    GUI_STARTUP = "gui_startup"
    CLI_STARTUP = "cli_startup"
    MANUAL_REPORT_RUN = "manual_report_run"
    MAIL_READ = "mail_read"
    ATTACHMENT_DOWNLOAD = "attachment_download"
    EXCEL_REPORT = "excel_report"
    HTML_REPORT = "html_report"
    EMAIL_REPORT = "email_report"


@dataclass(frozen=True)
class LicenseRequirement:
    checkpoint: LicenseCheckPoint
    required_feature: str | None = None


@dataclass(frozen=True)
class LicenseStatus:
    ok: bool
    message: str
    payload: dict | None = None
    license_path: Path | None = None
    days_remaining: int | None = None
    warning: str = ""


def infer_base_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()


def get_license_status(base_dir: Path | None = None, required_feature: str | None = None) -> LicenseStatus:
    root = base_dir or infer_base_dir()
    try:
        license_data, path = load_license_data(root)
        payload = validate_license_for_machine(license_data, PUBLIC_KEY_B64, required_feature=required_feature)
        time_result = check_and_update_time_state(root, payload)
        expiry = date.fromisoformat(str(payload["expiry_date"]))
        days_remaining = (expiry - date.today()).days
        warning = time_result.warning or _expiry_warning(days_remaining)
        message = "许可证有效" if not warning else f"许可证有效，{warning}"
        return LicenseStatus(True, message, payload, path, days_remaining, warning)
    except Exception as exc:
        return LicenseStatus(False, str(exc), None, None, None, "")


def require_valid_license(requirement: LicenseRequirement, base_dir: Path | None = None) -> None:
    if requirement.checkpoint == LicenseCheckPoint.GUI_STARTUP:
        return
    root = base_dir or infer_base_dir()
    status = get_license_status(root, requirement.required_feature)
    if not status.ok:
        append_license_audit_event(
            root,
            "license_check_failed",
            {
                "checkpoint": requirement.checkpoint.value,
                "required_feature": requirement.required_feature,
                "message": status.message,
            },
        )
        raise LicensingError(f"授权检查失败：{status.message}")
    append_license_audit_event(
        root,
        "license_check_passed",
        {
            "checkpoint": requirement.checkpoint.value,
            "required_feature": requirement.required_feature,
            "license_id": (status.payload or {}).get("license_id"),
            "customer_name": (status.payload or {}).get("customer_name"),
            "edition": (status.payload or {}).get("edition"),
            "days_remaining": status.days_remaining,
            "warning": status.warning,
        },
    )


def import_and_validate_license(source_path: Path, base_dir: Path | None = None) -> LicenseStatus:
    root = base_dir or infer_base_dir()
    try:
        license_data = json.loads(source_path.read_text(encoding="utf-8"))
        payload = validate_license_for_machine(license_data, PUBLIC_KEY_B64)
        import_license_file(source_path, root)
        status = get_license_status(root)
        append_license_audit_event(
            root,
            "license_import_passed",
            {
                "license_id": payload.get("license_id"),
                "customer_name": payload.get("customer_name"),
                "edition": payload.get("edition"),
                "expiry_date": payload.get("expiry_date"),
            },
        )
        return status
    except Exception as exc:
        append_license_audit_event(root, "license_import_failed", {"message": str(exc)})
        raise


def _expiry_warning(days_remaining: int) -> str:
    if days_remaining <= 7:
        return f"强提醒：许可证将在 {days_remaining} 天后到期，请尽快续期。"
    if days_remaining <= 30:
        return f"许可证将在 {days_remaining} 天后到期，请准备续期。"
    return ""
