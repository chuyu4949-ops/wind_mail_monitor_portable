# 测风数据邮件日报监测工具

本仓库保存测风数据邮件日报监测工具的源码交付包。

## 文件

- `wind-mail-monitor-source.zip`：已清理源码包，包含 GUI、命令行入口、核心模块、测试和示例配置。
- `src/mail_client.py`：网易 163/188 邮箱 IMAP ID 兼容修复后的邮件读取模块，可直接在线查看关键修复代码。

## 网易邮箱兼容

已按网易邮箱客服要求，在 IMAP 登录成功后发送 RFC 2971 IMAP ID 信息：

- `name`: `wind-mail-monitor`
- `version`: `1.0.1`
- `vendor`: `Codex local app`
- `support-email`: `support@example.com`

Python 标准库 `imaplib` 默认没有公开 ID 命令，因此代码中注册了 `imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))`，再调用 `_simple_command("ID", payload)` 发送客户端信息。

同时兼容处理了部分网易邮件头返回 `unknown-8bit` 导致标题解码失败的问题。

## 安全说明

源码包不包含本地运行时、日志、数据库、下载附件、日报文件或真实邮箱授权码。

本地真实配置文件 `config/config.yaml` 不应提交到 GitHub；请使用源码包中的 `config/config.example.yaml` 作为模板。

## 验证

上传前已执行：

```powershell
python -m unittest discover -s tests
```

结果：3 个测试全部通过。

本地便携版已用真实 IMAP 读取流程验证：可登录邮箱、发送 IMAP ID、搜索候选邮件、保存附件并生成 Excel/HTML 日报。验证发送日报邮件时可先勾选“不发送日报邮件”做预览。
