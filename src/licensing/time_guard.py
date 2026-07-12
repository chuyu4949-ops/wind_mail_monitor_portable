from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .errors import LicensingError


STATE_FILENAME = "license_state.json"


@dataclass(frozen=True)
class TimeGuardResult:
    warning: str = ""


def check_and_update_time_state(base_dir: Path, payload: dict, now: datetime | None = None) -> TimeGuardResult:
    current = now or datetime.now()
    state_path = base_dir / "config" / STATE_FILENAME
    previous = _read_state(state_path)
    warning = ""

    last_seen_text = previous.get("last_seen_time")
    last_seen = datetime.fromisoformat(last_seen_text) if last_seen_text else None
    if last_seen is not None:
        rollback = last_seen - current
        if rollback > timedelta(hours=24):
            raise LicensingError("检测到系统时间明显回退，授权状态异常。请校准电脑时间后重试。")
        if rollback > timedelta(hours=12):
            warning = "检测到系统时间轻微回退，请确认电脑时间准确。"

    stored_seen = max(current, last_seen).isoformat(timespec="seconds") if last_seen else current.isoformat(timespec="seconds")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_seen_time": stored_seen,
                "last_valid_license_time": current.isoformat(timespec="seconds"),
                "license_id": payload.get("license_id", ""),
                "machine_hash": payload.get("machine_hash", ""),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return TimeGuardResult(warning)


def _read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
