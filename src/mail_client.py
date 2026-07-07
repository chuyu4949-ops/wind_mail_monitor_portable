from __future__ import annotations

import email
import imaplib
import time
from datetime import date, datetime, timedelta
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime
from logging import Logger

from .models import MailMessage


IMAP_ID = {
    "name": "wind-mail-monitor",
    "version": "1.0.1",
    "vendor": "Codex local app",
    "support-email": "support@example.com",
}


def fetch_messages(config: dict, stat_date: date, logger: Logger) -> list[MailMessage]:
    mail_cfg = config["mail"]
    account = mail_cfg.get("email_account", "")
    auth_code = mail_cfg.get("email_auth_code", "")
    if not account or account.startswith("请在本地填写") or not auth_code or auth_code.startswith("请在本地填写"):
        raise RuntimeError("请先在软件界面填写 163 邮箱账号和客户端授权码")

    for attempt in range(1, 4):
        try:
            return _fetch_once(config, stat_date, logger)
        except Exception as exc:
            logger.exception("邮件读取失败，第 %s 次：%s", attempt, exc)
            if attempt == 3:
                raise
            time.sleep(30)
    return []


def _fetch_once(config: dict, stat_date: date, logger: Logger) -> list[MailMessage]:
    mail_cfg = config["mail"]
    client = imaplib.IMAP4_SSL(mail_cfg["imap_server"], int(mail_cfg["imap_port"]))
    try:
        client.login(mail_cfg["email_account"], mail_cfg["email_auth_code"])
        logger.info("邮箱登录成功")
        _send_imap_id(client, logger)
        _select_inbox(client)

        since = _imap_date(stat_date)
        search_before = _imap_date(stat_date + timedelta(days=1))
        status, data = client.search(None, f'(SINCE "{since}" BEFORE "{search_before}")')
        if status != "OK":
            detail = _decode_imap_response(data)
            raise RuntimeError(f"IMAP 搜索失败：{detail}")

        messages: list[MailMessage] = []
        for uid in data[0].split():
            fetch_status, fetch_data = client.fetch(uid, "(RFC822)")
            if fetch_status != "OK" or not fetch_data:
                continue
            msg = email.message_from_bytes(fetch_data[0][1])
            mail = _to_mail_message(uid.decode("ascii", errors="ignore"), msg, config)
            if _message_matches(mail, config):
                messages.append(mail)

        logger.info("搜索到候选邮件 %s 封", len(messages))
        return messages
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _send_imap_id(client: imaplib.IMAP4_SSL, logger: Logger) -> None:
    payload = _format_imap_id(IMAP_ID)
    try:
        imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
        status, data = client._simple_command("ID", payload)
        if status == "OK":
            logger.info("已发送 IMAP ID 客户端信息")
            return
        logger.warning("IMAP ID 命令未成功：%s", _decode_imap_response(data))
    except Exception as exc:
        logger.warning("IMAP ID 命令发送失败：%s", exc)


def _format_imap_id(values: dict[str, str]) -> str:
    pairs: list[str] = []
    for key, value in values.items():
        pairs.append(f'"{_escape_imap_string(key)}"')
        pairs.append(f'"{_escape_imap_string(value)}"')
    return f"({' '.join(pairs)})"


def _escape_imap_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _select_inbox(client: imaplib.IMAP4_SSL) -> None:
    attempts = [
        lambda: client.select("INBOX"),
        lambda: client.select("INBOX", readonly=True),
        lambda: client.select(),
    ]
    errors: list[str] = []
    for attempt in attempts:
        status, data = attempt()
        if status == "OK":
            return
        errors.append(_decode_imap_response(data))

    status, boxes = client.list()
    box_hint = _decode_imap_response(boxes) if status == "OK" else "无法读取邮箱文件夹列表"
    raise RuntimeError(
        "邮箱登录成功，但无法进入收件箱。请确认 163 邮箱已开启 IMAP/SMTP 服务，"
        f"并使用客户端授权码。服务器返回：{'; '.join(errors)}。邮箱文件夹：{box_hint}"
    )


def _to_mail_message(uid: str, msg: email.message.Message, config: dict) -> MailMessage:
    subject = _decode_value(msg.get("Subject", ""))
    sender_name, sender_email = _parse_sender(msg.get("From", ""))
    received_header = msg.get("Date")
    received = parsedate_to_datetime(received_header).replace(tzinfo=None) if received_header else None
    if received is None:
        received = datetime.now()
    attachments: list[tuple[str, bytes]] = []
    allowed_exts = {item.lower() for item in config["filter"].get("attachment_extensions", [])}

    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        filename = _decode_value(filename)
        if allowed_exts and not any(filename.lower().endswith(ext) for ext in allowed_exts):
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append((filename, payload))

    return MailMessage(uid, subject, sender_name, sender_email, received, attachments)


def _message_matches(mail: MailMessage, config: dict) -> bool:
    allowed_senders = {item.lower() for item in config["filter"].get("allowed_senders", [])}
    keywords = config["filter"].get("subject_keywords", [])
    sender_ok = not allowed_senders or mail.sender_email.lower() in allowed_senders
    subject_ok = not keywords or any(keyword.lower() in mail.subject.lower() for keyword in keywords)
    return bool(mail.attachments) and sender_ok and subject_ok


def _decode_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(_decode_bytes(text, charset))
        else:
            decoded.append(text)
    return "".join(decoded)


def _decode_bytes(value: bytes, charset: str | None) -> str:
    candidates = [charset, "utf-8", "gb18030", "gbk", "latin1"]
    for candidate in candidates:
        if not candidate or candidate.lower() == "unknown-8bit":
            continue
        try:
            return value.decode(candidate, errors="replace")
        except LookupError:
            continue
    return value.decode("utf-8", errors="replace")


def _decode_imap_response(data: object) -> str:
    if not data:
        return ""
    if isinstance(data, (bytes, bytearray)):
        return bytes(data).decode("utf-8", errors="replace")
    if isinstance(data, list):
        return " | ".join(_decode_imap_response(item) for item in data if item)
    return str(data)


def _parse_sender(value: str) -> tuple[str, str]:
    parsed = getaddresses([value])[0]
    return _decode_value(parsed[0]), parsed[1]


def _imap_date(value: date) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{value.day:02d}-{months[value.month - 1]}-{value.year}"
