# 陪伴工作台 · 工作区说明

项目位于 `D:\青叶摩卡的面包坊\companion`，是一个独立的本地 Web 陪伴聊天控制台，同时可以作为 NapCat 的可切换上报目标。

## 模式

- 创造模式，允许直接读写和运行项目。
- 机器人设定由登录后的「机器人设定」页管理。
- 两套角色卡在 `persona_seed.py`，不要在未确认时删除。

## 边界

- 本项目**不写 NapCat 配置**；
- 只接收 `POST /napcat/event`；
- 切换上报项目、切换 NapCat 登录 QQ，只在青叶摩卡控制台操作；
- 数据只在 `D:\青叶摩卡的面包坊\companion\data\companion.db`；
- 与青叶摩卡不共享聊天、记忆、角色或运势数据。

## 运行

```powershell
cd D:\青叶摩卡的面包坊\companion
python app.py
```

访问 `http://127.0.0.1:8765`。

## 测试

```powershell
python -m unittest discover -s tests
```
