# 测风数据邮件日报监测工具

作者：楚煜  
邮箱：15274958341@163.com

这是一个 Windows 便携版工具，用于读取测风数据邮箱中的邮件和附件，识别测风塔数据接收、缺测、连续缺测、小文件异常和未识别附件，并生成 Excel/HTML 日报。

## 主要功能

- 图形界面配置邮箱、日报规则、收件人和统计日期。
- 支持 QQ、163、Gmail、Outlook、126、Foxmail 邮箱自动识别 IMAP/SMTP。
- 同时扫描收件箱和已发送文件夹，并按附件内容去重。
- 支持 `.rld`、`.swift`、`.RWD`、`.dat`、`.zip`、`.txt` 六种测风数据格式。
- 支持离线授权、续期申请、升级申请和许可证导入。
- 支持按允许发件人、主题关键词、附件名称和附件扩展名筛选邮件。
- 支持附件名前 6 位数字识别测风塔数据。
- 支持从附件名、邮件主题和附件内容识别历史日期。
- 支持多次运行去重，避免同一天数据重复进入日报。
- 根据历史已出现塔号判断缺测，首次统计即可显示缺测结果。
- 生成 Excel 和 HTML 日报，可选择发送日报邮件。
- 异常数据或运行失败后，软件图标显示红色感叹号。
- 文件低于固定大小阈值，或低于同一测风塔历史正常附件平均大小的 80% 时，标记为异常。
- 可配置“无效塔号”；倒塔或停用后不再保存其附件，也不再产生缺测、连续缺测或异常提醒。

## 目录结构

```text
config/                       配置模板
docs/                         客户使用手册和授权说明
release/WindMailMonitor-portable.zip
                              可直接解压双击运行的便携版
src/                          核心功能模块
tests/                        单元测试
gui.py                        图形界面入口
main.py                       命令行入口
requirements.txt              依赖说明
wind-mail-monitor-source.zip  源码交付包
```

## 客户直接使用

1. 下载 `release/WindMailMonitor-portable.zip`。
2. 解压后双击 `WindMailMonitor.exe`。
3. 首次使用先在“授权”页面导出授权申请并导入许可证。
4. 在“邮箱设置”页面填写邮箱账号、客户端授权码、日报收件人。
5. 在“日报规则”页面填写允许发件人、主题关键词；倒塔或停用的测风塔填入“无效塔号”。
6. 在“运行”页面选择统计日期，点击“立即生成日报”。
7. 点击“打开报告目录”查看 Excel 和 HTML 日报。

详细说明见：

```text
docs/测风数据邮件日报监测工具_客户使用手册.md
```

## 本地源码运行

开发运行需要 Python 3.10+。

```powershell
copy config\config.example.yaml config\config.yaml
python gui.py
```

命令行生成日报：

```powershell
python main.py --date 2026-07-12 --no-send
```

仅根据已有数据库重新生成日报：

```powershell
python main.py --date 2026-07-12 --skip-mail --no-send
```

## 测试

```powershell
python -m unittest discover -s tests
```

## 安全说明

- 不要提交真实 `config/config.yaml`。
- 不要提交真实邮箱客户端授权码。
- 不要提交 `data/`、`database/`、`logs/`、`reports/` 中的真实业务数据。
- 客户端交付包不得包含内部签发工具、私钥或私钥 seed。
