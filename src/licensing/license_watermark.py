from __future__ import annotations

from html import escape

from src.app_constants import APP_VERSION


WATERMARK_NOTICE = "This report is for the licensed organization internal use only."


def build_license_watermark(license_payload: dict | None) -> list[tuple[str, str]]:
    payload = license_payload or {}
    rows = [
        ("Authorized customer", str(payload.get("customer_name") or "")),
        ("License ID", str(payload.get("license_id") or "")),
        ("Edition", str(payload.get("edition") or "standard")),
        ("Software version", APP_VERSION),
        ("Notice", WATERMARK_NOTICE),
    ]
    return [(label, value) for label, value in rows if value]


def watermark_text(license_payload: dict | None) -> str:
    rows = build_license_watermark(license_payload)
    if not rows:
        return ""
    lines = ["Authorization watermark"]
    lines.extend(f"{label}: {value}" for label, value in rows)
    return "\n".join(lines)


def watermark_html(license_payload: dict | None) -> str:
    rows = build_license_watermark(license_payload)
    if not rows:
        return ""
    body = "".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )
    return (
        '<section class="license-watermark">'
        "<h3>Authorization watermark</h3>"
        f"<table><tbody>{body}</tbody></table>"
        "</section>"
    )


def watermark_xlsx_rows(license_payload: dict | None) -> list[list[str]]:
    rows = build_license_watermark(license_payload)
    if not rows:
        return []
    return [[""], ["Authorization watermark"]] + [[label, value] for label, value in rows]
