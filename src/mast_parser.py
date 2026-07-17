from __future__ import annotations

import re
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

RLD_PATTERN = re.compile(r"^(?P<code>\d{5,6})_(?P<data_date>\d{4}-\d{2}-\d{2})_00\.00_(?P<seq>\d+)\.rld$", re.I)
SWIFT_PATTERN = re.compile(r"^(?P<code>\d{5})(?P<data_date>20\d{6})m\d+\.swift$", re.I)
RWD_DAT_PATTERN = re.compile(r"^(?P<code>\d{4})(?P<data_date>20\d{6})\d*\.(?:rwd|dat)$", re.I)
MOLAS_ZIP_PATTERN = re.compile(r"^Molas B300-(?P<code>\d+)-(?P<attachment_date>\d{8})-(?P<batch>\d+)\.zip$", re.I)
MOLAS_INNER_PATTERN = re.compile(r"^Molas B300-(?P<code>\d+)WindSpeedAverage(?P<data_date>\d{8})\.txt$", re.I)
SUPPORTED_WIND_EXTENSIONS = {".rld", ".swift", ".rwd", ".dat", ".zip", ".txt"}


def normalize_code(raw_code: str) -> str:
    stripped = raw_code.lstrip("0")
    return stripped or raw_code


def filename_starts_with_six_digits(filename: str) -> bool:
    name = Path(filename).name
    return len(name) >= 6 and name[:6].isdigit()


def is_supported_wind_filename(filename: str) -> bool:
    name = Path(filename).name
    if Path(name).suffix.lower() not in SUPPORTED_WIND_EXTENSIONS:
        return False
    return bool(
        RLD_PATTERN.match(name)
        or SWIFT_PATTERN.match(name)
        or RWD_DAT_PATTERN.match(name)
        or MOLAS_ZIP_PATTERN.match(name)
        or MOLAS_INNER_PATTERN.match(name)
        or filename_starts_with_six_digits(name)
    )


def parse_attachment(
    filename: str,
    file_path: Path | None = None,
    subject: str = "",
    default_year: int | None = None,
) -> dict[str, str]:
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
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u5854"
        return result

    swift_match = SWIFT_PATTERN.match(name)
    if swift_match:
        raw = swift_match.group("code")
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=_format_yyyymmdd(swift_match.group("data_date")),
        )
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u5854"
        return result

    rwd_dat_match = RWD_DAT_PATTERN.match(name)
    if rwd_dat_match:
        raw = rwd_dat_match.group("code")
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=_format_yyyymmdd(rwd_dat_match.group("data_date")),
        )
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u5854"
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
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u96f7\u8fbe"
        return result

    molas_text_match = MOLAS_INNER_PATTERN.match(name)
    if molas_text_match:
        raw = molas_text_match.group("code")
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=_format_yyyymmdd(molas_text_match.group("data_date")),
        )
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u96f7\u8fbe"
        return result

    if filename_starts_with_six_digits(name) and ext:
        raw = name[:6]
        content_date = _date_from_file_content(file_path, default_year) if file_path else ""
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=_date_from_text(name, default_year) or _date_from_text(subject, default_year) or content_date,
        )
        result["display_name"] = f"{result['normalized_mast_id']}#\u6d4b\u98ce\u5854"
        return result

    raw = _code_from_subject(subject)
    if raw and ext:
        content_date = _date_from_file_content(file_path, default_year) if file_path else ""
        result.update(
            raw_device_code=raw,
            normalized_mast_id=normalize_code(raw),
            data_date=_date_from_text(name, default_year) or _date_from_text(subject, default_year) or content_date,
        )
        result["display_name"] = result["normalized_mast_id"]
    return result


def payload_has_stat_date(content: bytes, stat_date: date) -> bool:
    if _zip_payload_has_stat_date(content, stat_date):
        return True
    text = _decode_content_sample(content)
    if not text:
        return False
    return stat_date.isoformat() in _dates_from_text(text, stat_date.year)


def _zip_payload_has_stat_date(content: bytes, stat_date: date) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            expected = stat_date.isoformat()
            for info in archive.infolist():
                name = Path(info.filename).name
                parsed = parse_attachment(name, default_year=stat_date.year)
                if parsed.get("data_date") == expected or parsed.get("attachment_date") == expected:
                    return True
                if info.file_size <= 512 * 1024 and not info.is_dir():
                    text = _decode_content_sample(archive.read(info))
                    if expected in _dates_from_text(text, stat_date.year):
                        return True
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return False
    return False


def _code_from_subject(subject: str) -> str:
    numbers = re.findall(r"(?<!\d)(\d{1,6})(?!\d)", subject)
    if not numbers:
        return ""
    mast_like = [number for number in numbers if len(number) >= 4]
    return mast_like[-1] if mast_like else numbers[-1]


def _date_from_text(text: str, default_year: int | None = None) -> str:
    dates = _dates_from_text(text, default_year)
    return dates[0] if dates else ""


def _dates_from_text(text: str, default_year: int | None = None) -> list[str]:
    found: list[str] = []

    compact = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text)
    for compact in re.finditer(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text):
        _append_date(found, compact.group(1), compact.group(2), compact.group(3))

    for separated in re.finditer(r"(?<!\d)(20\d{2})[-_/.\u5e74](\d{1,2})[-_/.\u6708](\d{1,2})\u65e5?(?!\d)", text):
        _append_date(found, separated.group(1), separated.group(2), separated.group(3))

    if default_year is not None:
        for month_day in re.finditer(r"(?<!\d)(\d{1,2})\s*(?:\u6708|[-_.\/])\s*(\d{1,2})\s*\u65e5?(?!\d)", text):
            _append_date(found, str(default_year), month_day.group(1), month_day.group(2))

        for compact_month_day in re.finditer(r"(?<!\d)(0[1-9]|1[0-2])([0-3]\d)(?!\d)", text):
            _append_date(found, str(default_year), compact_month_day.group(1), compact_month_day.group(2))

    return found


def _append_date(target: list[str], year: str, month: str, day: str) -> None:
    parsed = _valid_date_or_empty(year, month, day)
    if parsed and parsed not in target:
        target.append(parsed)


def _valid_date_or_empty(year: str, month: str, day: str) -> str:
    try:
        parsed = date(int(year), int(month), int(day))
        return parsed.isoformat()
    except ValueError:
        return ""


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


def _date_from_file_content(path: Path | None, default_year: int | None = None) -> str:
    if not path or not path.exists() or path.suffix.lower() in {".zip", ".rar", ".7z"}:
        return ""
    return _date_from_text(_decode_content_sample(path.read_bytes()), default_year)


def _decode_content_sample(content: bytes) -> str:
    sample = content[:256 * 1024]
    for encoding in ("utf-8", "gb18030", "gbk", "latin1"):
        try:
            return sample.decode(encoding, errors="ignore")
        except LookupError:
            continue
    return ""


def _format_yyyymmdd(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
