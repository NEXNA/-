# 部署脚本

## 方案 A：本机双 NapCat

- [A_DUAL_NAPCAT.md](A_DUAL_NAPCAT.md)：端口、QQ、目录、管理入口；
- `start_napcat_companion.ps1`：只启动陪伴 NapCat（6100 / 3001，3848406242）；
- `start_all.ps1`：启动两套 NapCat + 陪伴 + 摩卡 bot；
- `start_companion.ps1`：带崩溃重启的陪伴启动器。

## 方案 B：上云 / 第二台 Windows

- [B_CLOUD.md](B_CLOUD.md)：完整部署步骤和安全要求；
- `.env.cloud.example`：云端 `.env` 模板；
- `package_companion.ps1`：打包（默认不含数据库和 `.env`）；
- `build` 后 zip 在 `dist\`；
- `install_task.ps1`：陪伴开机自启；
- `backup_companion.ps1`：备份数据库和 `.env.secret`。

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File .\package_companion.ps1
```

迁移数据时：

```powershell
powershell -ExecutionPolicy Bypass -File .\package_companion.ps1 -IncludeData
```
