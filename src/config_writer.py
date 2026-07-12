from __future__ import annotations

from pathlib import Path
from typing import Any


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_config(config), encoding="utf-8")


def _dump_config(config: dict[str, Any]) -> str:
    lines: list[str] = []
    for section in ("mail", "filter", "rules", "report", "storage"):
        if section not in config:
            continue
        lines.append(f"{section}:")
        for key, value in config[section].items():
            _write_value(lines, key, value, 2)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_value(lines: list[str], key: str, value: Any, indent: int) -> None:
    prefix = " " * indent
    if isinstance(value, list):
        if value:
            lines.append(f"{prefix}{key}:")
            for item in value:
                lines.append(f"{prefix}  - {_format_scalar(item)}")
        else:
            lines.append(f"{prefix}{key}: []")
    elif isinstance(value, bool):
        lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
    else:
        lines.append(f"{prefix}{key}: {_format_scalar(value)}")


def _format_scalar(value: Any) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    text = "" if value is None else str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
