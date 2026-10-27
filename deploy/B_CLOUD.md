# 方案 B：陪伴工作台上云 / 第二台 Windows

目标：让陪伴工作台拥有自己的 NapCat + QQ，不再和摩卡抢配置。

```text
本机                              云端 / 第二台 Windows
摩卡 bot 8080                     陪伴工作台 8765
NapCat 6099 / 3000                NapCat 6100 / 3001
QQ 3826300285（摩卡）             QQ 3848406242（陪伴/或另一个专属号）
```

> 只上传 `companion` 而不上传 NapCat/QQ，不能真正分离。
> 真正的 B 必须是“陪伴工作台 + NapCat + QQ”在同一台云端机器上。

## 服务器要求

- Windows Server 2019/2022 或 Windows 10/11；
- 2 核 4G 起，40G 磁盘；
- 能长期开机；
- 不建议用 Linux/Wine 跑 QQ，登录稳定性差；
- 数据中心 IP 可能触发 QQ 设备验证，优先家里第二台小主机。

## 端口

| 用途 | 地址 |
|---|---|
| 陪伴 Web | `127.0.0.1:8765` |
| 陪伴 NapCat API | `127.0.0.1:3001` |
| 陪伴 NapCat WebUI | `127.0.0.1:6100` |
| 摩卡（保持本机） | `8080 / 3000 / 6099` |

8765 只监听本机，不要直接暴露公网。远程访问用 Tailscale / ZeroTier / RDP。

## 部署步骤

1. 在云端安装 QQ 和 NapCat（Shell 或 Windows 一键版）。
2. 让 NapCat 使用独立目录，配置：
   - HTTP 服务端口 `3001`；
   - WebUI 端口 `6100`；
   - 只启用一个 HTTP 客户端：`http://127.0.0.1:8765/napcat/event?token=<事件token>`。
3. 扫码登录专属 QQ（不要和摩卡共用同一个 QQ）。
4. 把 `companion` 目录复制到云端，例如 `C:\CompanionStudio`。
5. 创建 `.env`（参考 `.env.cloud.example`），填写：
   - DeepSeek Key；
   - `NAPCAT_API_URL=http://127.0.0.1:3001`；
   - `NAPCAT_BOT_QQ`；
   - `NAPCAT_OWNER_QQ`；
   - `NAPCAT_EVENT_TOKEN`；
   - `COMPANION_PUBLIC_URL`（Tailscale 地址或本机地址）。
6. 启动：
   ```powershell
   cd C:\CompanionStudio
   python app.py --no-open
   ```
   陪伴 app 会每 2 秒轮询私聊历史作为 HTTP 上报兜底；NapCat 的 HTTP 客户端如果只发心跳，也能触发私聊。
7. 打开 `http://127.0.0.1:8765` 创建管理员、设置角色、绑定 QQ。
8. 用 `deploy/install_task.ps1` 配开机自启，用 `deploy/backup.ps1` 定时备份。

## 从本机迁移数据

需要迁移：

```text
companion/data/companion.db
companion/.env
```

不要迁移：

```text
__pycache__/
data/server.out.log
data/server.err.log
```

上传前先停陪伴工作台，复制数据库，再上传，避免 SQLite 写一半。

## 安全

- `8765` 只绑 `127.0.0.1`；
- 不要把 WebUI token、Bot token、DeepSeek Key 发到群里；
- 云端 Windows 登录密码要强；
- 开 RDP 时限制来源 IP；
- 定期备份 `companion.db`；
- 不要把 `.env` 打进 zip 发给别人。

## 上线前检查

- [ ] QQ 能在云端长期在线，不频繁设备验证；
- [ ] `http://127.0.0.1:3001/get_login_info` 能返回正确 QQ；
- [ ] 陪伴 Web `8765` 能登录；
- [ ] 私聊能收发；
- [ ] 群聊 @ 能回复；
- [ ] 自动启动和备份都验证过；
- [ ] 本机摩卡仍只连自己的 `3000 / 6099`。
