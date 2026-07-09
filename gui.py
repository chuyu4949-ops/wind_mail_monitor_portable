from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tkinter import filedialog, messagebox

import main as monitor_main
from src.config_loader import load_config
from src.config_writer import save_config


BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"

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
        self.title("测风数据邮件日报监测工具")
        self.geometry("1180x820")
        self.minsize(1000, 720)
        self.configure(bg=BG)
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.current_tab = "mail"
        self.nav_items: dict[str, dict[str, tk.Widget]] = {}
        self.pages: dict[str, tk.Frame] = {}
        self.log_empty = True
        self.config_data = load_config(CONFIG_PATH)
        self._build_vars()
        self._build_ui()
        self._poll_output()

    def _build_vars(self) -> None:
        mail = self.config_data["mail"]
        report = self.config_data["report"]
        rules = self.config_data["rules"]
        storage = self.config_data["storage"]
        filters = self.config_data["filter"]
        self.email_account = tk.StringVar(value=mail.get("email_account", ""))
        self.email_auth_code = tk.StringVar(value=mail.get("email_auth_code", ""))
        self.imap_server = tk.StringVar(value=mail.get("imap_server", "imap.163.com"))
        self.smtp_server = tk.StringVar(value=mail.get("smtp_server", "smtp.163.com"))
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

    def _build_ui(self) -> None:
        self._build_header()
        self._build_nav()
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill=tk.BOTH, expand=True, padx=36, pady=(0, 26))
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.pages["mail"] = self._mail_page(self.content)
        self.pages["rules"] = self._rules_page(self.content)
        self.pages["run"] = self._run_page(self.content)
        self._show_tab("mail")

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=SURFACE, height=136, highlightbackground="#e5ebf4", highlightthickness=1)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        inner = tk.Frame(header, bg=SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=38, pady=30)
        inner.columnconfigure(1, weight=1)

        icon = tk.Label(
            inner,
            text="\uE715",
            font=("Segoe MDL2 Assets", 28),
            fg=PRIMARY,
            bg="#e8f1ff",
            width=2,
            height=1,
            relief=tk.FLAT,
        )
        icon.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 18), pady=(2, 0), ipady=8)

        tk.Label(inner, text="测风数据邮件日报监测工具", font=(FONT, 22, "bold"), fg=TEXT, bg=SURFACE).grid(row=0, column=1, sticky="sw")
        tk.Label(inner, text="邮件接收、规则配置与日报发送 · 作者：楚煜", font=(FONT, 12), fg=MUTED, bg=SURFACE).grid(row=1, column=1, sticky="nw", pady=(6, 0))

        actions = tk.Frame(inner, bg=SURFACE)
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self._button(actions, "打开报告目录", self.open_report_dir, icon="\uE8B7", primary=False).pack(side=tk.LEFT, padx=(0, 18))
        self._button(actions, "保存设置", self.save_settings, icon="\uE74E", primary=True).pack(side=tk.LEFT)

    def _build_nav(self) -> None:
        nav = tk.Frame(self, bg=BG, height=72)
        nav.pack(fill=tk.X)
        nav.pack_propagate(False)
        row = tk.Frame(nav, bg=BG)
        row.pack(anchor="w", padx=62, pady=(18, 0))
        for key, icon, label in (
            ("mail", "\uE715", "邮箱设置"),
            ("rules", "\uE8FD", "日报规则"),
            ("run", "\uE768", "运行"),
        ):
            item = tk.Frame(row, bg=BG, cursor="hand2")
            item.pack(side=tk.LEFT, padx=(0, 24))
            text = tk.Label(item, text=f"{icon}  {label}", font=(FONT, 13, "bold"), fg=MUTED, bg=BG, padx=16, pady=10, cursor="hand2")
            text.pack()
            line = tk.Frame(item, bg=BG, height=3)
            line.pack(fill=tk.X, padx=2)
            text.bind("<Button-1>", lambda _event, tab=key: self._show_tab(tab))
            item.bind("<Button-1>", lambda _event, tab=key: self._show_tab(tab))
            self.nav_items[key] = {"label": text, "line": line}
            if key != "run":
                sep = tk.Frame(row, bg="#dbe3ef", width=1, height=24)
                sep.pack(side=tk.LEFT, padx=(0, 24), pady=8)

    def _show_tab(self, tab: str) -> None:
        self.current_tab = tab
        for key, page in self.pages.items():
            if key == tab:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        for key, item in self.nav_items.items():
            active = key == tab
            item["label"].configure(fg=PRIMARY if active else MUTED)
            item["line"].configure(bg=PRIMARY if active else BG)

    def _mail_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE715", "邮箱连接", "配置 163 邮箱连接信息")
        self._form_row(page, 1, "163 邮箱账号", self.email_account, "请输入 163 邮箱账号")
        self._form_row(page, 2, "客户端授权码", self.email_auth_code, "请输入客户端授权码（不是登录密码）", show="*")
        self._form_row(page, 3, "IMAP 服务器", self.imap_server)
        self._form_row(page, 4, "SMTP 服务器", self.smtp_server)

        self._section_header(page, 6, "\uE724", "日报发送", "设置日报邮件的接收与抄送")
        self._form_row(page, 7, "日报接收人", self.receivers, "请输入日报接收人（多个邮箱请用英文逗号分隔）")
        self._form_row(page, 8, "抄送", self.cc, "请输入抄送人（多个邮箱请用英文逗号分隔）")
        self._check_row(page, 9, self.send_email, "运行完成后发送日报邮件")
        self._info_bar(page, 10, "多个邮箱请用英文逗号分隔。163 邮箱请填写客户端授权码，不是登录密码。")
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
        self.allowed_senders_text = self._text_box(text_grid, 0, 0, "允许发件人（每行一个）", self.allowed_senders.get(), height=7)
        self.subject_keywords_text = self._text_box(text_grid, 0, 1, "主题关键词（每行一个）", self.subject_keywords.get(), height=7)
        page.rowconfigure(4, weight=1)
        self._info_bar(page, 5, "允许发件人与主题关键词支持多行输入，系统将按规则匹配邮件。")
        return page

    def _run_page(self, parent: tk.Frame) -> tk.Frame:
        page = self._page_frame(parent)
        self._section_header(page, 0, "\uE787", "运行设置", "设置统计日期并生成日报", icon_bg="#e8f1ff")
        tk.Label(page, text="统计日期", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=1, column=0, sticky="w", pady=(20, 8))
        date_frame = tk.Frame(page, bg=INPUT_BG, highlightbackground=INPUT_BORDER, highlightthickness=1)
        date_frame.grid(row=2, column=0, sticky="w", ipadx=8, ipady=8)
        tk.Label(date_frame, text="\uE787", font=ICON_FONT, fg=MUTED, bg=INPUT_BG).pack(side=tk.LEFT, padx=(4, 8))
        tk.Entry(date_frame, textvariable=self.stat_date, font=(FONT, 13), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, width=38).pack(side=tk.LEFT)

        self._check_row(page, 3, self.skip_mail, "不连接邮箱，仅根据数据库重新生成日报", "勾选后将不读取邮箱，仅基于已有数据生成日报。")
        self._info_bar(page, 4, "点击“立即生成日报”将按当前规则配置，生成所选日期的监测报告。")

        tk.Label(page, text="操作", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=5, column=0, sticky="w", pady=(22, 10))
        actions = tk.Frame(page, bg=SURFACE)
        actions.grid(row=6, column=0, sticky="w")
        self.run_button = self._button(actions, "立即生成日报", self.run_monitor, icon="\uE768", primary=True)
        self.run_button.pack(side=tk.LEFT, padx=(0, 18))
        self._button(actions, "清空日志", self.clear_log, icon="\uE74D", primary=False).pack(side=tk.LEFT)

        tk.Frame(page, bg="#e5ebf4", height=1).grid(row=7, column=0, sticky="ew", pady=24)
        tk.Label(page, text="运行日志", font=(FONT, 13, "bold"), fg=TEXT, bg=SURFACE).grid(row=8, column=0, sticky="w", pady=(0, 10))
        self.log_text = tk.Text(page, height=8, wrap="word", font=(FONT, 11), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, padx=18, pady=18)
        self.log_text.grid(row=9, column=0, sticky="nsew")
        self.log_text.configure(highlightbackground=BORDER, highlightthickness=1)
        self._set_log_placeholder()
        page.rowconfigure(9, weight=1)
        return page

    def _page_frame(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=0)
        return page

    def _section_header(self, parent: tk.Frame, row: int, icon: str, title: str, subtitle: str, icon_bg: str = SURFACE) -> None:
        frame = tk.Frame(parent, bg=SURFACE)
        frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=28, pady=(24 if row == 0 else 18, 8))
        tk.Label(frame, text=icon, font=("Segoe MDL2 Assets", 18), fg=PRIMARY, bg=icon_bg, width=3).pack(side=tk.LEFT, padx=(0, 10), ipady=6)
        copy = tk.Frame(frame, bg=SURFACE)
        copy.pack(side=tk.LEFT, fill=tk.X)
        tk.Label(copy, text=title, font=(FONT, 16, "bold"), fg=TEXT, bg=SURFACE).pack(anchor="w")
        tk.Label(copy, text=subtitle, font=(FONT, 10), fg=MUTED, bg=SURFACE).pack(anchor="w", pady=(5, 0))

    def _form_row(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar, placeholder: str = "", show: str | None = None) -> None:
        tk.Label(parent, text=label, font=(FONT, 12), fg=TEXT, bg=SURFACE).grid(row=row, column=0, sticky="w", padx=(54, 22), pady=8)
        entry = tk.Entry(parent, textvariable=variable, show=show, font=(FONT, 12), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 28), pady=8, ipady=10)
        entry.configure(highlightbackground=INPUT_BORDER, highlightcolor=PRIMARY, highlightthickness=1, insertbackground=TEXT)
        if placeholder:
            entry.configure(fg=TEXT)

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
        text = tk.Text(cell, height=height, wrap="word", font=(FONT, 11), fg=TEXT, bg=INPUT_BG, relief=tk.FLAT, padx=12, pady=10)
        text.insert("1.0", value)
        text.configure(highlightbackground=INPUT_BORDER, highlightcolor=PRIMARY, highlightthickness=1)
        text.grid(row=1, column=0, sticky="nsew")
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
        tk.Label(bar, text=text, font=(FONT, 11), fg="#41516d", bg=INFO_BG).pack(side=tk.LEFT)

    def _button(self, parent: tk.Widget, text: str, command, icon: str = "", primary: bool = False) -> tk.Button:
        bg = PRIMARY if primary else SURFACE
        fg = "#ffffff" if primary else TEXT
        active = PRIMARY_DARK if primary else "#f1f5f9"
        return tk.Button(
            parent,
            text=f"{icon}  {text}" if icon else text,
            command=command,
            font=(FONT, 12, "bold" if primary else "normal"),
            fg=fg,
            bg=bg,
            activeforeground=fg,
            activebackground=active,
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=11,
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
        self.config_data["mail"].update(email_account=self.email_account.get().strip(), email_auth_code=self.email_auth_code.get().strip(), imap_server=self.imap_server.get().strip(), smtp_server=self.smtp_server.get().strip(), imap_port=993, smtp_port=465, use_ssl=True, type="163_personal")
        self.config_data["report"].update(report_receivers=_split_csv(self.receivers.get()), report_cc=_split_csv(self.cc.get()), send_email=bool(self.send_email.get()), generate_excel=True, generate_html=True, send_time="09:00", statistic_period="previous_day_00_to_24")
        self.config_data["rules"].update(file_size_warning_kb=int(self.file_size_warning_kb.get()), continuous_missing_warning_days=int(self.continuous_missing_days.get()))
        self.config_data["filter"].update(allowed_senders=_split_lines(self.allowed_senders_text.get("1.0", tk.END)), subject_keywords=_split_lines(self.subject_keywords_text.get("1.0", tk.END)), attachment_extensions=[".rld", ".zip", ".txt", ".csv", ".xls", ".xlsx", ".rar"])
        self.config_data["storage"].update(data_dir=self.data_dir.get().strip() or "./data", report_dir=self.report_dir.get().strip() or "./reports", log_dir="./logs", database_path="./database/wind_mail_monitor.db")

    def run_monitor(self) -> None:
        if self.running:
            return
        try:
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


def _worker_python() -> str:
    runtime_python = BASE_DIR / ".runtime" / "python" / "python.exe"
    if runtime_python.exists():
        return str(runtime_python)
    if sys.executable.lower().endswith("pythonw.exe"):
        candidate = Path(sys.executable).with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
