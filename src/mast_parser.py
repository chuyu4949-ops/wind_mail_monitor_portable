from __future__ import annotations

import re
import zipfile
from pathlib import Path

RLD_PATTERN = re.compile(r"^(?P<code>\d{5,6})_(?P<data_date>\d{4}-\d{2}-\d{2})_00\.00_(?P<seq>\d+)\.rld$", re.I)
MOLAS_ZIP_PATTERN = re.compile(r"^Molas B300-(?P<code>\d+)-(?P<attachment_date>\d{8})-(?P<batch>\d+)\.zip$", re.I)
MOLAS_INNER_PATTERN = re.compile(r"^Molas B300-(?P<code>\d+)WindSpeedAverage(?P<data_date>\d{8})\.txt$", re.I)


def normalize_code(raw_code: str) -> str:
    stripped = raw_code.lstrip("0")
    return stripped or raw_code


def parse_attachment(filename: str, file_path: Path | None = None, subject: str = "") -> dict[str, str]:
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    result = {
        "raw_device_code": "",
        "normalized_mast_id": "",
        "display_name": "",
        "attachment_date": "",
        "data_date": "",
    }

    rld_match = RLD_PATTERN.match(name)
    if rld_match:
        raw = rld_match.group("code")
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=rld_match.group("data_date"),
        )
        result["display_name"] = f"{result['normalized_mast_id']}#测风塔"
        return result

    zip_match = MOLAS_ZIP_PATTERN.match(name)
    if zip_match:
        raw = zip_match.group("code")
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            attachment_date=_format_yyyymmdd(zip_match.group("attachment_date")),
        )
        if file_path and file_path.exists():
            result["data_date"] = _read_molas_zip_data_date(file_path) or ""
        result["display_name"] = f"{result['normalized_mast_id']}#测风雷达"
        return result

    subject_match = re.search(r"(?<!\d)(\d{1,6})(?!\d)", subject)
    if subject_match and ext:
        raw = subject_match.group(1)
        result.update(raw_device_code=raw, normalized_mast_id=normalize_code(raw))
        result["display_name"] = result["normalized_mast_id"]
    return result


def _read_molas_zip_data_date(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                match = MOLAS_INNER_PATTERN.match(Path(name).name)
                if match:
                    return _format_yyyymmdd(match.group("data_date"))
    except zipfile.BadZipFile:
        return None
    return None


def _format_yyyymmdd(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
