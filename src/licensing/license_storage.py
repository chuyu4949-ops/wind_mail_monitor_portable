from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


LICENSE_FILENAME = "license.lic"


def candidate_license_paths(base_dir: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get("WIND_MAIL_LICENSE_PATH")
    if override:
        paths.append(Path(override))
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        paths.append(Path(program_data) / "WindMailMonitor" / LICENSE_FILENAME)
    if base_dir is not None:
        paths.append(base_dir / LICENSE_FILENAME)
        paths.append(base_dir / "config" / LICENSE_FILENAME)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path.absolute())
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return deduped


def load_license_data(base_dir: Path | None = None) -> tuple[dict, Path]:
    for path in candidate_license_paths(base_dir):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
    raise FileNotFoundError("未导入许可证")


def import_license_file(source_path: Path, base_dir: Path | None = None) -> Path:
    targets = candidate_license_paths(base_dir)
    if not targets:
        raise RuntimeError("无法确定许可证保存位置")
    last_error: Exception | None = None
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = target.with_suffix(target.suffix + f".bak-{datetime.now().strftime('%Y%m%d%H%M%S')}")
                shutil.copy2(target, backup)
            shutil.copy2(source_path, target)
            return target
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"许可证保存失败：{last_error}")
