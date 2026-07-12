from __future__ import annotations


class LicensingError(RuntimeError):
    """Base error for offline licensing features."""


class MachineFingerprintError(LicensingError):
    """Raised when a stable machine fingerprint cannot be generated."""
