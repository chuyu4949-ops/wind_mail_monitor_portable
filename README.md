# 测风数据邮件日报监测工具

本仓库保存测风数据邮件日报监测工具的源码交付包。

## 文件

- `wind-mail-monitor-source.zip`：已清理源码包，包含 GUI、命令行入口、核心模块、测试和示例配置。

## 安全说明

源码包不包含本地运行时、日志、数据库、下载附件、日报文件或真实邮箱授权码。

本地真实配置文件 `config/config.yaml` 不应提交到 GitHub；请使用源码包中的 `config/config.example.yaml` 作为模板。

## 验证

上传前已执行：

```powershell
python -m unittest discover -s tests
```

结果：3 个测试全部通过。
