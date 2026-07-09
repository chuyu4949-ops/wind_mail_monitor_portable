from __future__ import annotations

import smtplib
from datetime import date
from email.message import EmailMessage
from logging import Logger
from pathlib import Path


def send_report_email(config: dict, stat_date: date, html_path: Path, xlsx_path: Path, logger: Logger) -> None:
    mail_cfg = config["mail"]
    receivers = config["report"].get("report_receivers", [])
    cc = config["report"].get("report_cc", [])
    if not receivers:
        raise RuntimeError("未配置日报接收人 report.report_receivers")

    msg = EmailMessage()
    msg["Subject"] = f"测风数据接收日报 - {stat_date.isoformat()}"
    msg["From"] = mail_cfg["email_account"]
    msg["To"] = ", ".join(receivers)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.set_content("请使用支持 HTML 的邮件客户端查看测风数据接收日报。")
    msg.add_alternative(html_path.read_text(encoding="utf-8"), subtype="html")
    msg.add_attachment(
        xlsx_path.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx_path.name,
    )

    recipients = receivers + cc
    try:
        with smtplib.SMTP_SSL(mail_cfg["smtp_server"], int(mail_cfg["smtp_port"])) as client:
            client.login(mail_cfg["email_account"], mail_cfg["email_auth_code"])
            client.send_message(msg, to_addrs=recipients)
        logger.info("日报邮件发送成功")
    except Exception as exc:
        logger.exception("日报邮件发送失败：%s", exc)
        raise
