# astrbot_plugin_xiaowo_bridge · 小窝桥接插件

> 给自建聊天 App [小窝](../xiaowo) 用的 AstrBot 插件：QQ 资料管理 Web API + 桌面文件与截屏 LLM 工具。
> AstrBot plugin for the self-hosted [Xiaowo](../xiaowo) chat app: QQ profile Web APIs + desktop file & screenshot tools.

[中文](#中文) · [English](#english)

---

## 中文

### 功能

**Web API**（dashboard 鉴权，供自建前端调用）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/plug/astrbot_plugin_xiaowo_bridge/signature` | 读取 / 修改 QQ 个性签名（`set_self_longnick`） |
| POST | `/api/plug/astrbot_plugin_xiaowo_bridge/avatar` | 更换 QQ 头像（支持 `base64://`，`set_qq_avatar`） |
| GET | `/api/plug/astrbot_plugin_xiaowo_bridge/status` | 签名/头像最近更新记录 |

**LLM 工具**（函数调用，AI 可直接使用）
| 工具 | 作用 |
|---|---|
| `list_desktop_files(keyword)` | 列出桌面文件（按修改时间排序） |
| `send_desktop_file(filename)` | 把桌面文件作为附件发给用户 |
| `screenshot_desktop()` | 截取当前桌面画面发给用户 |

> 桌面范围锁死 `~/OneDrive/Desktop`（无 OneDrive 时回退 `~/Desktop`），只读 + 发送，不做任何监控。

### 安装

放入 AstrBot 的 `data/plugins/` 目录，重启 AstrBot 即可。依赖：`aiocqhttp` 平台（NapCat 等）。

### 配套

- 主应用：[小窝](../xiaowo)
- AstrBot：https://github.com/AstrBotDevs/AstrBot

### 许可

MIT

---

## English

### Features

**Web APIs** (dashboard auth, for custom front-ends)
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/plug/astrbot_plugin_xiaowo_bridge/signature` | Read / update the QQ signature (`set_self_longnick`) |
| POST | `/api/plug/astrbot_plugin_xiaowo_bridge/avatar` | Change the QQ avatar (`set_qq_avatar`, `base64://` supported) |
| GET | `/api/plug/astrbot_plugin_xiaowo_bridge/status` | Last update records |

**LLM tools** (function calling)
| Tool | Purpose |
|---|---|
| `list_desktop_files(keyword)` | List desktop files (newest first) |
| `send_desktop_file(filename)` | Send a desktop file as an attachment |
| `screenshot_desktop()` | Capture and send a desktop screenshot |

> Desktop scope is locked to `~/OneDrive/Desktop` (falls back to `~/Desktop`); read + send only, no monitoring.

### Install

Copy into AstrBot's `data/plugins/` and restart. Requires the `aiocqhttp` platform (NapCat etc.).

### Related

- Main app: [Xiaowo](../xiaowo)
- AstrBot: https://github.com/AstrBotDevs/AstrBot

### License

MIT
