from __future__ import annotations

from datetime import date

from src.app_constants import PRODUCT_CODE

from .errors import LicensingError
from .license_signature import verify_license_signature
from .machine_fingerprint import MachineFingerprint, get_machine_fingerprint


def validate_signed_license(license_data: dict, public_key_b64: str) -> dict:
    if license_data.get("format_version") != 1:
        raise LicensingError("不支持的许可证格式版本")
    payload = license_data.get("payload")
    if not isinstance(payload, dict):
        raise LicensingError("许可证 payload 格式错误")
    if payload.get("product_code") != PRODUCT_CODE:
        raise LicensingError("许可证产品编码不匹配")
    if not verify_license_signature(license_data, public_key_b64):
        raise LicensingError("许可证签名无效")
    return payload


def validate_license_for_machine(
    license_data: dict,
    public_key_b64: str,
    required_feature: str | None = None,
    today: date | None = None,
    fingerprint: MachineFingerprint | None = None,
) -> dict:
    payload = validate_signed_license(license_data, public_key_b64)
    fp = fingerprint or get_machine_fingerprint()
    if payload.get("machine_hash") != fp.machine_hash:
        raise LicensingError("许可证绑定设备与当前电脑不匹配")

    current = today or date.today()
    effective = date.fromisoformat(str(payload.get("effective_date")))
    expiry = date.fromisoformat(str(payload.get("expiry_date")))
    if current < effective:
        raise LicensingError(f"许可证尚未生效，生效日期：{effective.isoformat()}")
    if current > expiry:
        raise LicensingError(f"许可证已到期，到期日期：{expiry.isoformat()}")

    if int(payload.get("max_mailboxes", 0)) < 1:
        raise LicensingError("许可证允许邮箱数量无效")
    features = set(payload.get("features", []))
    legacy_feature_aliases = {
        PRODUCT_CODE: {"mail_monitor"},
    }
    allowed_aliases = legacy_feature_aliases.get(required_feature or "", set())
    if required_feature and required_feature not in features and not (features & allowed_aliases):
        raise LicensingError(f"当前许可证未授权功能：{required_feature}")
    return payload
