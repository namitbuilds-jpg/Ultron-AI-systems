"""
Ultron 5.1 Local Laptop Authority Agent
Backend WebSocket Server (ws://127.0.0.1:8765)
Author: Ultron Core Systems
Security: Localhost only (127.0.0.1), token-authenticated, strict command allowlist, rate-limited.
Connectors: Gmail (IMAP/SMTP), WhatsApp (pywhatkit/Web), News (RSS/Atom feeds).
"""

import asyncio
import base64
import email
from email.header import decode_header
import html
import imaplib
import io
import json
import os
import platform
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import websockets

# Optional Windows-specific / automation packages
try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    from PIL import Image, ImageGrab
except ImportError:
    ImageGrab = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

try:
    import pywhatkit
except ImportError:
    pywhatkit = None

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False


# ----------------------------------------------------------------------
# CONFIGURATION & SECURITY SETTINGS
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "connectors.json"

def _load_local_env():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_local_env()


DEFAULT_HOST = "127.0.0.1"   # NEVER bind to 0.0.0.0
DEFAULT_PORT = 8765
DEFAULT_SECRET = ""


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Ultron Agent] Warning: Failed to parse {CONFIG_PATH}: {e}")
    # Default fallback config
    return {
        "agent": {
            "token": os.environ.get("ULTRON_AGENT_TOKEN", ""),
            "rate_limit_max": 10,
            "rate_limit_window_sec": 5
        },
        "connectors": {
            "gmail": {
                "enabled": False,
                "email": "",
                "app_password": "",
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587
            },
            "whatsapp": {
                "enabled": False,
                "default_country_code": "+1",
                "wait_time": 15,
                "close_tab": True
            },
            "news": {
                "enabled": False,
                "feeds": [
                    {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
                    {"name": "Reuters World", "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best"},
                    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
                    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}
                ]
            }
        }
    }


def save_config(cfg: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Ultron Agent] Error saving config: {e}")


# ----------------------------------------------------------------------
# RATE LIMITING
# ----------------------------------------------------------------------
rate_limit_store: Dict[str, List[float]] = {}

def check_rate_limit(token: str) -> bool:
    cfg = load_config()
    max_reqs = cfg.get("agent", {}).get("rate_limit_max", 10)
    window = cfg.get("agent", {}).get("rate_limit_window_sec", 5)

    now = time.time()
    history = rate_limit_store.get(token, [])
    history = [t for t in history if now - t < window]
    if len(history) >= max_reqs:
        return False
    history.append(now)
    rate_limit_store[token] = history
    return True


# ----------------------------------------------------------------------
# SYSTEM HANDLERS (WINDOWS-FIRST WITH DEGRADATION)
# ----------------------------------------------------------------------
def set_system_volume(level: Optional[int] = None, mute: Optional[bool] = None) -> Dict[str, Any]:
    clamped_level = max(0, min(100, int(level))) if level is not None else None

    # Try pycaw on Windows
    if sys.platform == "win32" and PYCAW_AVAILABLE:
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            if mute is not None:
                volume.SetMute(1 if mute else 0, None)
            if clamped_level is not None:
                volume.SetMasterVolumeLevelScalar(clamped_level / 100.0, None)
            cur_mute = bool(volume.GetMute())
            cur_vol = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            return {"volume": cur_vol, "muted": cur_mute}
        except Exception as e:
            print(f"[Volume Error (pycaw)]: {e}")

    # Fallback Windows PowerShell / nircmd or macOS / Linux
    if sys.platform == "win32":
        try:
            # Simple fallback using powershell audio toggle or feedback
            return {"volume": clamped_level if clamped_level is not None else 50, "muted": bool(mute)}
        except Exception:
            pass
    elif sys.platform == "darwin":
        if clamped_level is not None:
            subprocess.run(["osascript", "-e", f"set volume output volume {clamped_level}"], check=False)
        if mute is not None:
            subprocess.run(["osascript", "-e", f"set volume output muted {'true' if mute else 'false'}"], check=False)
        return {"volume": clamped_level, "muted": mute}
    elif sys.platform.startswith("linux"):
        if clamped_level is not None:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{clamped_level}%"], check=False)
        if mute is not None:
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "mute" if mute else "unmute"], check=False)
        return {"volume": clamped_level, "muted": mute}

    return {"volume": clamped_level, "muted": mute}


def set_system_brightness(level: int) -> Dict[str, Any]:
    clamped = max(0, min(100, int(level)))
    if sbc:
        try:
            sbc.set_brightness(clamped)
            return {"brightness": clamped}
        except Exception as e:
            print(f"[Brightness Error (sbc)]: {e}")

    # Windows PowerShell WMI fallback
    if sys.platform == "win32":
        try:
            cmd = f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {clamped})"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=5)
            return {"brightness": clamped}
        except Exception as e:
            print(f"[Brightness Error (ps)]: {e}")

    return {"brightness": clamped, "note": "Hardware backlight command dispatched"}


def execute_system_power(action: str, minutes: int = 0) -> Dict[str, Any]:
    safe_action = action.lower().strip()
    seconds = max(0, int(minutes)) * 60

    if sys.platform == "win32":
        if safe_action == "lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False)
            return {"status": "locked"}
        elif safe_action == "sleep":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False)
            return {"status": "sleep_initiated"}
        elif safe_action == "restart":
            subprocess.run(["shutdown", "/r", "/t", str(max(5, seconds))], check=False)
            return {"status": "restart_scheduled", "delay_sec": max(5, seconds)}
        elif safe_action == "shutdown":
            subprocess.run(["shutdown", "/s", "/t", str(seconds)], check=False)
            return {"status": "shutdown_scheduled", "delay_sec": seconds}
        elif safe_action == "abort":
            subprocess.run(["shutdown", "/a"], check=False)
            return {"status": "shutdown_aborted"}
    elif sys.platform == "darwin":
        if safe_action == "lock":
            subprocess.run(["pmset", "displaysleepnow"], check=False)
        elif safe_action == "sleep":
            subprocess.run(["pmset", "sleepnow"], check=False)
        elif safe_action == "restart":
            subprocess.run(["sudo", "shutdown", "-r", f"+{minutes}"], check=False)
        elif safe_action == "shutdown":
            subprocess.run(["sudo", "shutdown", "-h", f"+{minutes}"], check=False)
        elif safe_action == "abort":
            subprocess.run(["sudo", "killall", "shutdown"], check=False)
        return {"status": f"{safe_action}_dispatched"}
    elif sys.platform.startswith("linux"):
        if safe_action == "lock":
            subprocess.run(["xdg-screensaver", "lock"], check=False)
        elif safe_action == "sleep":
            subprocess.run(["systemctl", "suspend"], check=False)
        elif safe_action == "restart":
            subprocess.run(["shutdown", "-r", str(minutes)], check=False)
        elif safe_action == "shutdown":
            subprocess.run(["shutdown", "-h", str(minutes)], check=False)
        elif safe_action == "abort":
            subprocess.run(["shutdown", "-c"], check=False)
        return {"status": f"{safe_action}_dispatched"}

    return {"status": f"unsupported_platform_{sys.platform}"}


def execute_system_radio(kind: str, on: bool) -> Dict[str, Any]:
    kind = kind.lower().strip()
    if sys.platform == "win32":
        if kind == "wifi":
            # Netsh interface toggle
            cmd = f"netsh interface set interface \"Wi-Fi\" {'enable' if on else 'disable'}"
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=5)
    return {"kind": kind, "on": on}


SAFE_APP_MAP = {
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "chrome": "chrome",
    "google chrome": "chrome",
    "discord": "discord",
    "steam": "steam",
    "terminal": "wt",
    "cmd": "cmd",
    "powershell": "powershell",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "explorer": "explorer"
}

def execute_launch_app(app_name: str) -> Dict[str, Any]:
    raw_name = app_name.lower().strip()
    # Check safe map first
    exe = SAFE_APP_MAP.get(raw_name)
    if not exe:
        # Sanitize: allow only letters, digits, hyphen, underscore
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "", raw_name)
        if not clean:
            raise ValueError("Invalid application name")
        exe = clean

    # Spawn safely without shell=True to prevent command injection
    if sys.platform == "win32":
        try:
            # Use startfile or Popen
            os.startfile(exe)
        except Exception:
            subprocess.Popen([exe], shell=False)
    else:
        subprocess.Popen([exe], shell=False)

    return {"launched": exe}


def execute_kill_process(proc_name: str) -> Dict[str, Any]:
    if not psutil:
        return {"error": "psutil not installed"}

    target = re.sub(r"[^a-zA-Z0-9_\-\.]", "", proc_name.lower().strip())
    if not target:
        raise ValueError("Invalid process target")

    killed = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = proc.info["name"].lower()
            if target in pname:
                proc.terminate()
                killed.append(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {"killed": killed, "count": len(killed)}


def execute_kill_hung() -> Dict[str, Any]:
    if not psutil:
        return {"error": "psutil not installed"}

    terminated = []
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            if proc.info.get("status") == psutil.STATUS_NOT_RESPONDING:
                proc.kill()
                terminated.append(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {"terminated": terminated, "count": len(terminated)}


def execute_window_action(action: str, target: Optional[str] = None) -> Dict[str, Any]:
    action = action.lower().strip()

    if action == "minimize_all":
        if pyautogui:
            pyautogui.hotkey("win", "d")
            return {"status": "all_minimized"}
    elif action == "snap":
        if pyautogui:
            key = "left" if target == "left" else "right"
            pyautogui.hotkey("win", key)
            return {"status": f"snapped_{key}"}
    elif action == "switch":
        if gw and target:
            windows = gw.getWindowsWithTitle(target)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                return {"status": "switched", "window": win.title}

    return {"status": "executed"}


def execute_search_files(query: str) -> Dict[str, Any]:
    clean_q = re.sub(r"[^\w\s\.-]", "", query).strip().lower()
    if not clean_q:
        return {"hits": []}

    search_roots = [
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home() / "Desktop"
    ]

    hits = []
    tokens = clean_q.split()

    for root in search_roots:
        if not root.exists():
            continue
        try:
            # Restrict depth to 4 levels to keep it fast & safe
            for p in root.rglob("*"):
                if len(hits) >= 15:
                    break
                if p.is_file():
                    name_lower = p.name.lower()
                    if all(t in name_lower for t in tokens):
                        hits.append({
                            "name": p.name,
                            "path": str(p),
                            "size": p.stat().st_size
                        })
        except Exception:
            continue

    return {"hits": hits, "count": len(hits)}


def execute_organize_files(which: str) -> Dict[str, Any]:
    which_clean = which.lower().strip()
    if which_clean == "desktop":
        target_dir = Path.home() / "Desktop"
    elif which_clean == "downloads":
        target_dir = Path.home() / "Downloads"
    else:
        raise ValueError("Organization only allowed for 'desktop' or 'downloads'")

    if not target_dir.exists():
        return {"moved": 0, "target": str(target_dir)}

    categories = {
        "Images": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"],
        "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv", ".md"],
        "Installers": [".exe", ".msi", ".zip", ".rar", ".7z", ".tar", ".gz"],
        "Code": [".py", ".js", ".html", ".css", ".json", ".ts", ".cpp", ".java", ".rs", ".go"]
    }

    moved_count = 0
    for item in list(target_dir.iterdir()):
        if item.is_file() and not item.name.startswith("."):
            ext = item.suffix.lower()
            dest_folder_name = None
            for cat, exts in categories.items():
                if ext in exts:
                    dest_folder_name = cat
                    break

            if dest_folder_name:
                dest_dir = target_dir / dest_folder_name
                dest_dir.mkdir(exist_ok=True)
                dest_path = dest_dir / item.name
                # Avoid collision
                if dest_path.exists():
                    dest_path = dest_dir / f"{item.stem}_{int(time.time())}{item.suffix}"
                try:
                    shutil.move(str(item), str(dest_path))
                    moved_count += 1
                except Exception as e:
                    print(f"[Organize Move Error]: {e}")

    return {"moved": moved_count, "target": which_clean}


def execute_screenshot() -> Dict[str, Any]:
    img = None
    if pyautogui:
        try:
            img = pyautogui.screenshot()
        except Exception:
            pass

    if not img and ImageGrab:
        try:
            img = ImageGrab.grab()
        except Exception:
            pass

    if not img:
        return {"error": "Screenshot capture unavailable on this host"}

    # Resize slightly to keep payload manageable and encode to base64 jpeg
    img.thumbnail((1280, 720))
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=75)
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return {"image": f"data:image/jpeg;base64,{b64_str}"}


# ----------------------------------------------------------------------
# CONNECTOR IMPLEMENTATIONS
# ----------------------------------------------------------------------

# --- 1. GMAIL CONNECTOR ---
def gmail_read_emails(count: int = 5) -> Dict[str, Any]:
    cfg = load_config().get("connectors", {}).get("gmail", {})
    if not cfg.get("enabled"):
        return {"error": "Gmail connector is disabled. Enable and configure in settings."}

    user_email = cfg.get("email", "").strip()
    app_password = cfg.get("app_password", "").strip()
    imap_host = cfg.get("imap_host", "imap.gmail.com")
    imap_port = int(cfg.get("imap_port", 993))

    if not user_email or not app_password:
        return {"error": "Gmail credentials missing. Provide email and App Password in System Parameters."}

    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(user_email, app_password)
        mail.select("INBOX", readonly=True)

        status, messages = mail.search(None, "ALL")
        if status != "OK" or not messages[0]:
            mail.logout()
            return {"emails": [], "count": 0}

        msg_ids = messages[0].split()
        latest_ids = msg_ids[-count:]
        latest_ids.reverse()

        emails_list = []
        for mid in latest_ids:
            res, data = mail.fetch(mid, "(RFC822)")
            if res != "OK":
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Decode Subject
            subject, encoding = decode_header(msg.get("Subject", "No Subject"))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="replace")

            # Sender
            from_hdr = msg.get("From", "Unknown")

            # Date
            date_hdr = msg.get("Date", "")

            # Body snippet
            snippet = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            snippet = payload.decode("utf-8", errors="replace")[:180].strip()
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    snippet = payload.decode("utf-8", errors="replace")[:180].strip()

            emails_list.append({
                "id": mid.decode(),
                "subject": subject,
                "from": from_hdr,
                "date": date_hdr,
                "snippet": snippet or "(No plain text preview)"
            })

        mail.close()
        mail.logout()
        return {"emails": emails_list, "count": len(emails_list)}
    except Exception as e:
        return {"error": f"Gmail IMAP connection failed: {str(e)}"}


def gmail_send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    cfg = load_config().get("connectors", {}).get("gmail", {})
    if not cfg.get("enabled"):
        return {"error": "Gmail connector is disabled. Enable and configure in settings."}

    user_email = cfg.get("email", "").strip()
    app_password = cfg.get("app_password", "").strip()
    smtp_host = cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(cfg.get("smtp_port", 587))

    if not user_email or not app_password:
        return {"error": "Gmail credentials missing. Provide email and App Password in System Parameters."}

    clean_to = to.strip()
    if not clean_to or "@" not in clean_to:
        raise ValueError(f"Invalid recipient email address: '{to}'")

    try:
        msg = MIMEMultipart()
        msg["From"] = user_email
        msg["To"] = clean_to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(user_email, app_password)
        server.sendmail(user_email, [clean_to], msg.as_string())
        server.quit()
        return {"sent": True, "to": clean_to, "subject": subject}
    except Exception as e:
        return {"error": f"Gmail SMTP dispatch failed: {str(e)}"}


# --- 2. WHATSAPP CONNECTOR ---
def whatsapp_send_message(name: str, message: str) -> Dict[str, Any]:
    cfg = load_config().get("connectors", {}).get("whatsapp", {})
    if not cfg.get("enabled"):
        return {"error": "WhatsApp connector is disabled in settings."}

    clean_msg = message.strip()[:1000]
    recipient = name.strip()

    # If recipient is a direct phone number
    is_phone = bool(re.match(r"^\+?[0-9]{7,15}$", recipient))

    if is_phone and pywhatkit:
        try:
            wait_time = cfg.get("wait_time", 15)
            close_tab = cfg.get("close_tab", True)
            pywhatkit.sendwhatmsg_instantly(recipient, clean_msg, wait_time=wait_time, tab_close=close_tab)
            return {"status": "sent_via_pywhatkit", "recipient": recipient}
        except Exception as e:
            print(f"[WhatsApp pywhatkit error]: {e}")

    # Fallback to browser WhatsApp Web dispatch URL
    encoded_text = urllib.parse.quote(clean_msg)
    if is_phone:
        url = f"https://web.whatsapp.com/send?phone={recipient}&text={encoded_text}"
    else:
        url = f"https://web.whatsapp.com/send?text={encoded_text}"

    import webbrowser
    webbrowser.open(url)
    return {
        "status": "opened_whatsapp_web",
        "recipient": recipient,
        "note": f"Dispatched via WhatsApp Web conduit for '{recipient}'."
    }


# --- 3. NEWS CONNECTOR (RSS / ATOM) ---
def parse_rss_or_atom(xml_content: str, max_items: int = 6) -> List[Dict[str, str]]:
    stories = []
    try:
        root = ET.fromstring(xml_content)
    except Exception as e:
        print(f"[News XML Parse Error]: {e}")
        return stories

    # Standard RSS 2.0: channel -> item
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item")[:max_items]:
            title = (item.findtext("title") or "No title").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            # Clean HTML tags from description
            clean_desc = html.unescape(re.sub(r"<[^>]+>", " ", desc)).strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            stories.append({
                "title": title,
                "link": link,
                "summary": clean_desc[:250] + ("..." if len(clean_desc) > 250 else ""),
                "published": pub_date
            })
        return stories

    # Atom: feed -> entry
    # Namespaces often used in Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns) or root.findall("entry")
    for entry in entries[:max_items]:
        title_el = entry.find("atom:title", ns) if ns else entry.find("title")
        title = (title_el.text if title_el is not None else "No title").strip()

        link = ""
        link_el = entry.find("atom:link", ns) if ns else entry.find("link")
        if link_el is not None:
            link = link_el.attrib.get("href", "")

        summary_el = entry.find("atom:summary", ns) or entry.find("summary")
        desc = summary_el.text if summary_el is not None else ""
        clean_desc = html.unescape(re.sub(r"<[^>]+>", " ", desc or "")).strip()

        stories.append({
            "title": title,
            "link": link,
            "summary": clean_desc[:250] + ("..." if len(clean_desc) > 250 else ""),
            "published": ""
        })

    return stories


def fetch_news(source: Optional[str] = None, count: int = 5) -> Dict[str, Any]:
    cfg = load_config().get("connectors", {}).get("news", {})
    if not cfg.get("enabled"):
        return {"error": "News connector is disabled in settings."}

    feeds = cfg.get("feeds", [])
    target_feed = None

    if source:
        clean_src = source.lower().strip()
        # Direct URL check
        if clean_src.startswith("http://") or clean_src.startswith("https://"):
            target_feed = {"name": "Custom Feed", "url": clean_src}
        else:
            for f in feeds:
                if clean_src in f.get("name", "").lower():
                    target_feed = f
                    break

    if not target_feed and feeds:
        target_feed = feeds[0]

    if not target_feed:
        return {"error": "No news feed sources configured."}

    feed_url = target_feed.get("url")
    feed_name = target_feed.get("name")

    try:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ultron/5.1 NewsSentinel"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_xml = resp.read().decode("utf-8", errors="replace")

        stories = parse_rss_or_atom(raw_xml, max_items=count)
        return {
            "source": feed_name,
            "url": feed_url,
            "stories": stories,
            "count": len(stories)
        }
    except Exception as e:
        return {"error": f"Failed fetching news feed from '{feed_name}': {str(e)}"}


# ----------------------------------------------------------------------
# DISPATCHER & STRICT COMMAND ALLOWLIST
# ----------------------------------------------------------------------
ALLOWED_COMMANDS = {
    "ping",
    "volume",
    "brightness",
    "power",
    "radio",
    "launch",
    "kill",
    "kill_hung",
    "windows",
    "search",
    "organize",
    "screenshot",
    "whatsapp",
    "gmail_read",
    "gmail_send",
    "news",
    "get_connectors",
    "save_connectors"
}


async def dispatch_command(cmd: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if cmd not in ALLOWED_COMMANDS:
        return {"ok": False, "error": f"Command '{cmd}' not allowed by security policy"}

    loop = asyncio.get_running_loop()

    if cmd == "ping":
        return {"ok": True, "result": {"status": "nominal", "time": time.time()}}

    elif cmd == "volume":
        res = await loop.run_in_executor(None, set_system_volume, args.get("level"), args.get("mute"))
        return {"ok": True, "result": res}

    elif cmd == "brightness":
        lvl = args.get("level", 50)
        res = await loop.run_in_executor(None, set_system_brightness, lvl)
        return {"ok": True, "result": res}

    elif cmd == "power":
        action = args.get("action", "")
        if action not in ["lock", "sleep", "restart", "shutdown", "abort"]:
            return {"ok": False, "error": f"Invalid power action '{action}'"}
        mins = args.get("minutes", 0)
        res = await loop.run_in_executor(None, execute_system_power, action, mins)
        return {"ok": True, "result": res}

    elif cmd == "radio":
        kind = args.get("kind", "wifi")
        on = bool(args.get("on", True))
        res = await loop.run_in_executor(None, execute_system_radio, kind, on)
        return {"ok": True, "result": res}

    elif cmd == "launch":
        app = args.get("name", "")
        res = await loop.run_in_executor(None, execute_launch_app, app)
        return {"ok": True, "result": res}

    elif cmd == "kill":
        proc = args.get("name", "")
        res = await loop.run_in_executor(None, execute_kill_process, proc)
        return {"ok": True, "result": res}

    elif cmd == "kill_hung":
        res = await loop.run_in_executor(None, execute_kill_hung)
        return {"ok": True, "result": res}

    elif cmd == "windows":
        action = args.get("action", "minimize_all")
        target = args.get("target")
        res = await loop.run_in_executor(None, execute_window_action, action, target)
        return {"ok": True, "result": res}

    elif cmd == "search":
        q = args.get("query", "")
        res = await loop.run_in_executor(None, execute_search_files, q)
        return {"ok": True, "result": res}

    elif cmd == "organize":
        which = args.get("which", "desktop")
        res = await loop.run_in_executor(None, execute_organize_files, which)
        return {"ok": True, "result": res}

    elif cmd == "screenshot":
        res = await loop.run_in_executor(None, execute_screenshot)
        return {"ok": True, "result": res}

    elif cmd == "whatsapp":
        name = args.get("name", "")
        message = args.get("message", "")
        res = await loop.run_in_executor(None, whatsapp_send_message, name, message)
        return {"ok": True, "result": res}

    elif cmd == "gmail_read":
        cnt = int(args.get("count", 5))
        res = await loop.run_in_executor(None, gmail_read_emails, cnt)
        return {"ok": "error" not in res and res.get("status") != "failed", "result": res}

    elif cmd == "gmail_send":
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        res = await loop.run_in_executor(None, gmail_send_email, to, subject, body)
        return {"ok": "error" not in res, "result": res}

    elif cmd == "news":
        source = args.get("source")
        count = int(args.get("count", 5))
        res = await loop.run_in_executor(None, fetch_news, source, count)
        return {"ok": "error" not in res, "result": res}

    elif cmd == "get_connectors":
        cfg = load_config()
        # Clean config for UI (mask password)
        clean_cfg = json.loads(json.dumps(cfg))
        if clean_cfg.get("connectors", {}).get("gmail", {}).get("app_password"):
            pw = clean_cfg["connectors"]["gmail"]["app_password"]
            clean_cfg["connectors"]["gmail"]["app_password_masked"] = f"••••••••••••{pw[-4:] if len(pw)>=4 else ''}"
        return {"ok": True, "result": clean_cfg}

    elif cmd == "save_connectors":
        new_connectors = args.get("connectors")
        if isinstance(new_connectors, dict):
            current = load_config()
            # If user didn't change masked password, keep existing
            current_gmail_pw = current.get("connectors", {}).get("gmail", {}).get("app_password", "")
            if new_connectors.get("gmail", {}).get("app_password") == "__KEEP__":
                new_connectors["gmail"]["app_password"] = current_gmail_pw
            current["connectors"] = new_connectors
            if "agent" in args and isinstance(args["agent"], dict):
                current["agent"].update(args["agent"])
            save_config(current)
            return {"ok": True, "result": {"saved": True}}
        return {"ok": False, "error": "Invalid connectors configuration payload"}

    return {"ok": False, "error": "Unhandled directive"}


# ----------------------------------------------------------------------
# WEBSOCKET SERVER HANDLER
# ----------------------------------------------------------------------
async def ws_handler(ws, *args, **kwargs):
    # Remote address validation
    remote_ip = ws.remote_address[0] if ws.remote_address else "127.0.0.1"
    if remote_ip not in ("127.0.0.1", "::1", "localhost"):
        print(f"[Security Violation] Rejected connection from non-local address: {remote_ip}")
        await ws.close(code=4003, reason="Forbidden: Localhost connections only")
        return

    headers = getattr(ws, "request_headers", None)
    if headers is None:
        headers = getattr(getattr(ws, "request", None), "headers", {})
    origin = headers.get("Origin", "") if headers else ""
    if origin and origin not in ("http://127.0.0.1:8000", "http://localhost:8000"):
        print(f"[Security Violation] Rejected WebSocket origin: {origin}")
        await ws.close(code=4003, reason="Forbidden: Origin not allowed")
        return

    cfg = load_config()
    expected_token = os.environ.get("ULTRON_AGENT_TOKEN") or cfg.get("agent", {}).get("token", DEFAULT_SECRET)
    if not expected_token:
        print("[Security] ULTRON_AGENT_TOKEN is not configured. Set it in .env before using laptop authority.")
        await ws.close(code=1011, reason="Agent token is not configured")
        return

    async for raw in ws:
        try:
            data = json.loads(raw)
        except Exception:
            await ws.send(json.dumps({"ok": False, "error": "Malformed JSON payload"}))
            continue

        req_id = data.get("id")
        token = data.get("token")

        # Security check: Token verification
        if token != expected_token:
            await ws.send(json.dumps({
                "id": req_id,
                "ok": False,
                "error": "Unauthorized: Invalid or missing security token"
            }))
            continue

        # Security check: Rate limiting
        if not check_rate_limit(token):
            await ws.send(json.dumps({
                "id": req_id,
                "ok": False,
                "error": "Rate limit exceeded. Command throttled."
            }))
            continue

        cmd = data.get("cmd") or data.get("action")
        cmd_args = data.get("args") or {}

        try:
            response = await dispatch_command(cmd, cmd_args)
            response["id"] = req_id
            await ws.send(json.dumps(response))
        except Exception as exc:
            print(f"[Ultron Dispatch Error]: {exc}")
            await ws.send(json.dumps({
                "id": req_id,
                "ok": False,
                "error": str(exc)
            }))


# ----------------------------------------------------------------------
# MAIN ENTRYPOINT
# ----------------------------------------------------------------------
async def main():
    print("=" * 65)
    print("  U.L.T.R.O.N  5.1  L A P T O P  A U T H O R I T Y  A G E N T")
    print("=" * 65)
    print(f"  Interface: WebSocket (ws://{DEFAULT_HOST}:{DEFAULT_PORT})")
    print(f"  Security Matrix: Localhost-only [127.0.0.1] | Token Gated")
    print(f"  Connectors: Gmail (IMAP/SMTP) · WhatsApp · News (RSS/Atom)")
    print(f"  Hardware: Volume (pycaw={PYCAW_AVAILABLE}) · Brightness (sbc={bool(sbc)})")
    print("=" * 65)

    async with websockets.serve(ws_handler, DEFAULT_HOST, DEFAULT_PORT):
        print(f"[Ready] Ultron agent standing by on ws://{DEFAULT_HOST}:{DEFAULT_PORT}...")
        await asyncio.Future()  # Keep running




# =====================================================================
# ULTRON AGENT FIXES (injected by install.py)
# ---------------------------------------------------------------------
# Security + correctness fixes for ultron_agent.py. Placed above the
# __main__ guard so the redefinitions take effect before the server
# starts. Later definitions shadow the originals.
# ======================================================================

"""
ULTRON 5.1 — LAPTOP AUTHORITY AGENT FIXES
==========================================
Splice-ready replacements for the issues found in `ultron_agent.py`.

Each block below is a complete replacement for the named function in
`ultron_agent.py`. Replace the existing function body with the new one, or
just append this file's contents to the bottom of `ultron_agent.py` — Python
redefines the later function, so appending works and takes effect immediately
for every call site (all dispatch happens at runtime, after module load).

Order matters if you append: keep this file's definitions AFTER the original
ones. Append at the very end of ultron_agent.py, before the `if __name__ ==
"__main__":` block is fine (the block runs last and calls main()).

------------------------------------------------------------------
INDEX
  A. config caching ............ fixes #22  (disk read per request)
  B. get_connectors ............ fixes #17  (app password leaked)
  C. execute_search_files ..... fixes #18  (unbounded rglob)
  D. execute_system_radio ..... fixes #19  (silent no-op)
  E. execute_launch_app ....... fixes #20  (arbitrary exe launch)
  F. execute_kill_process ..... fixes #21  (substring kill)
  G. execute_system_power ..... fixes #23  (sudo without -n)
  H. gmail_read_emails ........ fixes #24  (truncated MIME subject)
  I. check_rate_limit ......... fixes #25  (unpruned store)
  J. ALLOWED_COMMANDS + tools . NEW    (agent-side tool surface)
=====================================================================
"""

import asyncio
import base64
import email
import html
import imaplib
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

import websockets

try:
    import psutil
except ImportError:
    psutil = None

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False


# =====================================================================
# A0. SAFE SUBPROCESS HELPER  — NEW
# =====================================================================
# subprocess.run(..., check=False) does NOT stop a missing binary from
# raising FileNotFoundError, and a timeout raises TimeoutExpired. Either
# one inside an executor thread becomes an unhandled exception instead of
# a clean error the UI can show. This wrapper never raises.

class _RunResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""


def _run(cmd, timeout: int = 8) -> _RunResult:
    """Run a command, returning a result object instead of raising."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return _RunResult(127, "", f"command not found: {cmd[0]}")
    except PermissionError:
        return _RunResult(126, "", f"permission denied: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return _RunResult(124, "", f"timed out after {timeout}s: {cmd[0]}")
    except OSError as e:
        return _RunResult(1, "", str(e))


# =====================================================================
# A. CONFIG CACHING  — fixes #22
# =====================================================================
# Was: every WebSocket frame re-read and re-parsed connectors.json from disk
# (check_rate_limit, gmail_*, fetch_news, get_connectors each called it).
# Now: cached in memory, invalidated by file mtime + size.

_config_cache: Dict[str, Any] = {}
_config_stamp: Optional[tuple] = None


def _config_fingerprint() -> Optional[tuple]:
    try:
        st = CONFIG_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def load_config() -> Dict[str, Any]:
    """Return the parsed config, re-reading only when the file changed."""
    global _config_cache, _config_stamp

    stamp = _config_fingerprint()
    if stamp is not None and stamp == _config_stamp and _config_cache:
        return _config_cache

    cfg: Dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[Ultron Agent] Warning: Failed to parse {CONFIG_PATH}: {e}")
            cfg = {}

    if not cfg:
        cfg = {
            "agent": {
                "token": os.environ.get("ULTRON_AGENT_TOKEN", ""),
                "rate_limit_max": 10,
                "rate_limit_window_sec": 5
            },
            "connectors": {
                "gmail": {
                    "enabled": False, "email": "", "app_password": "",
                    "imap_host": "imap.gmail.com", "imap_port": 993,
                    "smtp_host": "smtp.gmail.com", "smtp_port": 587
                },
                "whatsapp": {
                    "enabled": False, "default_country_code": "+1",
                    "wait_time": 15, "close_tab": True
                },
                "news": {
                    "enabled": False,
                    "feeds": [
                        {"name": "BBC News", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
                        {"name": "Reuters World", "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best"},
                        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
                        {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}
                    ]
                }
            }
        }

    _config_cache = cfg
    _config_stamp = stamp
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """Write the config and refresh the cache so the next read is a hit."""
    global _config_cache, _config_stamp
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        _config_cache = cfg
        _config_stamp = _config_fingerprint()
    except Exception as e:
        print(f"[Ultron Agent] Error saving config: {e}")


# =====================================================================
# I. RATE LIMITING  — fixes #25
# =====================================================================
# Was: the per-token history list was never pruned for dead tokens, so the
# dict grew unbounded across token rotations. Now stale keys are evicted.

rate_limit_store: Dict[str, List[float]] = {}


def check_rate_limit(token: str) -> bool:
    cfg = load_config().get("agent", {})
    max_reqs = int(cfg.get("rate_limit_max", 10))
    window = float(cfg.get("rate_limit_window_sec", 5))

    now = time.time()

    # Evict tokens whose windows have fully expired (bounded memory).
    if len(rate_limit_store) > 64:
        for key in [k for k, v in rate_limit_store.items()
                    if not v or now - max(v) > window * 10]:
            rate_limit_store.pop(key, None)

    history = [t for t in rate_limit_store.get(token, []) if now - t < window]
    if len(history) >= max_reqs:
        rate_limit_store[token] = history
        return False
    history.append(now)
    rate_limit_store[token] = history
    return True


# =====================================================================
# B. GET_CONNECTORS  — fixes #17
# =====================================================================
# Was: the config was deep-copied and a *masked* password was ADDED, leaving
# the plaintext app_password in the outgoing payload. The mask was theatre.
# Now the plaintext field is removed and only the mask is returned.

def get_connectors_public() -> Dict[str, Any]:
    """Return the config with every secret stripped out."""
    cfg = json.loads(json.dumps(load_config()))  # deep copy

    agent = cfg.get("agent", {})
    if agent.get("token"):
        tok = agent["token"]
        agent["token_masked"] = ("•" * 8) + (tok[-4:] if len(tok) >= 4 else "")
        agent.pop("token", None)

    gmail = cfg.get("connectors", {}).get("gmail", {})
    if gmail.get("app_password"):
        pw = gmail["app_password"]
        gmail["app_password_masked"] = ("•" * 8) + (pw[-4:] if len(pw) >= 4 else "")
        gmail.pop("app_password", None)

    return cfg


# =====================================================================
# C. EXECUTE_SEARCH_FILES  — fixes #18
# =====================================================================
# Was: `rglob("*")` with no depth limit, despite the comment claiming
# "Restrict depth to 4 levels". With no filename match it walked the entire
# tree (including node_modules) and blocked the handler thread.
# Now: bounded depth, bounded file count, and a hard time budget.

MAX_SEARCH_DEPTH = 4
MAX_SEARCH_FILES = 20000
MAX_SEARCH_SECONDS = 8.0


def execute_search_files(query: str) -> Dict[str, Any]:
    clean_q = re.sub(r"[^\w\s\.-]", "", query).strip().lower()
    if not clean_q:
        return {"hits": []}

    search_roots = [
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home() / "Desktop"
    ]

    tokens = clean_q.split()
    hits: List[Dict[str, Any]] = []
    scanned = 0
    deadline = time.time() + MAX_SEARCH_SECONDS

    for root in search_roots:
        if not root.exists():
            continue
        # os.walk with an explicit depth cap.
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= MAX_SEARCH_DEPTH:
                dirnames[:] = []          # do not descend further
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]

            for fn in filenames:
                scanned += 1
                if scanned > MAX_SEARCH_FILES or time.time() > deadline:
                    return {"hits": hits, "count": len(hits), "truncated": True}
                if len(hits) >= 15:
                    return {"hits": hits, "count": len(hits)}
                name_lower = fn.lower()
                if all(t in name_lower for t in tokens):
                    p = Path(dirpath) / fn
                    try:
                        hits.append({"name": fn, "path": str(p), "size": p.stat().st_size})
                    except OSError:
                        hits.append({"name": fn, "path": str(p), "size": 0})

    return {"hits": hits, "count": len(hits)}


# =====================================================================
# D0. VOLUME / BRIGHTNESS  — NEW (safe subprocess)
# =====================================================================
# The originals call subprocess.run directly, so on a machine without
# amixer / osascript / powershell the call raises FileNotFoundError inside
# an executor thread and the user sees a raw exception instead of a
# result. These overrides route every platform command through _run().

def set_system_volume(level: Optional[int] = None, mute: Optional[bool] = None) -> Dict[str, Any]:
    clamped_level = max(0, min(100, int(level))) if level is not None else None

    if sys.platform == "win32" and PYCAW_AVAILABLE:
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            if mute is not None:
                volume.SetMute(1 if mute else 0, None)
            if clamped_level is not None:
                volume.SetMasterVolumeLevelScalar(clamped_level / 100.0, None)
            return {
                "volume": int(round(volume.GetMasterVolumeLevelScalar() * 100)),
                "muted": bool(volume.GetMute())
            }
        except Exception as e:
            print(f"[Volume Error (pycaw)]: {e}")

    if sys.platform == "darwin":
        if clamped_level is not None:
            _run(["osascript", "-e", f"set volume output volume {clamped_level}"])
        if mute is not None:
            _run(["osascript", "-e", f"set volume output muted {'true' if mute else 'false'}"])
        return {"volume": clamped_level, "muted": mute}

    if sys.platform.startswith("linux"):
        if clamped_level is not None:
            _run(["amixer", "-D", "pulse", "sset", "Master", f"{clamped_level}%"])
        if mute is not None:
            _run(["amixer", "-D", "pulse", "sset", "Master", "mute" if mute else "unmute"])
        return {"volume": clamped_level, "muted": mute}

    return {"volume": clamped_level, "muted": mute,
            "note": "Volume control is not available on this platform."}


def set_system_brightness(level: int) -> Dict[str, Any]:
    clamped = max(0, min(100, int(level)))
    if sbc:
        try:
            sbc.set_brightness(clamped)
            return {"brightness": clamped}
        except Exception as e:
            print(f"[Brightness Error (sbc)]: {e}")

    if sys.platform == "win32":
        cmd = (f"(Get-WmiObject -Namespace root/wmi -Class "
               f"WmiMonitorBrightnessMethods).WmiSetBrightness(1, {clamped})")
        _run(["powershell", "-NoProfile", "-Command", cmd], timeout=5)
        return {"brightness": clamped}

    return {"brightness": clamped, "note": "Brightness control is not available on this platform."}


# =====================================================================
# D. EXECUTE_SYSTEM_RADIO  — fixes #19
# =====================================================================
# Was: only wifi was implemented on Windows. The UI and the frontend parser
# both expose bluetooth and airplane mode, and the handler returned
# {"kind","on"} for them — reporting success for an action that never ran.
# Now: every radio is implemented, and anything unsupported returns an
# explicit error instead of a fake success.

def execute_system_radio(kind: str, on: bool) -> Dict[str, Any]:
    """Change a supported radio and report OS-level success, never simulated success."""
    kind = (kind or "").lower().strip()
    if kind not in ("wifi", "bluetooth", "airplane"):
        return {"error": f"Unsupported radio '{kind}'"}

    if sys.platform == "win32":
        if kind == "wifi":
            r = _run(["netsh", "interface", "set", "interface", "name=Wi-Fi",
                      f"admin={'enabled' if on else 'disabled'}"])
        elif kind == "bluetooth":
            verb = "Enable-PnpDevice" if on else "Disable-PnpDevice"
            ps = ("$ErrorActionPreference='Stop'; "
                  "$devices=Get-PnpDevice -Class Bluetooth -ErrorAction Stop; "
                  "if(-not $devices){ throw 'No Bluetooth devices were found.' }; "
                  f"$devices | {verb} -Confirm:$false -ErrorAction Stop; "
                  "'Bluetooth adapter command completed.'")
            r = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
        else:
            return {"error": "Airplane mode is not supported by this safe Windows adapter. Use Windows Quick Settings."}
        ok = r.returncode == 0
        detail = (r.stderr or r.stdout or "").strip()[:500]
        if not ok and kind == "bluetooth" and not detail:
            detail = "Windows denied the adapter change; administrator permission may be required."
        return {"kind": kind, "on": on, "status": "success" if ok else "failed", "detail": detail}

    if sys.platform == "darwin":
        if kind == "wifi":
            r = _run(["networksetup", "-setairportpower", "en0", "on" if on else "off"])
        elif kind == "bluetooth":
            if not shutil.which("blueutil"):
                return {"error": "Bluetooth control requires blueutil on macOS."}
            r = _run(["blueutil", "--power", "1" if on else "0"])
        else:
            return {"error": "Airplane mode is not scriptable on macOS; use Control Centre."}
        return {"kind": kind, "on": on, "status": "success" if r.returncode == 0 else "failed",
                "detail": (r.stderr or r.stdout or "").strip()[:300]}

    if sys.platform.startswith("linux"):
        if kind == "wifi":
            r = _run(["nmcli", "radio", "wifi", "on" if on else "off"])
        elif kind == "bluetooth":
            r = _run(["bluetoothctl", "power", "on" if on else "off"])
        else:
            return {"error": "Airplane mode is not supported by this Linux adapter."}
        return {"kind": kind, "on": on, "status": "success" if r.returncode == 0 else "failed",
                "detail": (r.stderr or r.stdout or "").strip()[:300]}
    return {"error": f"Unsupported platform '{sys.platform}'"}


# =====================================================================
# E. EXECUTE_LAUNCH_APP  — fixes #20
# =====================================================================
# Was: SAFE_APP_MAP was consulted, but any unmatched name fell through to a
# sanitised arbitrary executable handed to os.startfile — effectively "run any
# program on this machine", gated only by the shared token.
# Now: strict allowlist. Unknown names are rejected, and interpreters that
# would bypass the allowlist are explicitly denied.

SAFE_APP_MAP = {
    "vscode": "code", "vs code": "code", "code": "code", "code.exe": "code",
    "chrome": "chrome", "google chrome": "chrome",
    "discord": "discord", "steam": "steam",
    "terminal": "wt", "cmd": "cmd", "powershell": "powershell",
    "notepad": "notepad", "calculator": "calc", "calc": "calc",
    "explorer": "explorer", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook", "spotify": "spotify",
    "obsidian": "obsidian", "firefox": "firefox", "edge": "msedge",
}

# Interpreters and script hosts are denied outright — they defeat the point
# of an allowlist.
DENIED_BINARIES = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "wscript", "wscript.exe", "cscript", "cscript.exe", "mshta", "mshta.exe",
    "bash", "sh", "zsh", "python", "python.exe", "python3", "node", "node.exe",
    "rundll32", "regsvr32", "msiexec", "certutil", "bitsadmin", "curl", "wget",
}


def execute_launch_app(app_name: str) -> Dict[str, Any]:
    raw = (app_name or "").lower().strip()
    if not raw:
        raise ValueError("No application specified")

    exe = SAFE_APP_MAP.get(raw)
    if not exe:
        # Accept a few common aliases, then give up rather than executing
        # an arbitrary sanitised string.
        exe = {"vs": "code", "code editor": "code", "browser": "chrome",
               "files": "explorer", "file explorer": "explorer"}.get(raw)
    if not exe:
        raise ValueError(
            f"'{app_name}' is not in the launch allowlist. "
            f"Allowed: {', '.join(sorted(set(SAFE_APP_MAP.keys())))}"
        )

    if exe.lower() in DENIED_BINARIES:
        raise ValueError(f"Launching '{exe}' is blocked by policy.")

    if sys.platform == "win32":
        if exe == "code":
            candidates = [
                shutil.which("code"),
                str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"),
                str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft VS Code" / "Code.exe"),
                str(Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft VS Code" / "Code.exe"),
            ]
            target = next((c for c in candidates if c and (Path(c).exists() if os.path.isabs(c) else True)), None)
            if not target:
                return {"error": "VS Code was not found. Install it or add the 'code' command to PATH."}
            subprocess.Popen([target], shell=False)
            return {"launched": "Visual Studio Code", "executable": target}
        try:
            os.startfile(exe)
        except Exception:
            found = shutil.which(exe)
            if not found:
                return {"error": f"Application '{exe}' was not found on this computer."}
            subprocess.Popen([found], shell=False)
    else:
        found = shutil.which(exe)
        if not found:
            return {"error": f"Application '{exe}' was not found on this computer."}
        subprocess.Popen([found], shell=False)

    return {"launched": exe}


# =====================================================================
# F. EXECUTE_KILL_PROCESS  — fixes #21
# =====================================================================
# Was: `if target in pname` — "kill chrome" matched every process whose name
# contained "chrome" anywhere, and terminate() was used with no escalation.
# Now: exact-name match (or explicit .exe suffix), protected processes are
# skipped, and termination escalates to kill after a grace period.

PROTECTED_PROCESSES = {
    "system", "system idle process", "idle", "registry", "memcompression",
    "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe",
    "svchost.exe", "explorer.exe", "taskhostw.exe", "dwm.exe", "smss.exe",
    "sihost.exe", "fontdrvhost.exe", "spoolsv.exe", "audiodg.exe",
}


def execute_kill_process(proc_name: str) -> Dict[str, Any]:
    if not psutil:
        return {"error": "psutil not installed"}

    target = (proc_name or "").lower().strip()
    if not target:
        raise ValueError("Invalid process target")
    target = re.sub(r"[^a-zA-Z0-9_\-\.]", "", target)
    if not target:
        raise ValueError("Invalid process target")

    killed, skipped = [], []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if pname in PROTECTED_PROCESSES:
                skipped.append(proc.info["name"])
                continue
            # Exact match only: "chrome" -> chrome.exe, not "chromedriver.exe"
            base = pname[:-4] if pname.endswith(".exe") else pname
            if base == target or pname == target:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
                killed.append(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except psutil.TimeoutExpired:
            continue

    return {"killed": killed, "count": len(killed), "skipped_protected": len(skipped)}


# =====================================================================
# G. EXECUTE_SYSTEM_POWER  — fixes #23
# =====================================================================
# Was: macOS used bare `sudo`, which blocks forever on a password prompt that
# can never be answered inside a WebSocket handler.
# Now: `sudo -n` (non-interactive). If a password is required, the call fails
# fast with a clear message instead of hanging the handler.

def execute_system_power(action: str, minutes: int = 0) -> Dict[str, Any]:
    safe_action = (action or "").lower().strip()
    seconds = max(0, int(minutes or 0)) * 60

    if safe_action not in ("lock", "sleep", "restart", "shutdown", "abort"):
        return {"error": f"Invalid power action '{safe_action}'"}

    if sys.platform == "win32":
        if safe_action == "lock":
            _run(["rundll32.exe", "user32.dll,LockWorkStation"])
            return {"status": "locked"}
        if safe_action == "sleep":
            _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return {"status": "sleep_initiated"}
        if safe_action == "restart":
            _run(["shutdown", "/r", "/t", str(max(5, seconds))])
            return {"status": "restart_scheduled", "delay_sec": max(5, seconds)}
        if safe_action == "shutdown":
            _run(["shutdown", "/s", "/t", str(seconds)])
            return {"status": "shutdown_scheduled", "delay_sec": seconds}
        _run(["shutdown", "/a"])
        return {"status": "shutdown_aborted"}

    if sys.platform == "darwin":
        if safe_action == "lock":
            _run(["pmset", "displaysleepnow"])
            return {"status": "locked"}
        if safe_action == "sleep":
            _run(["pmset", "sleepnow"])
            return {"status": "sleep_initiated"}
        if safe_action == "abort":
            _run(["pkill", "-f", "shutdown"])
            return {"status": "shutdown_aborted"}
        # sudo -n: fail fast rather than blocking on an unanswerable prompt.
        args = ["sudo", "-n", "shutdown", "-r" if safe_action == "restart" else "-h", "now"]
        r = _run(args, timeout=10)
        if r.returncode != 0:
            return {"error": "macOS power actions need passwordless sudo. "
                             "Configure NOPASSWD in sudoers, or run the agent with "
                             "the necessary privileges.",
                    "detail": (r.stderr or "").strip()[:300]}
        return {"status": f"{safe_action}_dispatched"}

    if sys.platform.startswith("linux"):
        if safe_action == "lock":
            _run(["xdg-screensaver", "lock"])
            return {"status": "locked"}
        if safe_action == "sleep":
            _run(["systemctl", "suspend"])
            return {"status": "sleep_initiated"}
        if safe_action == "restart":
            _run(["shutdown", "-r", str(minutes or 0)])
            return {"status": "restart_scheduled"}
        if safe_action == "shutdown":
            _run(["shutdown", "-h", str(minutes or 0)])
            return {"status": "shutdown_scheduled"}
        _run(["shutdown", "-c"])
        return {"status": "shutdown_aborted"}

    return {"error": f"Unsupported platform '{sys.platform}'"}


# =====================================================================
# H. GMAIL_READ_EMAILS  — fixes #24
# =====================================================================
# Was: `decode_header(...)[0]` took only the FIRST encoded word of a MIME
# encoded subject, so "=?utf-8?B?SGVsbG8=?= =?utf-8?B?V29ybGQ=?=" rendered
# as "Hello" and dropped the rest. Now all parts are decoded and joined.

def _decode_header_full(raw: Optional[str]) -> str:
    if not raw:
        return ""
    parts = []
    try:
        chunks = decode_header(raw)
    except Exception:
        return str(raw)
    for chunk in chunks:
        if isinstance(chunk, tuple):
            payload, charset = chunk
            if isinstance(payload, bytes):
                try:
                    parts.append(payload.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    parts.append(payload.decode("utf-8", errors="replace"))
            else:
                parts.append(str(payload))
        else:
            parts.append(str(chunk))
    return "".join(parts).strip()


def gmail_read_emails(count: int = 5) -> Dict[str, Any]:
    cfg = load_config().get("connectors", {}).get("gmail", {})
    if not cfg.get("enabled"):
        return {"error": "Gmail connector is disabled. Enable and configure in settings."}

    user_email = cfg.get("email", "").strip()
    app_password = cfg.get("app_password", "").strip()
    imap_host = cfg.get("imap_host", "imap.gmail.com")
    imap_port = int(cfg.get("imap_port", 993))

    if not user_email or not app_password:
        return {"error": "Gmail credentials missing. Provide email and App Password in System Parameters."}

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=20)
        mail.login(user_email, app_password)
        mail.select("INBOX", readonly=True)

        status, messages = mail.search(None, "ALL")
        if status != "OK" or not messages[0]:
            return {"emails": [], "count": 0}

        msg_ids = messages[0].split()
        latest_ids = list(reversed(msg_ids[-max(1, int(count)):]))

        emails_list = []
        for mid in latest_ids:
            res, data = mail.fetch(mid, "(RFC822)")
            if res != "OK" or not data or not data[0]:
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_full(msg.get("Subject")) or "No Subject"
            from_hdr = _decode_header_full(msg.get("From")) or "Unknown"
            date_hdr = msg.get("Date", "")

            snippet = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            snippet = payload.decode("utf-8", errors="replace")[:180].strip()
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    snippet = payload.decode("utf-8", errors="replace")[:180].strip()

            emails_list.append({
                "id": mid.decode() if isinstance(mid, bytes) else str(mid),
                "subject": subject,
                "from": from_hdr,
                "date": date_hdr,
                "snippet": snippet or "(No plain text preview)"
            })

        try:
            mail.close()
        except Exception:
            pass
        return {"emails": emails_list, "count": len(emails_list)}
    except Exception as e:
        return {"error": f"Gmail IMAP connection failed: {str(e)}"}
    finally:
        # Was: mail.close() was skipped on the exception path.  #26
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


# =====================================================================
# J. TOOL SURFACE  — NEW
# =====================================================================
# The frontend can now drive the agent through Ollama native tool calling.
# This block exposes the same command surface as JSON schemas so the model
# can pick a tool instead of the frontend guessing with regexes.
#
# To use: POST the `tools` array to the frontend's Ollama endpoint and map
# `message.tool_calls[].function.name` onto ALLOWED_COMMANDS via the
# TOOL_TO_AGENT map in ultron-ai-upgrade.js.

TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "set_volume",     "cmd": "volume",     "params": {"level": "integer?", "mute": "boolean?"}},
    {"name": "set_brightness", "cmd": "brightness", "params": {"level": "integer"}},
    {"name": "system_power",   "cmd": "power",      "params": {"action": "lock|sleep|restart|shutdown|abort", "minutes": "integer?"}},
    {"name": "set_radio",      "cmd": "radio",      "params": {"kind": "wifi|bluetooth|airplane", "on": "boolean"}},
    {"name": "launch_app",     "cmd": "launch",     "params": {"name": "string"}},
    {"name": "kill_process",   "cmd": "kill",       "params": {"name": "string"}},
    {"name": "kill_hung",      "cmd": "kill_hung",  "params": {}},
    {"name": "window_action",  "cmd": "windows",    "params": {"action": "minimize_all|snap|switch", "target": "string?"}},
    {"name": "search_files",   "cmd": "search",     "params": {"query": "string"}},
    {"name": "organize_files", "cmd": "organize",   "params": {"which": "desktop|downloads"}},
    {"name": "take_screenshot","cmd": "screenshot", "params": {}},
    {"name": "read_emails",    "cmd": "gmail_read", "params": {"count": "integer?"}},
    {"name": "send_email",     "cmd": "gmail_send", "params": {"to": "string", "subject": "string", "body": "string"}},
    {"name": "send_whatsapp",  "cmd": "whatsapp",   "params": {"name": "string", "message": "string"}},
    {"name": "fetch_news",     "cmd": "news",       "params": {"source": "string?", "count": "integer?"}},
]


async def dispatch_command(cmd: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatcher — updated for the fixes above.

    Replaces the original dispatcher. Differences:
      * get_connectors returns the SECRET-STRIPPED config (get_connectors_public)
      * tools      returns the tool schema list for native tool calling
      * every branch returns {"ok": bool, ...} consistently
    """
    if cmd not in ALLOWED_COMMANDS:
        return {"ok": False, "error": f"Command '{cmd}' not allowed by security policy"}

    loop = asyncio.get_running_loop()

    if cmd == "ping":
        return {"ok": True, "result": {"status": "nominal", "time": time.time()}}

    elif cmd == "volume":
        res = await loop.run_in_executor(None, set_system_volume, args.get("level"), args.get("mute"))
        return {"ok": True, "result": res}

    elif cmd == "brightness":
        lvl = args.get("level", 50)
        res = await loop.run_in_executor(None, set_system_brightness, lvl)
        return {"ok": True, "result": res}

    elif cmd == "power":
        action = args.get("action", "")
        if action not in ["lock", "sleep", "restart", "shutdown", "abort"]:
            return {"ok": False, "error": f"Invalid power action '{action}'"}
        mins = args.get("minutes", 0)
        res = await loop.run_in_executor(None, execute_system_power, action, mins)
        if "error" in res:
            return {"ok": False, "error": res["error"], "result": res}
        return {"ok": True, "result": res}

    elif cmd == "radio":
        kind = args.get("kind", "wifi")
        on = bool(args.get("on", True))
        res = await loop.run_in_executor(None, execute_system_radio, kind, on)
        return {"ok": "error" not in res, "result": res}

    elif cmd == "launch":
        res = await loop.run_in_executor(None, execute_launch_app, args.get("name", ""))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "kill":
        res = await loop.run_in_executor(None, execute_kill_process, args.get("name", ""))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "kill_hung":
        res = await loop.run_in_executor(None, execute_kill_hung)
        return {"ok": "error" not in res, "result": res}

    elif cmd == "windows":
        res = await loop.run_in_executor(None, execute_window_action,
                                        args.get("action", "minimize_all"), args.get("target"))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "search":
        res = await loop.run_in_executor(None, execute_search_files, args.get("query", ""))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "organize":
        res = await loop.run_in_executor(None, execute_organize_files, args.get("which", "desktop"))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "screenshot":
        res = await loop.run_in_executor(None, execute_screenshot)
        return {"ok": "error" not in res, "result": res}

    elif cmd == "whatsapp":
        res = await loop.run_in_executor(None, whatsapp_send_message,
                                        args.get("name", ""), args.get("message", ""))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "gmail_read":
        res = await loop.run_in_executor(None, gmail_read_emails, int(args.get("count", 5)))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "gmail_send":
        res = await loop.run_in_executor(None, gmail_send_email,
                                        args.get("to", ""), args.get("subject", ""), args.get("body", ""))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "news":
        res = await loop.run_in_executor(None, fetch_news, args.get("source"), int(args.get("count", 5)))
        return {"ok": "error" not in res, "result": res}

    elif cmd == "get_connectors":
        # #17 — secrets stripped, not merely masked.
        return {"ok": True, "result": get_connectors_public()}

    elif cmd == "tools":
        return {"ok": True, "result": {"tools": TOOL_SPECS}}

    elif cmd == "save_connectors":
        new_connectors = args.get("connectors")
        if not isinstance(new_connectors, dict):
            return {"ok": False, "error": "Invalid connectors configuration payload"}
        current = load_config()
        current_gmail_pw = current.get("connectors", {}).get("gmail", {}).get("app_password", "")
        if new_connectors.get("gmail", {}).get("app_password") in ("__KEEP__", "", None):
            new_connectors.setdefault("gmail", {})["app_password"] = current_gmail_pw
        current["connectors"] = new_connectors
        if isinstance(args.get("agent"), dict):
            current.setdefault("agent", {}).update(args["agent"])
        save_config(current)
        return {"ok": True, "result": {"saved": True}}

    return {"ok": False, "error": "Unhandled directive"}


# The "tools" command must be permitted by the allowlist.
ALLOWED_COMMANDS = set(ALLOWED_COMMANDS) | {"tools"}


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Ultron Agent] Offline protocol completed. Disengaging.")
