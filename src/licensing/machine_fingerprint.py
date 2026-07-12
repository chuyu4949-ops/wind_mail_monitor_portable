from __future__ import annotations

import hashlib
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass

from src.app_constants import PRODUCT_CODE

from .errors import MachineFingerprintError


PRODUCT_SALT = "wind-mail-monitor-device-v1"
INVALID_VALUES = {
    "",
    "0",
    "NONE",
    "NULL",
    "UNKNOWN",
    "TO BE FILLED BY O.E.M.",
    "TO BE FILLED BY OEM",
    "SYSTEM SERIAL NUMBER",
    "DEFAULT STRING",
    "NOT APPLICABLE",
}


@dataclass(frozen=True)
class MachineFingerprint:
    machine_hash: str
    machine_code: str
    components: dict[str, str]
    device_name: str
    windows_version: str


def get_machine_fingerprint() -> MachineFingerprint:
    components = collect_machine_components()
    if len(components) < 2:
        raise MachineFingerprintError(
            "无法生成稳定设备码：读取到的硬件标识少于 2 项。请联系技术支持，并提供当前电脑型号和系统版本。"
        )

    canonical = "|".join(f"{key}={components[key]}" for key in sorted(components))
    digest = hashlib.sha256(f"{PRODUCT_SALT}|{PRODUCT_CODE}|{canonical}".encode("utf-8")).hexdigest()
    return MachineFingerprint(
        machine_hash=digest,
        machine_code=_short_machine_code(digest),
        components=components,
        device_name=socket.gethostname(),
        windows_version=_windows_version(),
    )


def collect_machine_components() -> dict[str, str]:
    collectors = {
        "machine_guid": _read_machine_guid,
        "bios_uuid": lambda: _read_wmic_value("csproduct", "UUID"),
        "baseboard_serial": lambda: _read_wmic_value("baseboard", "SerialNumber"),
        "system_drive_serial": _read_system_drive_serial,
    }
    values: dict[str, str] = {}
    for key, collector in collectors.items():
        value = _normalize(collector())
        if value:
            values[key] = value
    return values


def _read_machine_guid() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def _read_wmic_value(alias: str, field: str) -> str:
    result = _run_command(["wmic", alias, "get", field, "/value"])
    match = re.search(rf"^{re.escape(field)}=(.+)$", result, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1) if match else ""


def _read_system_drive_serial() -> str:
    drive = "C:"
    result = _run_command(["cmd", "/c", "vol", drive])
    match = re.search(r"([0-9A-F]{4}-[0-9A-F]{4})", result, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _run_command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=8)
        if result.returncode != 0:
            return ""
        return result.stdout
    except Exception:
        return ""


def _normalize(value: object) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"\s+", " ", text)
    if text in INVALID_VALUES:
        return ""
    if all(char in "0-" for char in text):
        return ""
    return text


def _short_machine_code(machine_hash: str) -> str:
    return f"WMPC-{machine_hash[:4].upper()}-{machine_hash[4:8].upper()}"


def _windows_version() -> str:
    return f"{platform.system()} {platform.release()} {platform.version()}".strip()
