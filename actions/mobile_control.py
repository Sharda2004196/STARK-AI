import os
import subprocess
import time
import re
import tempfile
import io
import uiautomator2 as u2
import adbutils
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from PIL import Image
from config.genai_client import generate_content
from google.genai import types as gtypes

# --- CORE INFRASTRUCTURE ---

_device = None

def get_device():
    """Wireless-First Connection: Automatically discovers the device via MDNS or existing ADB sessions."""
    global _device
    
    if _device:
        try:
            _ = _device.info
            return _device
        except:
            _device = None

    try:
        def get_online_serials():
            return [info.serial for info in adbutils.adb.list() if info.state == "device"]

        online_serials = get_online_serials()
        
        # AUTO-DISCOVERY (Wireless MDNS)
        if not online_serials:
            res = subprocess.run(["adb", "mdns", "services"], capture_output=True, text=True, timeout=5)
            mdns_matches = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)", res.stdout)
            for addr in mdns_matches:
                subprocess.run(["adb", "connect", addr], timeout=3, capture_output=True)
            online_serials = get_online_serials()

        if not online_serials: return None 

        target = next((s for s in online_serials if "." in s or ":" in s), online_serials[0])
        _device = u2.connect(target)
        
        try:
            _ = _device.info
        except:
            _device.reset_uiautomator()
            
        return _device
    except Exception as e:
        print(f"[Mobile] Wireless Discovery Error: {e}")
        _device = None
    return None

def _run_adb(args: list) -> str:
    """Helper to run ADB commands via u2's shell interface."""
    d = get_device()
    if not d: return ""
    res = d.shell(args)
    return res.output.strip()

def _get_pkg(name: str) -> str:
    """Finds package ID. Prioritizes exact matches, then searches device."""
    low_name = name.lower().strip()
    overrides = {
        "youtube": "com.google.android.youtube",
        "whatsapp": "com.whatsapp",
        "chrome": "com.android.chrome",
        "playstore": "com.android.vending",
        "gmail": "com.google.android.gm",
        "maps": "com.google.android.apps.maps",
        "chatgpt": "com.openai.chatgpt",
        "claude": "com.anthropic.claude",
        "contacts": "com.android.contacts",
        "camera": "com.android.camera",
        "music": "com.google.android.apps.youtube.music",
        "spotify": "com.spotify.music",
        "instagram": "com.instagram.android",
        "gallery": "com.google.android.apps.photos",
        "capcut": "com.lemon.lvoverseas",
        "settings": "com.android.settings",
        "files": "com.google.android.apps.nbu.files",
        "drive": "com.google.android.apps.docs",
        "meet": "com.google.android.apps.tachyon",
        "gemini": "com.google.android.apps.bard"
    }
    if low_name in overrides: return overrides[low_name]
    
    try:
        output = _run_adb(["pm", "list", "packages", low_name])
        if "package:" in output:
            pkgs = [line.replace("package:", "").strip() for line in output.splitlines() if "package:" in line]
            return min(pkgs, key=len)
    except: pass
    return low_name

# --- SMART UI INTERACTION ---

def _smart_click(identifier: str, player=None) -> bool:
    """Sequentially searches for elements by text, description, or ID."""
    d = get_device()
    if not d: return False
    
    selectors = [
        d(text=identifier),
        d(textContains=identifier),
        d(description=identifier),
        d(descriptionContains=identifier),
        d(resourceId=identifier),
        d(resourceIdMatches=f".*/{identifier}")
    ]
    
    for s in selectors:
        if s.exists(timeout=1.0):
            s.click()
            if player: player.write_log(f"Mobile: Found '{identifier}' via UI Tree.")
            return True
            
    return _vision_click(identifier, player=player)

def _smart_type(text: str, identifier: str = None, player=None) -> bool:
    """Types text into a field identified by ID/Text or the currently focused field."""
    d = get_device()
    if not d: return False
    
    if identifier:
        s = d(resourceId=identifier) or d(text=identifier) or d(description=identifier)
        if s.exists(timeout=1.5):
            s.set_text(text)
            return True
            
    d.send_keys(text)
    return True

def _scroll(direction: str = "down"):
    d = get_device()
    if not d: return
    if direction == "down": d.swipe_ext("up", scale=0.8)
    else: d.swipe_ext("down", scale=0.8)

def _swipe(start: Tuple[int, int], end: Tuple[int, int]):
    d = get_device()
    if d: d.swipe(start[0], start[1], end[0], end[1])

# --- VISION FALLBACK ---

def _get_screenshot_bytes() -> bytes:
    """Captures a screenshot from the mobile and returns PNG bytes."""
    d = get_device()
    if not d: return b""
    try:
        # ponytail: u2 v3.x returns PIL image, convert to bytes manually
        img = d.screenshot()
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        print(f"[Mobile] Screenshot Error: {e}")
        return b""

def _vision_locate_element(description: str, player=None) -> Optional[Tuple[int, int]]:
    if player: player.write_log(f"Vision: Locating '{description}'...")
    img_data = _get_screenshot_bytes()
    if not img_data: return None
    
    d = get_device()
    w, h = d.window_size()
    prompt = (
        f"Mobile Screen ({w}x{h}). Find center [X, Y] for: '{description}'. "
        "Return ONLY '[X, Y]' or 'NOT_FOUND'."
    )

    try:
        response = generate_content(
            model="gemini-3.1-flash-lite",
            contents=[gtypes.Part.from_bytes(data=img_data, mime_type="image/png"), prompt],
            config=gtypes.GenerateContentConfig(temperature=0.0)
        )
        text = response.strip()
        match = re.search(r"\[(\d+),\s*(\d+)\]", text)
        if match: return int(match.group(1)), int(match.group(2))
    except Exception as e:
        print(f"[MobileVision] Error: {e}")
    return None

def _vision_click(description: str, player=None, retries: int = 1) -> bool:
    for _ in range(retries):
        coords = _vision_locate_element(description, player=player)
        if coords:
            get_device().click(coords[0], coords[1])
            return True
    return False

# --- MAIN CONTROLLER ---

def mobile_control(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "").lower()
    value  = parameters.get("value", "")   
    text   = parameters.get("text", "")    
    message = parameters.get("message", "") 
    
    d = get_device()
    if not d: return "Mobile Error: No device connection."

    if player: player.write_log(f"Mobile: {action}...")

    try:
        if action == "whatsapp_message":
            target = text or value
            msg = message or "Hello"
            d.app_start("com.whatsapp", stop=True)
            if _smart_click("Search", player):
                d.send_keys(target)
                d.press("enter")
                if not _smart_click(target, player): d.click(300, 300) 
            d.send_keys(msg)
            d.press("enter")
            return f"Sent WhatsApp message to {target}."

        elif action == "whatsapp_call":
            target = text or value
            d.app_start("com.whatsapp", stop=True)
            # ponytail: search and enter is faster than waiting for lists to load
            if _smart_click("Search", player):
                d.send_keys(target)
                d.press("enter")
                if _smart_click(target, player):
                    if _smart_click("Voice call", player) or _smart_click("Call", player):
                        _smart_click("CALL", player)
                        return f"Initiated WhatsApp call to {target}."
            return f"Opened WhatsApp for {target}."

        elif action == "direct_call":
            target = text or value
            clean_num = re.sub(r"[^\d+]", "", str(target))
            if clean_num and len(clean_num) >= 7:
                d.shell(["am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{clean_num}"])
                _smart_click("Call", player) or _smart_click("Dial", player) or d.click(500, 1800)
                return f"Dialed {clean_num}."
            
            d.app_start(_get_pkg("contacts"), stop=True)
            if _smart_click("Search", player) or _smart_click("Find", player):
                d.send_keys(target)
                d.press("enter")
                if _smart_click(target, player):
                    _smart_click("Call", player) or _smart_click("phone", player)
                    return f"Calling {target}."
            return f"Opened contacts for {target}."

        elif action == "youtube_play":
            d.app_start("com.google.android.youtube", stop=True)
            time.sleep(3)
            if _smart_click("Search", player):
                d.send_keys(value)
                d.press("enter") # ponytail: triggers the search
                time.sleep(3)
                d.click(500, 600)
                return f"Playing '{value}' on YouTube."
            return "Failed to trigger YouTube search."

        elif action == "web_search":
            d.app_start("com.android.chrome", stop=True)
            time.sleep(2)
            if _smart_click("Search", player) or _smart_click("Address bar", player) or _smart_click("Search or type URL", player):
                d.send_keys(value)
                d.press("enter") # ponytail: triggers the search
                return f"Searching for '{value}' on Chrome."
            d.app_start("com.google.android.googlequicksearchbox", stop=True)
            time.sleep(2)
            d.send_keys(value)
            d.press("enter")
            return f"Searching for '{value}' via Google."

        elif action == "open_app":
            pkg = _get_pkg(value)
            d.app_start(pkg, use_monkey=True)
            return f"Launched {value}."

        elif action == "close_app":
            pkg = _get_pkg(value)
            d.app_stop(pkg)
            return f"Stopped {value}."

        elif action == "home":
            d.press("home")
            return "Returned Home."

        elif action == "back":
            d.press("back")
            return "Pressed Back."

        elif action == "scroll":
            _scroll(value or "down")
            return f"Scrolled {value or 'down'}."

        elif action == "swipe":
            try:
                c = [int(x) for x in value.split(",")]
                _swipe((c[0], c[1]), (c[2], c[3]))
                return "Swiped."
            except: return "Invalid coordinates."

        elif action == "click":
            if _smart_click(value, player): return f"Clicked '{value}'."
            return f"Not found: '{value}'."

        elif action == "volume_up":
            d.press("volume_up")
            return "Volume increased."

        elif action == "volume_down":
            d.press("volume_down")
            return "Volume decreased."

        elif action == "set_brightness":
            # value expected as 0-255 or 0-100%
            try:
                val = int(re.sub(r"[^\d]", "", str(value)))
                if "%" in str(value) or val <= 100:
                    val = int((val / 100) * 255)
                # ponytail: use shell for deep system settings
                d.shell(["settings", "put", "system", "screen_brightness", str(val)])
                return f"Brightness set to {value}."
            except: return "Failed to set brightness."

        elif action == "type":
            d.send_keys(value)
            return f"Typed '{value}'."

        elif action == "unlock":
            d.screen_on(); d.unlock()
            return "Unlock sent."

        elif action == "screenshot":
            p = Path.home() / "Desktop" / "JarvisVision" / f"mobile_{int(time.time())}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            d.screenshot(str(p))
            return f"Saved to {p.name}."

        return f"Action '{action}' complete."

    except Exception as e:
        return f"Mobile Error: {e}"
