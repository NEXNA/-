# 方案 A：本机双 NapCat 双 QQ

当前已按这个结构拆分：

| 项目 | NapCat 目录 | WebUI | OneBot HTTP | QQ | 应用 |
|---|---|---|---|---|---|
| 青叶摩卡 | `D:\NapCat.Shell.Windows.OneKey\NapCat.52230.Shell` | `6099` | `3000` | `3826300285` | `8080` |
| 陪伴工作台 | `D:\NapCatCompanion\NapCat.52230.Shell` | `6100` | `3001` | `3848406242` | `8765` |

两个 NapCat 各自有独立配置目录、端口和 QQ，不再互相改写。

## 陪伴工作台配置

`companion/.env`：

```env
NAPCAT_API_URL=http://127.0.0.1:3001
NAPCAT_BOT_QQ=3848406242
NAPCAT_OWNER_QQ=10001
NAPCAT_EVENT_TOKEN=<事件token>
COMPANION_PUBLIC_URL=http://127.0.0.1:8765
```

陪伴的 NapCat 只启用一个 HTTP 客户端：

```text
http://127.0.0.1:8765/napcat/event?token=<事件token>
```

摩卡的 NapCat 只启用：

```text
http://127.0.0.1:8080/event?token=<摩卡token>
```

## 启动

摩卡 NapCat：

```powershell
D:\NapCat.Shell.Windows.OneKey\NapCat.52230.Shell\NapCatWinBootMain.exe 3826300285
```

陪伴 NapCat：

```powershell
D:\NapCatCompanion\NapCat.52230.Shell\NapCatWinBootMain.exe 3848406242
```

陪伴应用：

```powershell
cd D:\青叶摩卡的面包坊\companion
python app.py --no-open
```

> 陪伴 app 启动后会每 2 秒轮询一次私聊历史，作为 NapCat HTTP 上报的兜底；
> 即使 6100 的 HTTP 客户端只发心跳，私聊也能触发。

## 管理

- 摩卡 NapCat：<http://127.0.0.1:6099>
- 陪伴 NapCat：<http://127.0.0.1:6100>
- 摩卡控制台「QQ 扫码登录」只管摩卡（6099）；
- 陪伴换 QQ 用 6100 WebUI，或改 `D:\NapCatCompanion\...\napcat.quick.bat` 后重启；
- **不要再点「NapCat 路由」把摩卡切到陪伴**；现在不需要切。

## 注意

- 两份 NapCat 共用 `C:\Users\NEXNA7\AppData\Roaming\QQ` 的 QQ 数据目录，升级/清理 QQ 时注意不要误删；
- 两个 QQ 同时在线会占更多内存；
- 如果 6100 提示“当前账号已登录”，说明两个实例用了同一个 QQ，改 quick bat 为另一个号；
- 重启电脑后，两个 NapCat 需要分别启动；可用计划任务或启动脚本。
