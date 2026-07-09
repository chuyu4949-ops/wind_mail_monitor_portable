# 测风数据邮件日报监测工具

作者：楚煜

Windows 本地便携工具，用于读取 163/188 邮箱中的测风数据邮件，下载并记录附件，按规则识别缺失与异常，生成 Excel/HTML 日报，并可选择通过 SMTP 发送日报邮件。

## 功能

- 图形界面配置邮箱、筛选规则、日报收件人与运行日期
- 支持 163/188 邮箱 IMAP/SMTP，包含网易 IMAP ID 兼容修复
- 按发件人、主题关键词、附件扩展名筛选邮件
- 支持 `.rld`、Molas B300 `.zip` 以及常见表格/文本附件
- SQLite 保存邮件、附件和每日状态
- 识别小文件、缺失数据和连续缺失风险
- 生成 Excel 和 HTML 日报
- 可选择只生成本地日报，不发送邮件

## 目录

```text
config/                       配置模板
docs/                         使用说明书
release/WindMailMonitor-portable.zip
                               可直接解压双击运行的便携版
src/                          核心功能模块
tests/                        单元测试
gui.py                        图形界面入口
main.py                       命令行入口
requirements.txt              依赖说明
wind-mail-monitor-source.zip  源码交付包
```

## 直接使用

1. 下载 `release/WindMailMonitor-portable.zip`。
2. 解压后双击 `WindMailMonitor.exe`。
3. 在界面中填写 163/188 邮箱账号、客户端授权码、日报接收人和筛选规则。
4. 点击 `保存设置`。
5. 在 `运行` 页选择统计日期并点击 `立即生成日报`。

详细说明见：

```text
docs/测风数据邮件日报监测工具说明书.md
```

## 本地源码运行

开发运行需要 Python 3.10+。

```powershell
copy config\config.example.yaml config\config.yaml
python gui.py
```

命令行生成日报：

```powershell
python main.py --date 2026-07-08 --no-send
```

仅根据数据库重新生成日报：

```powershell
python main.py --date 2026-07-08 --skip-mail --no-send
```

## 测试

```powershell
python -m unittest discover -s tests
```

## 安全说明

- `config/config.yaml` 会保存本地邮箱账号和客户端授权码，请勿提交到 GitHub。
- `data/`、`database/`、`logs/`、`reports/` 为本地运行数据目录，请勿提交真实业务数据。
- 客户端授权码不是网页登录密码，请在邮箱网页端开启 IMAP/SMTP 后生成。
