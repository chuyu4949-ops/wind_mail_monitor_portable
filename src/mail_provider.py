from __future__ import annotations

from copy import deepcopy


MAIL_PROVIDERS: dict[str, dict[str, object]] = {
    "qq.com": {
        "label": "QQ邮箱",
        "imap_server": "imap.qq.com",
        "imap_port": 993,
        "smtp_server": "smtp.qq.com",
        "smtp_port": 465,
        "use_ssl": True,
        "smtp_starttls": False,
        "type": "qq",
    },
    "foxmail.com": {
        "label": "Foxmail",
        "imap_server": "imap.qq.com",
        "imap_port": 993,
        "smtp_server": "smtp.qq.com",
        "smtp_port": 465,
        "use_ssl": True,
        "smtp_starttls": False,
        "type": "foxmail",
    },
    "163.com": {
        "label": "163邮箱",
        "imap_server": "imap.163.com",
        "imap_port": 993,
        "smtp_server": "smtp.163.com",
        "smtp_port": 465,
        "use_ssl": True,
        "smtp_starttls": False,
        "type": "163",
    },
    "126.com": {
        "label": "126邮箱",
        "imap_server": "imap.126.com",
        "imap_port": 993,
        "smtp_server": "smtp.126.com",
        "smtp_port": 465,
        "use_ssl": True,
        "smtp_starttls": False,
        "type": "126",
    },
    "gmail.com": {
        "label": "Gmail",
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 465,
        "use_ssl": True,
        "smtp_starttls": False,
        "type": "gmail",
    },
    "outlook.com": {
        "label": "Outlook",
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "use_ssl": False,
        "smtp_starttls": True,
        "type": "outlook",
    },
}


def email_domain(account: str) -> str:
    text = (account or "").strip().lower()
    if "@" not in text:
        return ""
    return text.rsplit("@", 1)[-1]


def provider_for_account(account: str) -> dict[str, object] | None:
    domain = email_domain(account)
    provider = MAIL_PROVIDERS.get(domain)
    return deepcopy(provider) if provider else None


def apply_mail_provider_defaults(mail_cfg: dict) -> dict:
    account = str(mail_cfg.get("email_account", "")).strip()
    provider = provider_for_account(account)
    if not provider:
        mail_cfg.setdefault("imap_port", 993)
        mail_cfg.setdefault("smtp_port", 465)
        mail_cfg.setdefault("use_ssl", True)
        mail_cfg.setdefault("smtp_starttls", False)
        mail_cfg.setdefault("type", "custom")
        return mail_cfg

    for key in ("imap_server", "imap_port", "smtp_server", "smtp_port", "use_ssl", "smtp_starttls", "type"):
        mail_cfg[key] = provider[key]
    return mail_cfg


def supported_provider_text() -> str:
    labels = [str(provider["label"]) for provider in MAIL_PROVIDERS.values()]
    return "、".join(labels)
