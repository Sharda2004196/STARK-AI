# computer_control.py
import io
import json
import re
import string
import subprocess
import sys
import time
import random
from pathlib import Path
from typing import Optional, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

try:
    from pywinauto import Desktop as WinDesktop
    _PYWINAUTO = True
except ImportError:
    _PYWINAUTO = False

# --- CONFIG & PATHS ---

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "api_keys.json"
_MEMORY_PATH  = _BASE / "memory" / "long_term.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except: return {}

def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")

# --- STRUCTURAL UI INTERACTION (Windows Native) ---

def _win_click(identifier: str) -> bool:
    """Attempts to click a Windows UI element by name using structural tree."""
    if not _PYWINAUTO: return False
    try:
        # ponytail: searches all top-level windows for a matching button/item
        windows = WinDesktop(backend="uia").windows()
        for win in windows:
            if not win.is_visible(): continue
            try:
                # Search for button, child window, or menu item
                # Added title_re for fuzzy matching and auto_id fallback
                element = win.child_window(title_re=f".*{identifier}.*", found_index=0)
                if element.exists(timeout=1):
                    element.click_input()
                    return True
            except: continue
        return False
    except: return False

# --- VISION FLASH ENGINE (Gemini 2.5 Flash) ---

def _screen_find(description: str) -> Optional[Tuple[int, int]]:
    """Uses Gemini 2.5 Flash for ultra-fast coordinate localization."""
    api_key = _get_api_key()
    if not api_key: return None

    try:
        from google import genai
        from google.genai import types as gtypes

        w, h  = pyautogui.size()
        img   = pyautogui.screenshot()
        buf   = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        client = genai.Client(api_key=api_key)
        # ponytail: specific prompt for coordinate mapping
        prompt = (
            f"Screen: {w}x{h}. Target: '{description}'. "
            "Locate this element and return ONLY the center [X, Y] coordinates. "
            "If not visible, return 'NOT_FOUND'."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash", # ponytail: Flash 2.0 is the current best for speed/vision
            contents=[gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"), prompt],
            config=gtypes.GenerateContentConfig(temperature=0.0)
        )

        text = (response.text or "").strip()
        match = re.search(r"\[?(\d+)\s*,\s*(\d+)\]?", text)
        if match: return int(match.group(1)), int(match.group(2))
    except Exception as e:
        print(f"[ComputerControl] Vision failed: {e}")
    return None

# --- CORE ACTIONS ---

def _smart_click(description: str, player=None) -> str:
    """Hybrid: Structural click -> Vision click fallback."""
    if player: player.write_log(f"Searching for '{description}'...")
    
    # 1. Try structural Windows click (Fast & Native)
    if _win_click(description):
        return f"Clicked '{description}' via Windows UI tree."
    
    # 2. Try Vision Flash (Precise for custom/web/app UIs)
    coords = _screen_find(description)
    if coords:
        pyautogui.click(coords[0], coords[1])
        return f"Clicked '{description}' at {coords} via Vision."
    
    return f"Failed to find '{description}' on screen."

def _scroll_precise(direction: str, amount: int = 500):
    """High-precision pixel scrolling."""
    if direction == "down": pyautogui.scroll(-amount)
    elif direction == "up": pyautogui.scroll(amount)
    return f"Scrolled {direction} by {amount} pixels."

# --- DISPATCHER ---

def computer_control(parameters: dict, player=None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    
    if player: player.write_log(f"[Computer] {action}")
    print(f"[ComputerControl] ▶ {action}  {params}")

    try:
        if action == "screen_click":
            return _smart_click(params.get("description", ""), player)

        if action == "type":
            text = params.get("text", "")
            pyautogui.typewrite(text, interval=0.02)
            return f"Typed: {text[:30]}..."

        if action == "press":
            key = params.get("key", "enter")
            pyautogui.press(key)
            return f"Pressed: {key}"

        if action == "hotkey":
            keys = params.get("keys", "").split("+")
            pyautogui.hotkey(*[k.strip() for k in keys])
            return f"Hotkey: {params.get('keys')}"

        if action == "scroll":
            return _scroll_precise(params.get("direction", "down"), int(params.get("amount", 500)))

        if action == "focus_window":
            title = params.get("title", "")
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
            return f"Focused: {title}"

        if action == "screenshot":
            path = Path.home() / "Desktop" / "JarvisVision" / f"pc_{int(time.time())}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            pyautogui.screenshot().save(str(path))
            return f"Saved screenshot to Desktop/JarvisVision."

        # ponytail: Fallback for older action names
        if action == "click":
            x, y = params.get("x"), params.get("y")
            if x is not None: pyautogui.click(x, y); return f"Clicked ({x}, {y})"
            return _smart_click(params.get("description", ""), player)

    except Exception as e:
        return f"Error: {e}"

    return f"Unknown action: {action}"
