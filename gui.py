from __future__ import annotations

import queue
import json
import subprocess
import sys
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from tkinter import filedialog, messagebox

import main as monitor_main
from src.app_constants import APP_VERSION, PRODUCT_NAME
from src.config_loader import load_config
from src.config_writer import save_config
from src.licensing import LicenseCheckPoint, LicenseRequirement, export_license_change_request, export_license_request, get_license_status, get_machine_fingerprint, import_and_validate_license, require_valid_license
from src.licensing.errors import MachineFingerprintError
from src.mail_provider import apply_mail_provider_defaults, supported_provider_text


BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
ASSET_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "assets"

BG = "#f5f8fc"
SURFACE = "#ffffff"
BORDER = "#dbe3ef"
TEXT = "#0f172a"
MUTED = "#64748b"
PRIMARY = "#0f6bff"
PRIMARY_DARK = "#0757d9"
INFO_BG = "#eef6ff"
INFO_BORDER = "#acd2ff"
INPUT_BG = "#ffffff"
INPUT_BORDER = "#cfd8e6"
ICON_FONT = ("Segoe MDL2 Assets", 15)
FONT = "Microsoft YaHei UI"


class MonitorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        require_valid_license(LicenseRequirement(LicenseCheckPoint.GUI_STARTUP, "mail_monitor"), BASE_DIR)
        self.title(f"{PRODUCT_NAME} V{APP_VERSION}")
        self._set_app_icon()
        self._configure_window()
        self.configure(bg=BG)
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.current_tab = "mail"
        self.nav_items: dict[str, dict[str, tk.Widget]] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.log_empty = True
        self.alert_icon_active = False
        self.machine_fingerprint = None
        self.config_data = load_config(CONFIG_PATH)
        self._build_vars()
        self._build_ui()
        self.refresh_alert_icon()
        self._poll_output()

    def _configure_window(self) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1120, max(780, int(screen_w * 0.9)))
        height = min(780, max(560, int(screen_h * 0.86)))
        left = max(0, (screen_w - width) // 2)
        top = max(0, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.minsize(720, 520)

    def _set_app_icon(self, alert: bool = False) -> None:
        icon_name = "app_icon_alert.ico" if alert else "app_icon.ico"
        icon_path = ASSET_DIR / icon_name
        if not icon_path.exists():
            icon_path = BASE_DIR / "assets" / icon_name
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                pass

    def _build_vars(self) -> None:
        mail = self.config_data["mail"]
        report = self.config_data["report"]
        rules = self.config_data["rules"]
        storage = self.config_data["storage"]
        filters = self.config_data["filter"]
        self.email_account = tk.StringVar(value=mail.get("email_account", ""))
        self.email_auth_code = tk.StringVar(value=mail.get("email_auth_code", ""))
        self.imap_server = tk.StringVar(value=mail.get("imap_server", ""))
        self.smtp_server = tk.StringVar(value=mail.get("smtp_server", ""))
        self.receivers = tk.StringVar(value=", ".join(report.get("report_receivers", [])))
        self.cc = tk.StringVar(value=", ".join(report.get("report_cc", [])))
        self.send_email = tk.BooleanVar(value=bool(report.get("send_email", True)))
        self.file_size_warning_kb = tk.StringVar(value=str(rules.get("file_size_warning_kb", 20)))
        self.continuous_missing_days = tk.StringVar(value=str(rules.get("continuous_missing_warning_days", 2)))
        self.stat_date = tk.StringVar(value=(date.today() - timedelta(days=1)).isoformat())
        self.allowed_senders = tk.StringVar(value="\n".join(filters.get("allowed_senders", [])))
        self.subject_keywords = tk.StringVar(value="\n".join(filters.get("subject_keywords", [])))
        self.data_dir = tk.StringVar(value=storage.get("data_dir", "./data"))
        self.report_dir = tk.StringVar(value=storage.get("report_dir", "./reports"))
        self.skip_mail = tk.BooleanVar(value=False)
        self.license_customer_name = tk.StringVar(value="")
        self.license_status = tk.StringVar(value="当前状态：正在读取许可证...")
        self.machine_code = tk.StringVar(value="正在读取...")
        self.machine_hash = tk.StringVar(value="正在读取...")
        self.machine_detail = tk.StringVar(value="")

    def _build_ui(self) -> None:
        self._build_header()
        self._build_nav()
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 18))
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.pages["mail"] = self._mail_page(self.content)
        self.pages["rules"] = self._rules_page(self.content)
        self.pages["run"] = self._run_page(self.content)
        self.pages["license"] = self._license_page(self.content)
        self._show_tab("mail" if get_license_status(BASE_DIR).ok else "license")

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=SURFACE, height=112, highlightbackground="#e5ebf4", highlightthickness=1)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        inner = tk.Frame(header, bg=SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=28, pady=22)
        inner.columnconfigure(1, weight=1)

        icon = tk.Label(
            inner,
            text="\uE715",
            font=("Segoe MDL2 Assets", 24),
            fg=PRIMARY,
            bg="#e8f1ff",
            width=2,
            height=1,
            relief=tk.FLAT,
        )
        icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 18), pady=(2, 0), ipady=8)

        tk.Label(inner, text="测风数据邮件日报监测工具", font=(FONT, 18, "bold"), fg=TEXT, bg=SURFACE).grid(row=0, column=1, sticky="sw")
        tk.Label(inner, text="邮件接收、规则配置与日报发送 · 作者：楚煜 · 邮箱：15274958341@163.com", font=(FONT, 10), fg=MUTED, bg=SURFACE).grid(row=1, column=1, sticky="nw", pady=(6, 0))

        actions = tk.Frame(inner, bg=SURFACE)
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self._button(actions, "打开报告目录", self.open_report_dir, icon="\uE8B7", primary=False).pack(side=tk.LEFT, padx=(0, 10))
        self._button(actions, "保存设置", self.save_settings, icon="\uE74E", primary=True).pack(side=tk.LEFT)

    def _build_nav(self) -> None:
        nav = tk.Frame(self, bg=BG, height=60)
        nav.pack(fill=tk.X)
        nav.pack_propagate(False)
        row = tk.Frame(nav, bg=BG)
        row.pack(anchor="w", padx=42, pady=(12, 0))
        for key, label in (
            ("mail", "邮箱设置"),
            ("rules", "日报规则"),
            ("run", "运行"),
            ("license", "授权"),
        ):
            item = tk.Frame(row, bg=BG, cursor="hand2")
            item.pack(side=tk.LEFT, padx=(0, 24))
            text = tk.Label(item, text=label, font=(FONT, 13, "bold"), fg=MUTED, bg=BG, padx=16, pady=10, cursor="hand2")
            text.pack()
            line = tk.Frame(item, bg=BG, height=3)
            line.pack(fill=tk.X, padx=2)
            text.bind("<Button-1>", lambda _event, tab=key: self._show_tab(tab))
            item.bind("<Button-1>", lambda _event, tab=key: self._show_tab(tab))
            self.nav_items[key] = {"label": text, "line": line}
            if key != "license":
                sep = tk.Frame(row, bg="#dbe3ef", width=1, height=24)
                sep.pack(side=tk.LEFT, padx=(0, 24), pady=8)

    def _show_tab(self, tab: str) -> None:
        if tab != "license" and not get_license_status(BASE_DIR).ok:
            tab = "license"
            if hasattr(self, "license_status"):
                self.refresh_license_status()
        self.current_tab = tab
        for key, page in self.pages.items():
            container = getattr(page, "_scroll_container", page)
            if key == tab:
                container.grid(row=0, column=0, sticky="nsew")
            else:
                container.grid_remove()
        for key, item in self.nav_items.items():
            active = key == tab
            item["label"].configure(fg=PRIMARY if active else MUTED)
            item["line"].configure(bg=PRIMARY if active else BG)

    def _mail_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE715", "邮箱连接", "配置邮箱连接信息")
        self._form_row(page, 1, "邮箱账号", self.email_account, "请输入邮箱账号，如 example@qq.com")
        self._form_row(page, 2, "客户端授权码", self.email_auth_code, "请输入客户端授权码/应用专用密码（不是登录密码）", show="*")
        self._form_row(page, 3, "IMAP 服务器", self.imap_server)
        self._form_row(page, 4, "SMTP 服务器", self.smtp_server)

        self._section_header(page, 6, "\uE724", "日报发送", "设置日报邮件的接收与抄送")
        self._form_row(page, 7, "日报接收人", self.receivers, "请输入日报接收人（多个邮箱请用英文逗号分隔）")
        self._form_row(page, 8, "抄送", self.cc, "请输入抄送人（多个邮箱请用英文逗号分隔）")
        self._check_row(page, 9, self.send_email, "运行完成后发送日报邮件")
        self._info_bar(page, 10, f"多个邮箱请用英文逗号分隔。支持自动识别：{supported_provider_text()}。请填写客户端授权码/应用专用密码，不是网页登录密码。")
        return page

    def _rules_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE9D2", "规则参数", "配置文件检查与缺失提醒规则")
        grid = tk.Frame(page, bg=SURFACE)
        grid.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 10))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self._compact_field(grid, 0, 0, "小文件阈值 KB", self.file_size_warning_kb)
        self._compact_field(grid, 0, 1, "连续缺失提醒天数", self.continuous_missing_days)
        self._compact_field(grid, 1, 0, "附件保存目录", self.data_dir, browse=lambda: self._browse_dir(self.data_dir))
        self._compact_field(grid, 1, 1, "日报保存目录", self.report_dir, browse=lambda: self._browse_dir(self.report_dir))

        self._section_header(page, 3, "\uE9D2", "邮件筛选规则", "限定发件人与主题关键词，提升识别准确性")
        text_grid = tk.Frame(page, bg=SURFACE)
        text_grid.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        text_grid.columnconfigure(0, weight=1)
        text_grid.columnconfigure(1, weight=1)
        text_grid.rowconfigure(0, weight=1)
        self.allowed_senders_text = self._text_box(text_grid, 0, 0, "允许发件人（每行一个）", self.allowed_senders.get(), height=7)
        self.subject_keywords_text = self._text_box(text_grid, 0, 1, "主题关键词（每行一个）", self.subject_keywords.get(), height=7)
        page.rowconfigure(4, weight=1, minsize=170)
        self._info_bar(page, 5, "允许发件人与主题关键词支持多行输入，系统将按规则匹配邮件。")
        return page

    def _run_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE787", "运行设置", "设置统计日期并生成日报", icon_bg="#e8f1ff")
        tk.Label(page, text="统计日期", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=1, column=0, sticky="w", pady=(18, 8))
        date_frame = tk.Frame(page, bg=INPUT_BG, highlightbackground=INPUT_BORDER, highlightthickness=1)
        date_frame.grid(row=2, column=0, sticky="w", ipadx=8, ipady=8)
        tk.Label(date_frame, text="\uE787", font=ICON_FONT, fg=MUTED, bg=INPUT_BG).pack(side=tk.LEFT, padx=(4, 8))
        tk.Entry(date_frame, textvariable=self.stat_date, font=(FONT, 13), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, width=38).pack(side=tk.LEFT)

        self._check_row(page, 3, self.skip_mail, "不连接邮箱，仅根据数据库重新生成日报", "勾选后将不读取邮箱，仅基于已有数据生成日报。")
        self._info_bar(page, 4, "点击“立即生成日报”将按当前规则配置，生成所选日期的监测报告。")

        tk.Label(page, text="操作", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=5, column=0, sticky="w", pady=(18, 10))
        actions = tk.Frame(page, bg=SURFACE)
        actions.grid(row=6, column=0, sticky="w")
        self.run_button = self._button(actions, "立即生成日报", self.run_monitor, icon="\uE768", primary=True)
        self.run_button.pack(side=tk.LEFT, padx=(0, 18))
        self._button(actions, "清空日志", self.clear_log, icon="\uE74D", primary=False).pack(side=tk.LEFT)

        tk.Frame(page, bg="#e5ebf4", height=1).grid(row=7, column=0, sticky="ew", pady=18)
        tk.Label(page, text="运行日志", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=8, column=0, sticky="w", pady=(0, 10))
        log_frame = tk.Frame(page, bg=INPUT_BG, highlightbackground=BORDER, highlightthickness=1)
        log_frame.grid(row=9, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=8, wrap="word", font=(FONT, 11), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, padx=18, pady=18)
        log_scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self._set_log_placeholder()
        page.rowconfigure(9, weight=1, minsize=120)
        return page

    def _license_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE72E", "离线授权", "导出本机授权申请文件并导入许可证")
        tk.Label(page, textvariable=self.license_status, font=(FONT, 11, "bold"), fg=PRIMARY, bg=SURFACE, wraplength=820, justify=tk.LEFT).grid(row=1, column=0, columnspan=2, sticky="ew", padx=54, pady=(8, 14))
        self._form_row(page, 2, "客户名称", self.license_customer_name, "请输入授权单位或客户名称")
        self._readonly_row(page, 3, "短设备编号", self.machine_code)
        self._readonly_row(page, 4, "完整设备码", self.machine_hash)

        actions = tk.Frame(page, bg=SURFACE)
        actions.grid(row=5, column=0, columnspan=2, sticky="ew", padx=54, pady=(14, 10))
        action_buttons = [
            self._button(actions, "复制完整设备码", self.copy_machine_hash, icon="\uE8C8", primary=False),
            self._button(actions, "导出授权申请", self.export_license_request_file, icon="\uEDE1", primary=True),
            self._button(actions, "导出续期申请", lambda: self.export_license_change_request_file("renewal"), icon="\uE8BB", primary=False),
            self._button(actions, "导出升级申请", lambda: self.export_license_change_request_file("upgrade"), icon="\uE7C3", primary=False),
            self._button(actions, "导入许可证", self.import_license_placeholder, icon="\uE8E5", primary=False),
        ]
        for index, button in enumerate(action_buttons):
            button.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 12), pady=(0, 10))

        detail = tk.Label(page, textvariable=self.machine_detail, font=(FONT, 10), fg=MUTED, bg=SURFACE, justify=tk.LEFT, wraplength=760)
        detail.grid(row=6, column=0, columnspan=2, sticky="ew", padx=54, pady=(10, 0))
        page.bind("<Configure>", lambda event, label=detail: label.configure(wraplength=max(260, event.width - 120)), add="+")
        self._info_bar(page, 7, "导出的 .req 文件不包含邮箱密码、客户端授权码、业务数据或许可证签名。")
        self.refresh_machine_fingerprint()
        self.refresh_license_status()
        return page

    def _page_frame(self, parent: tk.Frame) -> tk.Frame:
        container = tk.Frame(parent, bg=BG)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(container, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        page = tk.Frame(canvas, bg=SURFACE)
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=4)
        window_id = canvas.create_window((0, 0), window=page, anchor="nw")

        def sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event) -> None:
            canvas.itemconfigure(window_id, width=max(event.width, 1))

        def mousewheel(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        page.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_width)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", mousewheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        setattr(page, "_scroll_container", container)
        return page

    def _section_header(self, parent: tk.Frame, row: int, icon: str, title: str, subtitle: str, icon_bg: str = SURFACE) -> None:
        frame = tk.Frame(parent, bg=SURFACE)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=28, pady=(24 if row == 0 else 18, 8))
        frame.columnconfigure(1, weight=1)
        tk.Label(frame, text=icon, font=("Segoe MDL2 Assets", 18), fg=PRIMARY, bg=icon_bg, width=3).pack(side=tk.LEFT, padx=(0, 10), ipady=6)
        copy = tk.Frame(frame, bg=SURFACE)
        copy.pack(side=tk.LEFT, fill=tk.X)
        tk.Label(copy, text=title, font=(FONT, 16, "bold"), fg=TEXT, bg=SURFACE).pack(anchor="w")
        subtitle_label = tk.Label(copy, text=subtitle, font=(FONT, 10), fg=MUTED, bg=SURFACE, justify=tk.LEFT)
        subtitle_label.pack(anchor="w", pady=(5, 0))
        parent.bind("<Configure>", lambda event, label=subtitle_label: label.configure(wraplength=max(260, event.width - 150)), add="+")

    def _form_row(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar, placeholder: str = "", show: str | None = None) -> None:
        tk.Label(parent, text=label, font=(FONT, 12), fg=TEXT, bg=SURFACE).grid(row=row, column=0, sticky="w", padx=(54, 22), pady=8)
        entry = tk.Entry(parent, textvariable=variable, show=show, font=(FONT, 12), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 28), pady=8, ipady=10)
        entry.configure(highlightbackground=INPUT_BORDER, highlightcolor=PRIMARY, highlightthickness=1, insertbackground=TEXT)
        if placeholder:
            entry.configure(fg=TEXT)

    def _readonly_row(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=label, font=(FONT, 12), fg=TEXT, bg=SURFACE).grid(row=row, column=0, sticky="w", padx=(54, 22), pady=8)
        entry = tk.Entry(parent, textvariable=variable, font=(FONT, 11), fg=TEXT, bg="#f8fafc", relief=tk.FLAT, state="readonly", readonlybackground="#f8fafc")
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 28), pady=8, ipady=10)
        entry.configure(highlightbackground=INPUT_BORDER, highlightcolor=PRIMARY, highlightthickness=1)

    def _compact_field(self, parent: tk.Frame, row: int, column: int, label: str, variable: tk.StringVar, browse=None) -> None:
        cell = tk.Frame(parent, bg=SURFACE)
        cell.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 18, 18 if column == 0 else 0), pady=(0, 18))
        cell.columnconfigure(0, weight=1)
        tk.Label(cell, text=label, font=(FONT, 11, "bold"), fg=TEXT, bg=SURFACE).grid(row=0, column=0, sticky="w", pady=(0, 8))
        box = tk.Frame(cell, bg=INPUT_BG, highlightbackground=INPUT_BORDER, highlightthickness=1)
        box.grid(row=1, column=0, sticky="ew")
        box.columnconfigure(0, weight=1)
        tk.Entry(box, textvariable=variable, font=(FONT, 12), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT).grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        if browse:
            tk.Button(box, text="\uE8B7", font=ICON_FONT, fg=TEXT, bg=INPUT_BG, activebackground="#f1f5f9", relief=tk.FLAT, command=browse, cursor="hand2", width=3).grid(row=0, column=1, sticky="e", padx=(0, 8))

    def _text_box(self, parent: tk.Frame, row: int, column: int, label: str, value: str, height: int) -> tk.Text:
        cell = tk.Frame(parent, bg=SURFACE)
        cell.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 18, 18 if column == 0 else 0))
        cell.columnconfigure(0, weight=1)
        cell.rowconfigure(1, weight=1)
        tk.Label(cell, text=label, font=(FONT, 11, "bold"), fg=TEXT, bg=SURFACE).grid(row=0, column=0, sticky="w", pady=(0, 8))
        box = tk.Frame(cell, bg=INPUT_BG, highlightbackground=INPUT_BORDER, highlightcolor=PRIMARY, highlightthickness=1)
        box.grid(row=1, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        text = tk.Text(box, height=height, wrap="word", font=(FONT, 11), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, padx=12, pady=10)
        scrollbar = tk.Scrollbar(box, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", value)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return text

    def _check_row(self, parent: tk.Frame, row: int, variable: tk.BooleanVar, label: str, help_text: str = "") -> None:
        frame = tk.Frame(parent, bg=SURFACE)
        frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=54, pady=(12, 4))
        check = tk.Checkbutton(frame, variable=variable, bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE, relief=tk.FLAT)
        check.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(frame, text=label, font=(FONT, 12), fg=TEXT, bg=SURFACE).pack(side=tk.LEFT)
        if help_text:
            tk.Label(parent, text=help_text, font=(FONT, 10), fg=MUTED, bg=SURFACE).grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=86, pady=(0, 8))

    def _info_bar(self, parent: tk.Frame, row: int, text: str) -> None:
        bar = tk.Frame(parent, bg=INFO_BG, highlightbackground=INFO_BORDER, highlightthickness=1)
        bar.grid(row=row, column=0, columnspan=2, sticky="ew", padx=28, pady=(20, 24), ipady=9)
        tk.Label(bar, text="\uE946", font=ICON_FONT, fg=PRIMARY, bg=INFO_BG).pack(side=tk.LEFT, padx=(18, 14))
        label = tk.Label(bar, text=text, font=(FONT, 11), fg="#41516d", bg=INFO_BG, justify=tk.LEFT)
        label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        parent.bind("<Configure>", lambda event, target=label: target.configure(wraplength=max(260, event.width - 130)), add="+")

    def _button(self, parent: tk.Widget, text: str, command, icon: str = "", primary: bool = False) -> tk.Button:
        bg = PRIMARY if primary else SURFACE
        fg = "#ffffff" if primary else TEXT
        active = PRIMARY_DARK if primary else "#f1f5f9"
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=(FONT, 12, "bold" if primary else "normal"),
            fg=fg,
            bg=bg,
            activeforeground=fg,
            activebackground=active,
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=9,
            cursor="hand2",
            highlightbackground=INPUT_BORDER,
            highlightthickness=1,
        )

    def save_settings(self) -> None:
        try:
            self._update_config_from_ui()
            save_config(CONFIG_PATH, self.config_data)
            messagebox.showinfo("已保存", "设置已保存。")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _update_config_from_ui(self) -> None:
        int(self.file_size_warning_kb.get())
        int(self.continuous_missing_days.get())
        date.fromisoformat(self.stat_date.get())
        mail_cfg = self.config_data["mail"]
        mail_cfg.update(email_account=self.email_account.get().strip(), email_auth_code=self.email_auth_code.get().strip(), imap_server=self.imap_server.get().strip(), smtp_server=self.smtp_server.get().strip(), imap_port=993, smtp_port=465, use_ssl=True, smtp_starttls=False, type="auto")
        apply_mail_provider_defaults(mail_cfg)
        self.imap_server.set(mail_cfg.get("imap_server", ""))
        self.smtp_server.set(mail_cfg.get("smtp_server", ""))
        self.config_data["report"].update(report_receivers=_split_csv(self.receivers.get()), report_cc=_split_csv(self.cc.get()), send_email=bool(self.send_email.get()), generate_excel=True, generate_html=True, send_time="09:00", statistic_period="previous_day_00_to_24")
        self.config_data["rules"].update(file_size_warning_kb=int(self.file_size_warning_kb.get()), continuous_missing_warning_days=int(self.continuous_missing_days.get()))
        self.config_data["filter"].update(allowed_senders=_split_lines(self.allowed_senders_text.get("1.0", tk.END)), subject_keywords=_split_lines(self.subject_keywords_text.get("1.0", tk.END)), attachment_extensions=[".rld", ".zip", ".txt", ".csv", ".xls", ".xlsx", ".rar"])
        self.config_data["storage"].update(data_dir=self.data_dir.get().strip() or "./data", report_dir=self.report_dir.get().strip() or "./reports", log_dir="./logs", database_path="./database/wind_mail_monitor.db")

    def run_monitor(self) -> None:
        if self.running:
            return
        try:
            require_valid_license(LicenseRequirement(LicenseCheckPoint.MANUAL_REPORT_RUN, "mail_monitor"), BASE_DIR)
            self._update_config_from_ui()
            save_config(CONFIG_PATH, self.config_data)
        except Exception as exc:
            messagebox.showerror("设置有误", str(exc))
            return
        self.running = True
        self.run_button.configure(state=tk.DISABLED)
        self._append_log("开始运行...\n")
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self) -> None:
        if getattr(sys, "frozen", False):
            self._run_worker_in_process()
            return
        command = [_worker_python(), str(BASE_DIR / "main.py"), "--date", self.stat_date.get()]
        if not self.send_email.get():
            command.append("--no-send")
        if self.skip_mail.get():
            command.append("--skip-mail")
        try:
            process = subprocess.Popen(command, cwd=str(BASE_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert process.stdout is not None
            for line in process.stdout:
                self.output_queue.put(line)
            code = process.wait()
            self.output_queue.put("\n运行完成。\n" if code == 0 else f"\n运行失败，退出码：{code}\n")
        except Exception as exc:
            self.output_queue.put(f"\n运行失败：{exc}\n")
        finally:
            self.output_queue.put("__DONE__")

    def _run_worker_in_process(self) -> None:
        argv = ["main.py", "--date", self.stat_date.get()]
        if not self.send_email.get():
            argv.append("--no-send")
        if self.skip_mail.get():
            argv.append("--skip-mail")
        old_argv = sys.argv[:]
        sys.argv = argv
        buffer = StringIO()
        try:
            with redirect_stdout(buffer):
                code = monitor_main.main()
            output = buffer.getvalue()
            if output:
                self.output_queue.put(output)
            self.output_queue.put("\n运行完成。\n" if code == 0 else f"\n运行失败，退出码：{code}\n")
        except Exception as exc:
            output = buffer.getvalue()
            if output:
                self.output_queue.put(output)
            self.output_queue.put(f"\n运行失败：{exc}\n")
            _write_runtime_status(
                {
                    "ok": False,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "has_alert": True,
                    "message": str(exc),
                }
            )
        finally:
            sys.argv = old_argv
            self.output_queue.put("__DONE__")

    def _poll_output(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__DONE__":
                    self.running = False
                    self.run_button.configure(state=tk.NORMAL)
                    self.refresh_alert_icon()
                else:
                    self._append_log(item)
        except queue.Empty:
            pass
        self.after(150, self._poll_output)

    def _set_log_placeholder(self) -> None:
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n\n\n运行日志将显示在这里")
        self.log_text.tag_add("center", "1.0", "end")
        self.log_text.tag_config("center", justify="center", foreground="#a8b2c3", font=(FONT, 12))
        self.log_empty = True

    def _append_log(self, text: str) -> None:
        if self.log_empty:
            self.log_text.delete("1.0", tk.END)
            self.log_empty = False
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def clear_log(self) -> None:
        self._set_log_placeholder()

    def refresh_machine_fingerprint(self) -> None:
        try:
            self.machine_fingerprint = get_machine_fingerprint()
            self.machine_code.set(self.machine_fingerprint.machine_code)
            self.machine_hash.set(self.machine_fingerprint.machine_hash)
            component_names = "、".join(sorted(self.machine_fingerprint.components))
            self.machine_detail.set(
                f"设备名称：{self.machine_fingerprint.device_name}\n"
                f"系统版本：{self.machine_fingerprint.windows_version}\n"
                f"已读取稳定标识：{component_names}"
            )
        except MachineFingerprintError as exc:
            self.machine_fingerprint = None
            self.machine_code.set("无法生成")
            self.machine_hash.set("无法生成")
            self.machine_detail.set(str(exc))
        except Exception as exc:
            self.machine_fingerprint = None
            self.machine_code.set("读取失败")
            self.machine_hash.set("读取失败")
            self.machine_detail.set(f"设备信息读取失败：{exc}")

    def copy_machine_hash(self) -> None:
        value = self.machine_hash.get().strip()
        if not value or value in {"正在读取...", "无法生成", "读取失败"}:
            messagebox.showwarning("无法复制", "当前没有可复制的完整设备码。")
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        messagebox.showinfo("已复制", "完整设备码已复制到剪贴板。")

    def export_license_request_file(self) -> None:
        customer_name = self.license_customer_name.get().strip()
        if not customer_name:
            messagebox.showwarning("请填写客户名称", "导出授权申请前，请先填写客户名称。")
            return
        if self.machine_fingerprint is None:
            self.refresh_machine_fingerprint()
        if self.machine_fingerprint is None:
            messagebox.showerror("无法导出", self.machine_detail.get() or "当前无法生成设备码。")
            return
        target_dir = filedialog.askdirectory(initialdir=str(BASE_DIR), title="选择授权申请保存目录")
        if not target_dir:
            return
        try:
            path = export_license_request(customer_name, Path(target_dir), self.machine_fingerprint)
            messagebox.showinfo("已导出", f"授权申请文件已导出：\n{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def export_license_change_request_file(self, request_type: str) -> None:
        customer_name = self.license_customer_name.get().strip()
        if not customer_name:
            messagebox.showwarning("请填写客户名称", "导出续期或升级申请前，请先填写客户名称。")
            return
        status = get_license_status(BASE_DIR)
        if not status.ok or not status.payload:
            messagebox.showwarning("当前未授权", "续期或升级申请需要先导入当前有效许可证。")
            return
        if self.machine_fingerprint is None:
            self.refresh_machine_fingerprint()
        if self.machine_fingerprint is None:
            messagebox.showerror("无法导出", self.machine_detail.get() or "当前无法生成设备码。")
            return
        target_dir = filedialog.askdirectory(initialdir=str(BASE_DIR), title="选择申请文件保存目录")
        if not target_dir:
            return
        try:
            path = export_license_change_request(customer_name, Path(target_dir), request_type, status.payload, self.machine_fingerprint)
            label = "续期" if request_type == "renewal" else "升级"
            messagebox.showinfo("已导出", f"{label}申请文件已导出：\n{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))

    def import_license_placeholder(self) -> None:
        path = filedialog.askopenfilename(title="选择许可证文件", filetypes=[("许可证文件", "*.lic"), ("所有文件", "*.*")])
        if path:
            try:
                status = import_and_validate_license(Path(path), BASE_DIR)
                if status.ok:
                    self.refresh_license_status()
                    messagebox.showinfo("导入成功", "许可证已导入并验证通过。")
                else:
                    messagebox.showerror("导入失败", status.message)
            except Exception as exc:
                messagebox.showerror("导入失败", str(exc))

    def refresh_license_status(self) -> None:
        status = get_license_status(BASE_DIR)
        if status.ok and status.payload:
            payload = status.payload
            days = status.days_remaining if status.days_remaining is not None else "-"
            self.license_customer_name.set(str(payload.get("customer_name", self.license_customer_name.get())))
            self.license_status.set(
                "当前状态：已授权 | "
                f"客户：{payload.get('customer_name', '')} | "
                f"许可证：{payload.get('license_id', '')} | "
                f"到期：{payload.get('expiry_date', '')} | "
                f"剩余：{days} 天"
            )
        else:
            self.license_status.set(f"当前状态：未授权或许可证无效（{status.message}）")

    def open_report_dir(self) -> None:
        path = BASE_DIR / self.report_dir.get()
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["explorer", str(path)])
        except Exception:
            filedialog.askdirectory(initialdir=str(path))

    def _browse_dir(self, variable: tk.StringVar) -> None:
        initial = BASE_DIR / variable.get()
        selected = filedialog.askdirectory(initialdir=str(initial if initial.exists() else BASE_DIR))
        if selected:
            try:
                variable.set(str(Path(selected).relative_to(BASE_DIR)).replace("\\", "/"))
            except ValueError:
                variable.set(selected)

    def refresh_alert_icon(self) -> None:
        status_path = BASE_DIR / "runtime_status.json"
        alert = False
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                alert = bool(status.get("has_alert") or not status.get("ok", True))
            except Exception:
                alert = False
        if alert != self.alert_icon_active:
            self.alert_icon_active = alert
            self._set_app_icon(alert)


def _worker_python() -> str:
    runtime_python = BASE_DIR / ".runtime" / "python" / "python.exe"
    if runtime_python.exists():
        return str(runtime_python)
    if sys.executable.lower().endswith("pythonw.exe"):
        candidate = Path(sys.executable).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _write_runtime_status(payload: dict) -> None:
    (BASE_DIR / "runtime_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()

