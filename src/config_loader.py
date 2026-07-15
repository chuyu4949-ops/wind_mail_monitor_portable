from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("[]", ""):
        return [] if value == "[]" else ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")

    raw_lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, raw_line in enumerate(raw_lines):
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        if line.startswith("- "):
            current = stack[-1][1]
            if isinstance(current, list):
                current.append(_parse_scalar(line[2:]))
            continue

        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            current[key] = [] if _next_is_list(raw_lines, index, indent) else {}
            stack.append((indent, current[key]))
            continue
        current[key] = _parse_scalar(value)

    _apply_defaults(root)
    return root


def _next_is_list(lines: list[str], index: int, indent: int) -> bool:
    for next_line in lines[index + 1:]:
        next_indent = len(next_line) - len(next_line.lstrip(" "))
        if next_indent <= indent:
            return False
        return next_line.strip().startswith("- ")
    return False


def _apply_defaults(config: dict[str, Any]) -> None:
    config.setdefault("mail", {})
    config.setdefault("filter", {})
    config.setdefault("rules", {})
    config.setdefault("report", {})
    config.setdefault("storage", {})

    config["mail"].setdefault("email_account", "")
    config["mail"].setdefault("email_auth_code", "")
    config["mail"].setdefault("imap_server", "")
    config["mail"].setdefault("smtp_server", "")
    config["mail"].setdefault("imap_port", 993)
    config["mail"].setdefault("smtp_port", 465)
    config["mail"].setdefault("use_ssl", True)
    config["mail"].setdefault("smtp_starttls", False)
    config["mail"].setdefault("type", "auto")
    config["filter"].setdefault("allowed_senders", [])
    config["filter"].setdefault("subject_keywords", [])
    config["filter"].setdefault("attachment_extensions", [".rld", ".zip"])
    config["rules"].setdefault("file_size_warning_kb", 20)
    config["report"]["report_receivers"] = _as_list(config["report"].get("report_receivers", []))
    config["report"]["report_cc"] = _as_list(config["report"].get("report_cc", []))
    config["report"].setdefault("send_email", True)
    config["storage"].setdefault("data_dir", "./data")
    config["storage"].setdefault("report_dir", "./reports")
    config["storage"].setdefault("log_dir", "./logs")
    config["storage"].setdefault("database_path", "./database/wind_mail_monitor.db")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict) or value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]
