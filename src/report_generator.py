from __future__ import annotations

import html
import zipfile
from datetime import date
from logging import Logger
from pathlib import Path
from xml.sax.saxutils import escape

from .models import DailyResult


def generate_html_report(report_dir: Path, stat_date: date, result: DailyResult, logger: Logger) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"测风数据接收日报_{stat_date.isoformat()}.html"
    received_names = "、".join(r["display_name"] for r in result.received_rows) or "无"
    body = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>测风数据接收日报 - {stat_date}</title>
<style>body{{font-family:Microsoft YaHei,Arial,sans-serif;line-height:1.6;color:#222}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #ddd;padding:6px 8px;text-align:left}}th{{background:#f3f6fb}}.warn{{color:#b00020;font-weight:600}}</style></head>
<body>
<h2>测风数据接收日报 - {stat_date}</h2>
<p>统计周期：{stat_date} 00:00:00 至 {stat_date} 23:59:59</p>
<h3>一、总体情况</h3>
<ul>
<li>今日收到测风塔数量：{len(result.received_rows)} 座</li>
<li>今日附件数量：{len(result.attachment_rows)} 个</li>
<li>今日缺失提醒：{len(result.missing_rows)} 座</li>
<li>连续缺失提醒：{len(result.continuous_missing_rows)} 座</li>
<li>文件大小异常：{len(result.size_warning_rows)} 个</li>
<li>未识别附件：{len(result.unknown_rows)} 个</li>
</ul>
<h3>二、今日收到测风塔</h3><p>{html.escape(received_names)}</p>
<h3>三、今日缺失提醒</h3>{_html_table(result.missing_rows, ["display_name", "continuous_missing_days", "missing_status"])}
<h3>四、连续缺失提醒</h3>{_html_table(result.continuous_missing_rows, ["display_name", "continuous_missing_days", "missing_status"])}
<h3>五、文件大小异常</h3>{_html_table(result.size_warning_rows, ["display_name", "filename", "file_size_kb", "size_status"])}
<h3>六、未识别附件</h3>{_html_table(result.unknown_rows, ["subject", "filename", "file_size_kb"])}
<h3>七、处理建议</h3>
<ol><li>联系缺失测风塔对应的数据发送单位核查是否漏发。</li><li>对连续缺失 2 天及以上的测风塔建立补发跟踪。</li><li>对小于 20 KB 的附件进行人工复核。</li></ol>
</body></html>"""
    path.write_text(body, encoding="utf-8")
    logger.info("HTML 日报生成成功：%s", path)
    return path


def generate_xlsx_report(report_dir: Path, stat_date: date, result: DailyResult, logger: Logger) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"测风数据接收日报_{stat_date.isoformat()}.xlsx"
    sheets = [
        ("总体汇总", [["指标", "数量"], ["今日收到测风塔数量", len(result.received_rows)], ["今日附件数量", len(result.attachment_rows)], ["今日缺失提醒", len(result.missing_rows)], ["连续缺失提醒", len(result.continuous_missing_rows)], ["文件大小异常", len(result.size_warning_rows)], ["未识别附件", len(result.unknown_rows)]]),
        ("今日接收清单", _rows(result.received_rows, ["normalized_mast_id", "display_name", "attachment_count", "min_file_size_kb"])),
        ("缺失提醒", _rows(result.missing_rows, ["normalized_mast_id", "display_name", "continuous_missing_days", "missing_status"])),
        ("连续缺失提醒", _rows(result.continuous_missing_rows, ["normalized_mast_id", "display_name", "continuous_missing_days", "missing_status"])),
        ("文件大小异常", _rows(result.size_warning_rows, ["display_name", "filename", "file_size_kb", "size_status"])),
        ("邮件附件明细", _rows(result.attachment_rows, ["email_received_date", "display_name", "filename", "file_size_kb", "size_status", "subject", "sender_email", "file_path"])),
        ("未识别附件", _rows(result.unknown_rows, ["email_received_date", "subject", "filename", "file_size_kb", "file_path"])),
    ]
    _write_xlsx(path, sheets)
    logger.info("Excel 日报生成成功：%s", path)
    return path


def _rows(rows: list[dict], columns: list[str]) -> list[list[object]]:
    return [columns] + [[row.get(col, "") for col in columns] for row in rows]


def _html_table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "<p>无。</p>"
    header = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(col, '')))}</td>" for col in columns) + "</tr>" for row in rows)
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def _write_xlsx(path: Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types(len(sheets)))
        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>""")
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets)))
        zf.writestr("xl/workbook.xml", _workbook_xml([name for name, _ in sheets]))
        zf.writestr("xl/styles.xml", """<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs></styleSheet>""")
        for idx, (_, rows) in enumerate(sheets, 1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(rows))


def _content_types(count: int) -> str:
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, count + 1))
    return f"""<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{sheets}</Types>"""


def _workbook_rels(count: int) -> str:
    rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, count + 1))
    return f"""<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}<Relationship Id="rId{count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>"""


def _workbook_xml(names: list[str]) -> str:
    sheets = "".join(f'<sheet name="{escape(name[:31])}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1))
    return f"""<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets}</sheets></workbook>"""


def _sheet_xml(rows: list[list[object]]) -> str:
    xml_rows = []
    for r_idx, row in enumerate(rows, 1):
        cells = []
        for c_idx, value in enumerate(row, 1):
            ref = f"{_col(c_idx)}{r_idx}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    return f"""<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(xml_rows)}</sheetData></worksheet>"""


def _col(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result
