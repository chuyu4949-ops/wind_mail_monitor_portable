from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


SENSITIVE_KEYS = {
    "machine_hash",
    "fingerprint_components",
    "components",
    "email_auth_code",
    "password",
    "private_seed_b64",
    "private_key",
    "signature",
}


def append_license_audit_event(base_dir: Path, event: str, details: dict | None = None) -> None:
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "details": _sanitize(details or {}),
    }
    with (log_dir / "license_audit.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _sanitize(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items() if key not in SENSITIVE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value
