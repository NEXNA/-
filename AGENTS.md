# 青叶摩卡 · 陪伴工作台

当前统一项目根目录：

```text
D:\青叶摩卡的面包坊
```

## 目录

- `bot/`、`control_panel.py`、`prompts/`、`data/`：青叶摩卡 QQ bot 和 Tkinter 控制台。
- `companion/`：陪伴工作台（独立 Web 控制台，端口 8765）。
- `companion/data/companion.db`：陪伴工作台自己的账号、角色、聊天、记忆、亲密度、运势。
- `companion/design/character_bible.md`：诗蔻蒂 / 伊邪那美 / 摩卡对照的角色资料与正常人语言设计。
- `companion/archive/napcat-integration/`：已归档的旧 NapCat 写配置脚本，不参与运行。
- `deploy/`：双 NapCat 说明（A）、云端部署包（B）、启动/备份脚本。
- `voice_samples/`：`mocha_ref.wav` 是从 BanG Dream! 摩卡视频分离出的克隆参考；`mocha_cv` 已注册。`mocha_v1/v2/v3.wav` 是早期 VoiceDesign 试听样本。
- `D:\NapCatCompanion\NapCat.52230.Shell`：陪伴工作台专用 NapCat。

## 设计入口

- 摩卡控制台：`control_panel.bat` 或桌面「青叶摩卡控制台」。
  - 「项目白名单」：分别管理两个项目的私聊账号 / 群白名单。
  - 「项目设计」：启动/停止/打开陪伴工作台，查看两套 NapCat 端口。
  - 「QQ 扫码登录」：只管理摩卡 NapCat（6099）。
- 陪伴工作台：`http://127.0.0.1:8765`
  - 两套角色、角色设定、记忆、今日运势、亲密度。
  - 私聊 `/面板` 打开文字功能面板；网页 `/panel` 打开完整面板。
  - 支持发图识图；`/搜 关键词` 查最新信息。

## 双 NapCat

| 项目 | WebUI | OneBot HTTP | QQ | 应用 |
|---|---|---|---|---|
| 青叶摩卡 | 6099 | 3000 | 3826300285 | 8080 |
| 陪伴工作台 | 6100 | 3001 | 3848406242 | 8765 |

## 边界

- 两个项目数据不混用；
- 两套 NapCat 各自独立，不再切换上报目标；
- 陪伴工作台只接收自己的 `/napcat/event`，不写摩卡配置；
- 不要从 `companion/archive/` 重新运行旧配置脚本；
- 上云前先看 `deploy/B_CLOUD.md`，不要把 `.env` 打进公开包。
