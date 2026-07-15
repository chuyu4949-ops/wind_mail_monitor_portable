from __future__ import annotations

import smtplib
from datetime import date
from email.message import EmailMessage
from logging import Logger
from pathlib import Path

from .licensing.license_watermark import watermark_text
from .mail_provider import apply_mail_provider_defaults, supported_provider_text


def send_report_email(config: dict, stat_date: date, html_path: Path, xlsx_path: Path, logger: Logger, license_payload: dict | None = None) -> None:
    mail_cfg = apply_mail_provider_defaults(config["mail"])
    receivers = _as_list(config["report"].get("report_receivers", []))
    cc = _as_list(config["report"].get("report_cc", []))
    if not receivers:
        raise RuntimeError("未配置日报接收人，请在“邮箱设置”中填写日报接收人。")

    msg = EmailMessage()
    msg["Subject"] = f"测风数据接收日报 - {stat_date.isoformat()}"
    msg["From"] = mail_cfg["email_account"]
    msg["To"] = ", ".join(receivers)
    if cc:
        msg["Cc"] = ", ".join(cc)
    text_body = "请使用支持 HTML 的邮件客户端查看测风数据接收日报。"
    license_text = watermark_text(license_payload)
    if license_text:
        text_body = f"{text_body}\n\n{license_text}"
    msg.set_content(text_body)
    msg.add_alternative(html_path.read_text(encoding="utf-8"), subtype="html")
    msg.add_attachment(
        xlsx_path.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx_path.name,
    )

    recipients = receivers + cc
    try:
        with _smtp_client(mail_cfg) as client:
            try:
                client.login(mail_cfg["email_account"], mail_cfg["email_auth_code"])
            except smtplib.SMTPAuthenticationError as exc:
                raise RuntimeError(_smtp_login_error_message(exc)) from exc
            client.send_message(msg, to_addrs=recipients)
        logger.info("日报邮件发送成功")
    except Exception as exc:
        logger.exception("日报邮件发送失败：%s", exc)
        raise


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict) or value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _smtp_client(mail_cfg: dict):
    host = mail_cfg["smtp_server"]
    port = int(mail_cfg["smtp_port"])
    if mail_cfg.get("smtp_starttls"):
        client = smtplib.SMTP(host, port, timeout=60)
        client.ehlo()
        client.starttls()
        client.ehlo()
        return client
    return smtplib.SMTP_SSL(host, port, timeout=60)


def _smtp_login_error_message(exc: smtplib.SMTPAuthenticationError) -> str:
    detail = exc.smtp_error
    if isinstance(detail, bytes):
        detail_text = detail.decode("utf-8", errors="replace")
    else:
        detail_text = str(detail)
    return (
        "日报邮件发送失败：SMTP 登录未通过邮箱验证。\n"
        f"请确认邮箱账号、客户端授权码/应用专用密码、SMTP 服务开关是否正确。当前支持自动识别：{supported_provider_text()}。\n"
        f"服务器返回：{exc.smtp_code} {detail_text}"
    )
