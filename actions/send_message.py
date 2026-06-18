import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)

def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else: 
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched

    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0) 
        return True
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open browser: {e}")
        return False

def _search_in_app(query: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)

def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if not _open_app(app_name):
        return f"Could not open {app_name}."

    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."

def _send_whatsapp(receiver: str, message: str) -> str:
    return _desktop_send("WhatsApp", receiver, message)

def _whatsapp_call(receiver: str, call_type: str = "voice") -> str:
    if not _open_app("WhatsApp"):
        return "Could not open WhatsApp Desktop."
    
    time.sleep(0.5)
    _search_in_app(receiver)
    
    time.sleep(0.3)
    pyautogui.press("down")
    time.sleep(0.1)
    pyautogui.press("enter")
    
    os_name = _get_os()
    
    if os_name == "windows":
        try:
            import uiautomation as auto
            print(f"[SendMessage] Using UIAutomation to locate {call_type.capitalize()} call button...")
            wa_window = auto.WindowControl(searchDepth=1, Name="WhatsApp")
            if wa_window.Exists(2, 0.2):
                wa_window.SetFocus()
                
                # Determine which button names to look for
                target_names = ["Video call", "Video"] if call_type == "video" else ["Voice call", "Audio call", "Call"]
                
                for btn_name in target_names:
                    btn = wa_window.ButtonControl(Name=btn_name)
                    # Dynamic wait: will wait UP TO 2 seconds, but proceed instantly if found
                    if btn.Exists(2, 0.2):
                        btn.Click()
                        return f"WhatsApp {call_type} call initiated with {receiver} via native UI."
                    
            print("[SendMessage] UIAutomation failed to find the button. Falling back to hotkeys.")
        except ImportError:
            print("[SendMessage] uiautomation not installed. Run: pip install uiautomation")
        except Exception as e:
            print(f"[SendMessage] UIAutomation error: {e}")

    # Fallback delays
    time.sleep(1.0)
    if call_type == "video":
        call_hotkey = ("command", "shift", "v") if os_name == "mac" else ("ctrl", "shift", "v")
    else:
        call_hotkey = ("command", "shift", "c") if os_name == "mac" else ("ctrl", "shift", "c")
        
    pyautogui.hotkey(*call_hotkey)
    time.sleep(0.5)
    
    for _ in range(4 if call_type == "video" else 3):
        pyautogui.hotkey("shift", "tab")
        time.sleep(0.1)
    pyautogui.press("enter")
    time.sleep(0.5)
    
    return f"WhatsApp {call_type} call initiated with {receiver}, sir. (Multiple methods attempted)"

def _send_telegram(receiver: str, message: str) -> str:
    return _desktop_send("Telegram", receiver, message)

def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return "Could not open Instagram in browser."

    _paste_text(receiver)
    time.sleep(1.5)

    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")   
    time.sleep(0.4)

    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Instagram."


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."


    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Messenger."


_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp, _whatsapp_call),
    ({"telegram", "tg"},                      _send_telegram, None),
    ({"instagram", "ig", "insta"},            _send_instagram, None),
    ({"signal"},                               _send_signal, None),
    ({"discord"},                              _send_discord, None),
    ({"messenger", "facebook", "fb"},         _send_messenger, None),
]

def _resolve_platform(platform_str: str, is_call: bool = False):
    key = platform_str.lower().strip()
    for keywords, send_handler, call_handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            if is_call:
                return call_handler or (lambda r, t: f"Calls not yet automated for {platform_str}.")
            return send_handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)

def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip()
    action       = params.get("action", "send").lower().strip()

    if not receiver:
        return "Please specify a recipient."
    
    is_call = action in ("call", "voice_call", "video_call")
    call_type = "video" if action == "video_call" else "voice"
    
    if not is_call and not message_text:
        return "Please specify the message content."

    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    print(f"[SendMessage] 📨 {platform} ({action}) → {receiver}")
    if player:
        player.write_log(f"[comm] {platform} {action} → {receiver}")

    try:
        handler = _resolve_platform(platform, is_call=is_call)
        if is_call:
            result = handler(receiver, call_type)
        else:
            result = handler(receiver, message_text)
    except Exception as e:
        result = f"Could not perform communication task: {e}"

    print(f"[SendMessage] ✅ {result}")
    return result