from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.app_constants import APP_VERSION, PRODUCT_CODE

from .machine_fingerprint import MachineFingerprint, get_machine_fingerprint


REQUEST_FORMAT_VERSION = 1


def build_license_request(customer_name: str, fingerprint: MachineFingerprint | None = None) -> dict:
    fp = fingerprint or get_machine_fingerprint()
    return {
        "request_format_version": REQUEST_FORMAT_VERSION,
        "request_type": "new",
        "product_code": PRODUCT_CODE,
        "app_version": APP_VERSION,
        "customer_name": customer_name.strip(),
        "machine_code": fp.machine_code,
        "machine_hash": fp.machine_hash,
        "device_name": fp.device_name,
        "windows_version": fp.windows_version,
        "request_time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint_components": sorted(fp.components.keys()),
    }


def export_license_request(customer_name: str, output_dir: Path, fingerprint: MachineFingerprint | None = None) -> Path:
    request = build_license_request(customer_name, fingerprint)
    output_dir.mkdir(parents=True, exist_ok=True)
    machine_code = request["machine_code"]
    path = output_dir / f"WindMail_授权申请_{machine_code}.req"
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_license_change_request(
    customer_name: str,
    request_type: str,
    current_license_payload: dict,
    fingerprint: MachineFingerprint | None = None,
) -> dict:
    if request_type not in {"renewal", "upgrade"}:
        raise ValueError("request_type must be renewal or upgrade")
    request = build_license_request(customer_name, fingerprint)
    request.update(
        {
            "request_type": request_type,
            "previous_license_id": str(current_license_payload.get("license_id", "")),
            "previous_customer_code": str(current_license_payload.get("customer_code", "")),
            "previous_edition": str(current_license_payload.get("edition", "")),
            "previous_max_mailboxes": current_license_payload.get("max_mailboxes", ""),
            "previous_effective_date": str(current_license_payload.get("effective_date", "")),
            "previous_expiry_date": str(current_license_payload.get("expiry_date", "")),
        }
    )
    return request


def export_license_change_request(
    customer_name: str,
    output_dir: Path,
    request_type: str,
    current_license_payload: dict,
    fingerprint: MachineFingerprint | None = None,
) -> Path:
    request = build_license_change_request(customer_name, request_type, current_license_payload, fingerprint)
    output_dir.mkdir(parents=True, exist_ok=True)
    machine_code = request["machine_code"]
    label = "renewal" if request_type == "renewal" else "upgrade"
    previous_license_id = request.get("previous_license_id", "")
    path = output_dir / f"WindMail_{label}_request_{machine_code}_{previous_license_id}.req"
    path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fingerprint_to_public_dict(fingerprint: MachineFingerprint) -> dict:
    data = asdict(fingerprint)
    data["fingerprint_components"] = sorted(fingerprint.components.keys())
    data.pop("components", None)
    return data
