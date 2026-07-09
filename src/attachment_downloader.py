from __future__ import annotations

from datetime import date
from logging import Logger
from pathlib import Path

from .mast_parser import parse_attachment
from .models import AttachmentRecord, EmailRecord, MailMessage, SavedAttachment


def save_attachments(base_dir: Path, config: dict, messages: list[MailMessage], stat_date: date, logger: Logger) -> list[SavedAttachment]:
    data_dir = base_dir / config["storage"]["data_dir"] / stat_date.isoformat()
    warning_kb = float(config["rules"]["file_size_warning_kb"])
    saved: list[SavedAttachment] = []

    for mail in messages:
        email_record = EmailRecord(
            email_uid=mail.email_uid,
            subject=mail.subject,
            sender_name=mail.sender_name,
            sender_email=mail.sender_email,
            received_time=mail.received_time.isoformat(sep=" "),
            has_attachment=1 if mail.attachments else 0,
        )
        for filename, content in mail.attachments:
            parsed = parse_attachment(filename, subject=mail.subject)
            mast_dir = data_dir / (parsed["normalized_mast_id"] or "未识别附件")
            mast_dir.mkdir(parents=True, exist_ok=True)
            path = _unique_path(mast_dir / filename)
            path.write_bytes(content)
            parsed = parse_attachment(filename, path, mail.subject)

            file_size_bytes = len(content)
            file_size_kb = round(file_size_bytes / 1024, 2)
            size_status = "正常"
            if file_size_bytes == 0:
                size_status = "空文件异常"
            elif file_size_kb < warning_kb:
                size_status = f"文件小于 {warning_kb:g} KB"

            attachment_record = AttachmentRecord(
                email_uid=mail.email_uid,
                subject=mail.subject,
                sender_email=mail.sender_email,
                raw_device_code=parsed["raw_device_code"],
                normalized_mast_id=parsed["normalized_mast_id"],
                display_name=parsed["display_name"] or "未识别附件",
                filename=filename,
                file_path=str(path),
                file_extension=path.suffix.lower(),
                file_size_bytes=file_size_bytes,
                file_size_kb=file_size_kb,
                email_received_date=mail.received_time.date().isoformat(),
                attachment_date=parsed["attachment_date"],
                data_date=parsed["data_date"],
                size_status=size_status,
            )
            saved.append(SavedAttachment(email_record, attachment_record))
            logger.info("保存附件：%s", path)
    return saved


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_重复{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
