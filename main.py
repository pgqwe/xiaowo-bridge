"""小窝桥接插件。

为小窝（自建聊天 App）与 DeepSeek 提供两层能力：
- Web API（dashboard 鉴权）：读取/修改 QQ 个性签名、更换 QQ 头像
- LLM 工具：列出桌面文件、发送桌面文件、截屏桌面发给用户（范围锁死桌面，只读+发送）
"""

import base64
import io
import json
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Image
from astrbot.api.star import Context, Star, StarTools

try:
    from quart import request as _quart_request
except Exception:
    _quart_request = None

_onedrive_desk = Path.home() / "OneDrive" / "Desktop"
DESKTOP = _onedrive_desk if _onedrive_desk.exists() else (Path.home() / "Desktop")
STATE_PATH = Path(__file__).parent / "state.json"
ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_SEND_BYTES = 200 * 1024 * 1024


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class XiaowoBridge(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._register_web_apis()

    # ---------- 状态 ----------
    def _load(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, d: dict) -> None:
        STATE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 客户端 ----------
    def _client(self):
        try:
            platform = self.context.get_platform("aiocqhttp")
        except Exception:
            platform = None
        if platform is not None and hasattr(platform, "get_client"):
            try:
                return platform.get_client()
            except Exception:
                pass
        for p in self.context.platform_manager.platform_insts:
            if hasattr(p, "get_client"):
                try:
                    return p.get_client()
                except Exception:
                    continue
        return None

    # ---------- Web API ----------
    def _register_web_apis(self) -> None:
        entries = [
            ("/astrbot_plugin_xiaowo_bridge/signature", self.api_signature, ["GET", "POST"], "小窝签名"),
            ("/astrbot_plugin_xiaowo_bridge/avatar", self.api_avatar, ["POST"], "小窝头像"),
            ("/astrbot_plugin_xiaowo_bridge/status", self.api_status, ["GET"], "小窝状态"),
        ]
        for entry in entries:
            route, handler, methods, desc = entry
            logger.info(f"[xiaowo_bridge] register {route} {methods}")
            self.context.register_web_api(route, handler, methods, desc)

    async def _json_body(self) -> dict:
        if _quart_request is None:
            return {}
        try:
            data = await _quart_request.get_json(silent=True)
        except TypeError:
            data = await _quart_request.get_json()
        return data if isinstance(data, dict) else {}

    async def api_signature(self):
        if _quart_request is not None and _quart_request.method == "POST":
            body = await self._json_body()
            sig = str(body.get("signature") or "").strip()
            if not sig:
                return {"ok": False, "message": "签名是空的"}
            if len(sig) > 40:
                return {"ok": False, "message": "签名超过 40 字"}
            client = self._client()
            if client is None:
                return {"ok": False, "message": "QQ 客户端未连接"}
            try:
                await client.call_action("set_self_longnick", longNick=sig)
            except Exception as exc:
                logger.error(f"[xiaowo_bridge] set signature failed: {exc}")
                return {"ok": False, "message": f"设置失败: {exc}"}
            st = self._load()
            st["signature"] = sig
            st["signature_updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            self._save(st)
            return {"ok": True, "message": "签名已更新", "data": {"signature": sig}}
        return {"ok": True, "data": self._load()}

    async def api_avatar(self):
        body = await self._json_body()
        source = str(body.get("image") or "")
        if not source:
            return {"ok": False, "message": "缺少 image（base64 或 URL）"}
        client = self._client()
        if client is None:
            return {"ok": False, "message": "QQ 客户端未连接"}
        file_arg = source
        if source.startswith("data:"):
            b64 = source.split(",", 1)[1]
            file_arg = "base64://" + b64
        try:
            await client.call_action("set_qq_avatar", file=file_arg)
        except Exception as exc:
            logger.error(f"[xiaowo_bridge] set avatar failed: {exc}")
            return {"ok": False, "message": f"设置失败: {exc}"}
        st = self._load()
        st["avatar_updated_at"] = time.strftime("%Y-%m-%d %H:%M")
        self._save(st)
        return {"ok": True, "message": "头像已更换"}

    async def api_status(self):
        return {"ok": True, "data": self._load()}

    # ---------- LLM 工具：桌面文件 ----------
    def _desktop_real(self) -> Path:
        try:
            return DESKTOP.resolve()
        except OSError:
            return DESKTOP

    def _resolve_desktop(self, rel: str) -> tuple[Path | None, str]:
        root = self._desktop_real()
        p = (root / rel).resolve() if rel else root
        try:
            p.relative_to(root)
        except ValueError:
            return None, "路径越出了桌面范围，拒绝访问"
        if not p.exists():
            return None, "文件不存在"
        if not p.is_file():
            return None, "那是一个文件夹，不是文件"
        return p, ""

    @filter.llm_tool(name="list_desktop_files")
    async def list_desktop_files(self, event: AstrMessageEvent, keyword: str = "") -> str:
        """列出电脑桌面上可以发送给用户的文件（按修改时间从新到旧）。

        当用户说"把那个文件发我""我桌面上有什么"但没给准确文件名时，先调用这个，
        再用 send_desktop_file 发送匹配的文件；也可以在用户说不清文件名时配合截屏让用户指认。

        Args:
            keyword(string, optional): 关键词过滤文件名（不区分大小写）；留空列出全部。
        Returns:
            文件清单文本（文件名 + 大小 + 修改时间）。
        """
        root = self._desktop_real()
        if not root.exists():
            return f"桌面目录不可用：{root}"
        needle = str(keyword or "").strip().lower()
        rows = []
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("~$"):
                continue
            if needle and needle not in path.name.lower():
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            rows.append((st.st_mtime, path.name, st.st_size))
        if not rows:
            return "桌面上没有匹配的文件"
        rows.sort(reverse=True)
        lines = [f"桌面共 {len(rows)} 个文件，最近的 30 个："]
        for mtime, name, size in rows[:30]:
            when = time.strftime("%m-%d %H:%M", time.localtime(mtime))
            lines.append(f"- {name}（{_human(size)}，{when}）")
        return "\n".join(lines)

    @filter.llm_tool(name="send_desktop_file")
    async def send_desktop_file(self, event: AstrMessageEvent, filename: str, display_name: str = "") -> str:
        """把电脑桌面上的一个文件发送给当前用户（用户可以在手机上下载）。

        只在用户明确要"发文件/发给我"时调用；一次只发一个文件。文件名先从
        list_desktop_files 或截屏指认里确认。不要向用户复述绝对路径。

        Args:
            filename(string): 桌面上的文件名（或桌面内相对路径），例如 "实习报告.docx"。
            display_name(string, optional): 发送时显示的文件名；不填用原名。
        Returns:
            发送结果；失败时说明原因。
        """
        resolved, error = self._resolve_desktop(str(filename or "").strip())
        if error:
            return f"发文件失败：{error}"
        size = resolved.stat().st_size
        if size > MAX_SEND_BYTES:
            return f"文件太大（{_human(size)}），发不了"
        name = str(display_name or "").strip() or resolved.name
        try:
            await event.send(event.chain_result([File(name=name, file=str(resolved))]))
        except Exception as exc:
            return f"发送失败：{exc}"
        return f"已把 {name} 发给用户"

    @filter.llm_tool(name="screenshot_desktop")
    async def screenshot_desktop(self, event: AstrMessageEvent) -> str:
        """截取当前电脑桌面的画面，作为图片发送给用户。

        当用户要找文件但说不清名字、或想看看电脑当前状态时调用；发送后主动问用户
        "是哪一个？"或需要做什么。

        Args:
            无参数。
        Returns:
            截屏发送结果。
        """
        try:
            from PIL import ImageGrab
        except Exception:
            return "电脑缺少截图组件（Pillow），发不了截屏"
        try:
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            path = Path(__file__).parent / "temp"
            path.mkdir(exist_ok=True)
            out = path / f"screenshot_{int(time.time())}.png"
            out.write_bytes(buf.getvalue())
            await event.send(event.chain_result([Image.fromFileSystem(str(out))]))
            try:
                out.unlink()
            except OSError:
                pass
        except Exception as exc:
            return f"截屏失败：{exc}"
        return "截屏已发送给用户。请用户指认目标文件或说明需求。"


