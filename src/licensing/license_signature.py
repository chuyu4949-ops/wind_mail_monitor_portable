from __future__ import annotations

import base64

from .ed25519_core import verify
from .errors import LicensingError
from .license_canonical import canonical_payload
from .public_key import PUBLIC_KEY_B64


SIGNATURE_ALGORITHM = "Ed25519"


def verify_payload_signature(payload: dict, signature_b64: str, public_key_b64: str = PUBLIC_KEY_B64) -> bool:
    if not public_key_b64:
        raise LicensingError("客户端未配置许可证验签公钥")
    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception as exc:
        raise LicensingError("许可证签名或公钥不是有效 Base64") from exc
    return verify(public_key, canonical_payload(payload), signature)


def verify_license_signature(license_data: dict, public_key_b64: str = PUBLIC_KEY_B64) -> bool:
    if license_data.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise LicensingError("不支持的许可证签名算法")
    payload = license_data.get("payload")
    signature = license_data.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise LicensingError("许可证缺少 payload 或 signature")
    return verify_payload_signature(payload, signature, public_key_b64)
