# 陪伴工作台 · Companion Studio

独立运行的本地陪伴聊天控制台。

```text
D:\青叶摩卡的面包坊\companion
http://127.0.0.1:8765
```

## 独立 NapCat

本项目使用自己的 NapCat，不再和青叶摩卡抢上报：

```text
陪伴 NapCat：6100 / 3001
陪伴应用：8765
摩卡 NapCat：6099 / 3000
摩卡应用：8080
```

- 陪伴 `.env` 的 `NAPCAT_API_URL` 指向 `http://127.0.0.1:3001`；
- 陪伴 NapCat 只上报到 `http://127.0.0.1:8765/napcat/event`；
- 另外每 2 秒轮询一次私聊历史，HTTP 上报只发心跳时也能兜底回复；
- 数据只写 `D:\青叶摩卡的面包坊\companion\data\companion.db`；
- 不共享聊天、记忆、角色或运势数据；
- 不再需要「NapCat 路由」切换。

详见 [ISOLATION.md](ISOLATION.md) 和 `deploy/A_DUAL_NAPCAT.md`。

## 功能

- 登录控制台（单管理员）
- 两套可切换的机器人角色
- 网页聊天和历史
- 长期记忆：自动记住自述、手动添加、删除、清空
- 今日运势：按日期确定性生成，娱乐性质
- 亲密度：0–100，可开关、可设置
- 机器人设定：名字、人设/system prompt、开场白、模型、温度、最大 token
- **QQ 私聊**：作为 NapCat 目标时接收私聊
- **识图**：私聊/群聊发图，配一句问题即可；模型直接看图
- **最新信息**：命中最新/版本/活动/公告等关键词时自动检索网页；也可 `/搜 关键词`
- **QQ 群聊**：被 @ 或消息里叫到角色名时回复；群白名单可在摩卡控制台管理
- **私人账号 / 群白名单**：由摩卡控制台「项目白名单」页分别管理

## 角色设计

- [角色资料库](design/character_bible.md)：诗蔻蒂 / 伊邪那美 / 青叶摩卡（摩卡只对照，不修改）
- 诗蔻蒂、伊邪那美已改为**现代正常人口语**：
  - 默认 1–3 句，不每句省略号；
  - 不堆古风、不背情话；
  - 用具体细节表达在意，可接梗、可短评；
  - 认真/危险时才切换短硬语气。
- 青叶摩卡保持原样，不改人格和口癖。

网页「角色资料」页可以直接看这份设计库。

## 启动

双击：

```text
start.bat
```

或：

```powershell
cd D:\青叶摩卡的面包坊\companion
python app.py
```

启动后打开：

```text
http://127.0.0.1:8765
```

首次使用会进入创建管理员账号；如果数据库里已有账号，直接登录。

## 文件

```text
D:\青叶摩卡的面包坊\companion\
├─ app.py               HTTP 服务、登录、聊天 API
├─ chat_engine.py       聊天与提示词
├─ db.py                SQLite 存储
├─ ui.py                页面与样式
├─ llm.py               DeepSeek 客户端
├─ fortune.py           每日运势
├─ persona_seed.py      两套角色卡
├─ design/
│  └─ character_bible.md 人物资料、经历、行为和语言设计
├─ napcat.py            QQ 私聊事件接收（只读配置，不修改 NapCat）
├─ start.bat            启动
├─ .env                 DeepSeek Key、NapCat 事件 token
├─ ISOLATION.md         项目隔离与切换约定
├─ archive/napcat-integration/
│  └─ 旧的账号切换/写配置脚本（归档，不参与运行）
└─ data/
   └─ companion.db      账号、角色、聊天、记忆、亲密度、运势
```

## 测试

```powershell
python -m unittest discover -s tests
```

当前测试覆盖建库、登录、角色切换、记忆、亲密度、运势、Web 聊天、群聊桥接和面板。

## 注意

- `.env` 和 `data/` 不要外传；
- 服务只绑本机，不要直接暴露公网；
- 陪伴使用 6100 / 3001 的独立 NapCat，不要再改摩卡的 6099 / 3000；
- 云端部署看 `deploy/B_CLOUD.md`，打包用 `deploy/package_companion.ps1`。
