"""
opencode 会话更新监控通知脚本

独立运行，监控 opencode.db 中所有会话的更新，检测到 AI 回复完毕
（step_finish + reason=stop）后通过微信 iLink 机器人 API 发送通知。

首次使用需要扫码登录微信机器人，后续自动复用 token。
首次运行后，需要在微信中向该机器人发送任意一条消息，
脚本获取到 context_token 后才能推送通知。
"""

import time
import json
import os
import random
import base64
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from threading import Thread

from db import connect_db
from services.monitor_state import MonitorNotification, find_completed_sessions

# ── 配置 ──────────────────────────────────────────────

DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))
STABLE_WINDOW_MS = int(os.environ.get("MONITOR_STABLE_WINDOW_MS", "1500"))
WECHAT_BASE_URL = "https://ilinkai.weixin.qq.com"
CRED_FILE = Path.home() / ".opencode-monitor-cred.json"

_ctx_token = None
_ctx_user_id = None
_ctx_token_ready = False
_log_file = None


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


def wechat_uin() -> str:
    return base64.b64encode(str(random.getrandbits(32)).encode()).decode()


# ── 微信 iLink API ───────────────────────────────────


def api_call(path: str, data=None, method="GET", headers=None, auth=False):
    url = f"{WECHAT_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if auth:
        hdrs["X-WECHAT-UIN"] = wechat_uin()
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=hdrs, method=method)
    return json.loads(urlopen(req).read())


def fetch_qrcode():
    resp = api_call("/ilink/bot/get_bot_qrcode?bot_type=3")
    return resp["qrcode"], resp["qrcode_img_content"]


def poll_qr_status(qrcode: str):
    hdrs = {"iLink-App-ClientVersion": "1"}
    return api_call(f"/ilink/bot/get_qrcode_status?qrcode={qrcode}", headers=hdrs)


def get_updates(token: str, buf=""):
    body = {"get_updates_buf": buf, "base_info": {"channel_version": "1.0.0"}}
    hdrs = {"Authorization": f"Bearer {token}", "AuthorizationType": "ilink_bot_token"}
    return api_call("/ilink/bot/getupdates", data=body, method="POST", headers=hdrs, auth=True)


def send_wechat_message(token: str, bot_id: str, text: str):
    global _ctx_token, _ctx_user_id
    if not _ctx_token or not _ctx_user_id:
        log("  \u26a0 \u5c1a\u65e0 context_token")
        return False
    payload = {
        "msg": {
            "from_user_id": bot_id,
            "to_user_id": _ctx_user_id,
            "client_id": f"{int(time.time() * 1000)}-monitor",
            "message_type": 2,
            "message_state": 2,
            "context_token": _ctx_token,
            "item_list": [{"type": 1, "text_item": {"text": text}}],
        },
        "base_info": {"channel_version": "1.0.0"},
    }
    hdrs = {"Authorization": f"Bearer {token}", "AuthorizationType": "ilink_bot_token"}
    resp = api_call("/ilink/bot/sendmessage", data=payload, method="POST", headers=hdrs, auth=True)
    if not resp:
        log(f"  \u2717 API \u8fd4\u56de\u7a7a")
        return False
    ok = resp.get("ret") == 0
    if not ok:
        log(f"  \u2717 API \u8fd4\u56de: {json.dumps(resp, ensure_ascii=False)[:200]}")
    return ok


# ── 扫码登录 ──────────────────────────────────────────


def login():
    print("=" * 50)
    print("  opencode \u76d1\u63a7 \u2014 \u5fae\u4fe1\u767b\u5f55")
    print("=" * 50)
    print()
    qrcode, qr_img = fetch_qrcode()
    print("\u8bf7\u7528\u5fae\u4fe1\u626b\u63cf\u4ee5\u4e0b\u4e8c\u7ef4\u7801\uff1a")
    print()
    import webbrowser
    webbrowser.open(qr_img)
    print(f"  \u4e8c\u7ef4\u7801\u94fe\u63a5: {qr_img}")
    print(f"  \u5df2\u81ea\u52a8\u5728\u6d4f\u89c8\u5668\u6253\u5f00\uff0c\u8bf7\u7528\u5fae\u4fe1\u626b\u7801")
    print()
    start = time.time()
    timeout = 8 * 60
    while time.time() - start < timeout:
        status = poll_qr_status(qrcode)
        s = status.get("status", "")
        if s == "wait":
            print(".", end="", flush=True)
        elif s == "scaned":
            print("\n\u5df2\u626b\u7801\uff01\u8bf7\u5728\u624b\u673a\u4e0a\u786e\u8ba4...")
        elif s == "expired":
            print("\n\u4e8c\u7ef4\u7801\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u8bd5")
            return None
        elif s == "confirmed":
            cred = {
                "token": status["bot_token"],
                "base_url": status.get("baseurl", WECHAT_BASE_URL),
                "account_id": status["ilink_bot_id"],
            }
            CRED_FILE.write_text(json.dumps(cred, indent=2))
            print("\n\u767b\u5f55\u6210\u529f\uff01\u51ed\u636e\u5df2\u4fdd\u5b58\u3002")
            return cred
        time.sleep(1)
    print("\n\u767b\u5f55\u8d85\u65f6")
    return None


def load_cred():
    if CRED_FILE.exists():
        return json.loads(CRED_FILE.read_text())
    return None


# ── 会话监控 ──────────────────────────────────────────


def get_completed_notifications(notified_part_ids=None, now_ms=None):
    conn = connect_db(DB_PATH)
    try:
        return find_completed_sessions(
            conn,
            notified_part_ids=notified_part_ids or (),
            stable_window_ms=STABLE_WINDOW_MS,
            now_ms=now_ms,
        )
    finally:
        conn.close()


def notification_to_session(notification: MonitorNotification):
    return {
        "pid": notification.part_id,
        "sid": notification.session_id,
        "title": notification.title,
        "directory": notification.directory,
        "model": notification.model,
    }


def get_finished():
    """返回状态机判定已完成的 part rowid 及会话信息。"""
    return [notification_to_session(notification) for notification in get_completed_notifications()]


def notify(cred, session):
    global _ctx_token_ready
    if not _ctx_token_ready:
        log("  \u23f3 \u5c1a\u65e0 context_token")
        return
    text = (
        f"\U0001f4ec opencode \u65b0\u56de\u590d\n\n"
        f"\u6587\u4ef6\u5939\uff1a{session['directory']}\n"
        f"\u5bf9\u8bdd\uff1a{session['title']}\n"
        f"\u6a21\u578b\uff1a{session['model'] or 'N/A'}\n"
        f"\u65f6\u95f4\uff1a{time.strftime('%m-%d %H:%M')}"
    )
    try:
        ok = send_wechat_message(cred["token"], cred["account_id"], text)
        if ok:
            log(f"  \u2713 \u5df2\u901a\u77e5: {session['title'][:30]}")
        else:
            log(f"  \u2717 \u53d1\u9001\u5931\u8d25")
    except Exception as e:
        log(f"  \u2717 \u901a\u77e5\u5931\u8d25: {e}")


def start_get_updates_poller(token: str, buf=""):
    global _ctx_token, _ctx_user_id, _ctx_token_ready
    poll_buf = buf
    while True:
        try:
            resp = get_updates(token, poll_buf)
            if resp.get("get_updates_buf"):
                poll_buf = resp["get_updates_buf"]
            for msg in resp.get("msgs") or []:
                if msg.get("message_type") != 1:
                    continue
                uid = msg.get("from_user_id")
                ctx = msg.get("context_token")
                if uid and ctx:
                    _ctx_token = ctx
                    _ctx_user_id = uid
                    if not _ctx_token_ready:
                        _ctx_token_ready = True
                        log("\u2705 \u5df2\u83b7\u53d6 context_token\uff0c\u53ef\u4ee5\u53d1\u9001\u901a\u77e5\u4e86")
        except Exception as e:
            time.sleep(2)


# ── 主函数 ────────────────────────────────────────────


def main():
    print("opencode \u4f1a\u8bdd\u76d1\u63a7")
    print(f"\u6570\u636e\u5e93: {DB_PATH}")
    print(f"\u8f6e\u8be2\u95f4\u9694: {POLL_INTERVAL}s")
    print(f"\u7a33\u5b9a\u7a97\u53e3: {STABLE_WINDOW_MS}ms")
    print()

    global _log_file
    log_path = Path.home() / "opencode-monitor.log"
    _log_file = open(log_path, "a", encoding="utf-8")
    log("\u542f\u52a8\u76d1\u63a7")

    cred = load_cred()
    if not cred:
        cred = login()
        if not cred:
            log("\u767b\u5f55\u5931\u8d25\uff0c\u9000\u51fa")
            return

    Thread(target=start_get_updates_poller, args=(cred["token"],), daemon=True).start()
    log("\u7b49\u5f85 context_token\u2026 \u8bf7\u5411\u4f60\u7684\u5fae\u4fe1\u673a\u5668\u4eba\u53d1\u9001\u4efb\u610f\u4e00\u6761\u6d88\u606f")
    print()

    # 初始化：记录所有已有完成候选，防止重启后重复通知
    initial = get_completed_notifications()
    notified = {notification.part_id for notification in initial}
    log(f"\u5df2\u8bb0\u5f55 {len(notified)} \u4e2a\u5df2\u5b8c\u6210\u7684\u4f1a\u8bdd\u901a\u77e5\u5019\u9009")

    while True:
        time.sleep(POLL_INTERVAL)
        try:
            finished = get_completed_notifications(notified_part_ids=notified)
        except Exception as e:
            log(f"\u6570\u636e\u5e93\u8bfb\u53d6\u5931\u8d25: {e}")
            continue

        for notification in finished:
            notified.add(notification.part_id)
            session = notification_to_session(notification)
            log(f"\u65b0\u56de\u590d: {session['title'][:40]} ({session['directory']})")
            notify(cred, session)


if __name__ == "__main__":
    main()
