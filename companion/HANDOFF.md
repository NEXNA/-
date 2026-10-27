# 交接 / 当前状态

> 更新时间：2026-10-22 11:05
> 状态：作为 NapCat 的可切换目标保留；切换入口在青叶摩卡控制台。

## 当前架构

- 陪伴工作台：`127.0.0.1:8765`
- 青叶摩卡：`127.0.0.1:8080`
- NapCat 同一时刻只启用一个上报客户端
- 切换入口：青叶摩卡控制台 →「NapCat 路由」
- 本项目只接收 `/napcat/event`，不写 NapCat 配置

## 当前功能

- 登录控制台
- 两套角色：诗蔻蒂 / 伊邪那美
- 网页聊天与历史
- 记忆
- 今日运势
- 亲密度
- 全局开关与机器人设定
- 被选中时，QQ 私聊桥接（`napcat.py`）

## 数据

```text
D:\青叶摩卡的面包坊\companion\data\companion.db
```

## 测试

```powershell
cd D:\青叶摩卡的面包坊\companion
python -m unittest discover -s tests
```

## 注意

不要在陪伴工作台里写 NapCat 配置。  
切换项目、切换 NapCat 登录 QQ，统一在青叶摩卡控制台操作。
