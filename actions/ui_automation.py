# ui_automation.py
"""
Windows UIAutomation module for J.A.R.V.I.S.
Wraps Microsoft's UI Automation API via the 'uiautomation' library,
enabling precise control of any desktop application's UI elements.

Usage (from main.py tool dispatch):
    ui_automation(parameters={
        "action": "click",
        "window": "Filmora",
        "description": "New Project"
    })
"""

from __future__ import annotations

import time
from typing import Optional

try:
    import uiautomation as auto
    _UIA = True
except ImportError:
    _UIA = False


def _require_uia() -> None:
    if not _UIA:
        raise RuntimeError(
            "uiautomation not installed. Run: pip install uiautomation"
        )


# ── Helpers ───────────────────────────────────────────────────────────────

# Pre-built list of typed control method names (in order of likelihood)
_TYPED_CTRL_NAMES = [
    "ButtonControl",
    "MenuItemControl",
    "TextControl",
    "TabItemControl",
    "ListItemControl",
    "HyperlinkControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "ComboBoxControl",
    "EditControl",
    "SliderControl",
    "TreeItemControl",
    "TreeControl",
    "ImageControl",
    "PaneControl",
    "CustomControl",
    "GroupControl",
    "ToolBarControl",
    "StatusBarControl",
]


def _find_window(title: str, timeout: float = 5.0):
    """
    Find a top-level window whose Name contains *title* (case-insensitive).

    Returns the control (WindowControl, PaneControl, CustomControl, etc.)
    or None.  The caller can use .SetFocus(), .Control(), .ButtonControl()
    etc. on the returned object regardless of its concrete type.
    """
    _require_uia()
    deadline = time.time() + timeout
    root = auto.GetRootControl()

    while time.time() < deadline:
        per_try = min(0.5, max(0.2, deadline - time.time()))

        # --- Strategy 1: Direct WindowControl search (most common) ---
        # searchDepth=1 means children of the Desktop (top-level windows)
        # Quick Exists timeout: if not found, the outer loop retries
        win = auto.WindowControl(searchDepth=1, Name=title)
        if win.Exists(per_try, 0.2):
            return win

        # --- Strategy 2: Broad scan — return the matched control AS-IS ---
        # CRITICAL: Do NOT recreate as WindowControl!  Many apps
        # (Electron, WPF, WinUI3) use PaneControl or CustomControl
        # as their root window type, and recreating would search for
        # a different ControlType, causing a miss.
        for w in root.GetChildren():
            if not w.Name:
                continue
            if title.lower() in w.Name.lower():
                return w  # Return the actual control, whatever its type

        time.sleep(0.3)

    return None


def _resolve_control_type(ctrl_type: str):
    """
    Map a string control type to the uiautomation ControlType constant.
    """
    suffix_map = {
        "button":       "ButtonControl",
        "edit":         "EditControl",
        "text":         "TextControl",
        "checkbox":     "CheckBoxControl",
        "radiobutton":  "RadioButtonControl",
        "combobox":     "ComboBoxControl",
        "list":         "ListControl",
        "listitem":     "ListItemControl",
        "menu":         "MenuControl",
        "menuitem":     "MenuItemControl",
        "tab":          "TabControl",
        "tabitem":      "TabItemControl",
        "tree":         "TreeControl",
        "treeitem":     "TreeItemControl",
        "hyperlink":    "HyperlinkControl",
        "image":        "ImageControl",
        "slider":       "SliderControl",
        "scrollbar":    "ScrollBarControl",
        "statusbar":    "StatusBarControl",
        "toolbar":      "ToolBarControl",
        "tooltip":      "ToolTipControl",
        "window":       "WindowControl",
        "pane":         "PaneControl",
        "custom":       "CustomControl",
        "group":        "GroupControl",
        "titlebar":     "TitleBarControl",
    }
    attr_name = suffix_map.get(ctrl_type.lower().strip())
    if attr_name:
        return getattr(auto.ControlType, attr_name, None)
    return None


def _find_control(win,
                  description: str,
                  ctrl_type: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  search_depth: int = 0xFFFFFFFF,
                  timeout: float = 5.0):
    """
    Search for a control inside *win* by Name (*description*).

    Follows the proven pattern from send_message.py:
      btn = wa_window.ButtonControl(Name=btn_name)
      if btn.Exists(2, 0.2):          # ← positive wait, NOT 0 seconds!
          btn.Click()

    The critical fix: `Exists(maxSearchSeconds, searchIntervalSeconds)`
    with a POSITIVE maxSearchSeconds gives UIA time to populate/refresh
    its element tree.  The old code used `Exists(0, 0.1)` which polls
    ONCE against a potentially stale tree and misses controls that are
    still being enumerated.

    Tries multiple strategies in order of reliability.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        # Short per-strategy timeout — the outer while loop retries.
        # This avoids blocking for seconds on each strategy if the control
        # isn't immediately available (common in Electron/WPF apps).
        per_try = min(0.5, max(0.2, deadline - time.time()))
        poll = 0.2

        # --- Strategy 1: Typed control (if ctrl_type specified) ---
        if ctrl_type:
            ctype = _resolve_control_type(ctrl_type)
            if ctype:
                try:
                    ctrl = win.Control(Name=description, ControlType=ctype, searchDepth=search_depth)
                    if ctrl.Exists(per_try, poll):
                        return ctrl
                except Exception:
                    pass

        # --- Strategy 2: Typed control methods (proven send_message.py pattern) ---
        # wa_window.ButtonControl(Name=btn_name).Exists(2, 0.2)
        for type_name in _TYPED_CTRL_NAMES:
            if time.time() >= deadline:
                break
            method = getattr(win, type_name, None)
            if not method:
                continue
            try:
                ctrl = method(Name=description, searchDepth=search_depth)
                if ctrl.Exists(per_try, poll):
                    return ctrl
            except Exception:
                pass

        # --- Strategy 3: Generic Control search (widest net) ---
        if time.time() < deadline:
            try:
                ctrl = win.Control(Name=description, searchDepth=search_depth)
                if ctrl.Exists(per_try, poll):
                    return ctrl
            except Exception:
                pass

        # --- Strategy 4: Manual tree walk (last resort) ---
        # WalkControl uses GetFirstChildControl() / GetNextSiblingControl()
        # at a lower level, which can find controls GetChildren() misses.
        # Limit depth to 16 to avoid excessive iteration on large UIs.
        if time.time() < deadline:
            try:
                for ctrl, depth in auto.WalkControl(win, maxDepth=16):
                    name = ctrl.Name or ""
                    if description.lower() in name.lower():
                        return ctrl
                    if automation_id and ctrl.AutomationId == automation_id:
                        return ctrl
            except Exception:
                pass

        # --- Strategy 5: AutomationId search (if provided) ---
        if automation_id and time.time() < deadline:
            try:
                ctrl = win.Control(AutomationId=automation_id, searchDepth=search_depth)
                if ctrl.Exists(per_try, poll):
                    return ctrl
            except Exception:
                pass

        time.sleep(0.3)

    return None


# ── Public Actions ────────────────────────────────────────────────────────

def _action_find_window(title: str, timeout: float = 3.0) -> str:
    """Find and focus a window by its title."""
    win = _find_window(title, timeout=timeout)
    if not win:
        return f"Could not find window containing '{title}'."
    try:
        win.SetFocus()
        try:
            win.SetActive()
        except Exception:
            pass
        return f"Window '{win.Name}' found and focused."
    except Exception as e:
        return f"Found window '{win.Name}' but could not focus: {e}"


def _vision_fallback_action(description: str, action: str = "click", player=None):
    """
    Fallback: Use Gemini vision to locate an element and perform a click action.
    """
    try:
        from actions.computer_control import _screen_find
        import pyautogui
    except ImportError:
        return None

    try:
        coords = _screen_find(description)
        if coords:
            if action == "double_click":
                pyautogui.doubleClick(coords[0], coords[1])
            elif action == "right_click":
                pyautogui.rightClick(coords[0], coords[1])
            else:
                pyautogui.click(coords[0], coords[1])
            return f"{action.replace('_', ' ').title()} '{description}' at {coords} via vision fallback."
        return f"Vision fallback: could not find '{description}' on screen."
    except Exception as e:
        print(f"[UIAutomation] Vision fallback failed: {e}")
        return None


def _action_click(window: str,
                  description: str,
                  ctrl_type: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  wait_before: float = 0.0,
                  player=None) -> str:
    """Click a UI element inside a window by its name/description.

    Priority: UIAutomation → Gemini vision + pyautogui
    """
    if wait_before > 0:
        time.sleep(wait_before)

    win = _find_window(window)
    if not win:
        fallback = _vision_fallback_action(description, "click", player)
        if fallback:
            return fallback
        return f"Could not find window '{window}'. Ensure it is open."

    try:
        win.SetFocus()
        time.sleep(0.3)
    except Exception:
        pass

    ctrl = _find_control(win, description, ctrl_type, automation_id)
    if not ctrl:
        fallback = _vision_fallback_action(description, "click", player)
        if fallback:
            return fallback
        return (f"Could not find '{description}' in '{win.Name}'. "
                f"Try 'list_controls' action to see available elements.")

    try:
        ctrl.Click()
        return f"Clicked '{description}' in '{win.Name}'."
    except Exception as e:
        fallback = _vision_fallback_action(description, "click", player)
        if fallback:
            return fallback
        return f"Found '{description}' but could not click: {e}"


def _action_double_click(window: str,
                         description: str,
                         ctrl_type: Optional[str] = None,
                         wait_before: float = 0.0,
                         player=None) -> str:
    """Double-click a UI element. Falls back to vision + pyautogui if UIA fails."""
    if wait_before > 0:
        time.sleep(wait_before)

    win = _find_window(window)
    if not win:
        fallback = _vision_fallback_action(description, "double_click", player)
        if fallback:
            return fallback
        return f"Could not find window '{window}'."

    ctrl = _find_control(win, description, ctrl_type)
    if not ctrl:
        fallback = _vision_fallback_action(description, "double_click", player)
        if fallback:
            return fallback
        return f"Could not find '{description}' in '{win.Name}'."

    try:
        ctrl.DoubleClick()
        return f"Double-clicked '{description}' in '{win.Name}'."
    except Exception as e:
        fallback = _vision_fallback_action(description, "double_click", player)
        if fallback:
            return fallback
        return f"Could not double-click: {e}"


def _action_right_click(window: str,
                        description: str,
                        ctrl_type: Optional[str] = None,
                        wait_before: float = 0.0,
                        player=None) -> str:
    """Right-click a UI element. Falls back to vision + pyautogui if UIA fails."""
    if wait_before > 0:
        time.sleep(wait_before)

    win = _find_window(window)
    if not win:
        fallback = _vision_fallback_action(description, "right_click", player)
        if fallback:
            return fallback
        return f"Could not find window '{window}'."

    ctrl = _find_control(win, description, ctrl_type)
    if not ctrl:
        fallback = _vision_fallback_action(description, "right_click", player)
        if fallback:
            return fallback
        return f"Could not find '{description}' in '{win.Name}'."

    try:
        ctrl.RightClick()
        return f"Right-clicked '{description}' in '{win.Name}'."
    except Exception as e:
        fallback = _vision_fallback_action(description, "right_click", player)
        if fallback:
            return fallback
        return f"Could not right-click: {e}"


def _action_type_text(window: str,
                      text: str,
                      description: Optional[str] = None,
                      clear_first: bool = True,
                      wait_before: float = 0.0) -> str:
    """Type text into a control (or the focused control if no description)."""
    if wait_before > 0:
        time.sleep(wait_before)

    win = _find_window(window)
    if not win:
        return f"Could not find window '{window}'."

    try:
        win.SetFocus()
        time.sleep(0.2)
    except Exception:
        pass

    if description:
        ctrl = _find_control(win, description, ctrl_type="edit")
        if not ctrl:
            ctrl = _find_control(win, description)
        if not ctrl:
            return f"Could not find input '{description}' in '{win.Name}'."
        try:
            ctrl.SetFocus()
            time.sleep(0.1)
        except Exception:
            pass
        if clear_first:
            try:
                ctrl.SendKeys("{Ctrl}a")
                time.sleep(0.05)
                ctrl.SendKeys("{Delete}")
                time.sleep(0.05)
            except Exception:
                pass

    try:
        auto.SendKeys(text)
        return (f"Typed text into '{description or 'focused control'}'"
                f" in '{win.Name}'.")
    except Exception as e:
        return f"Could not type text: {e}"


def _action_get_text(window: str,
                     description: str,
                     ctrl_type: Optional[str] = None) -> str:
    """Get the text content of a UI element."""
    win = _find_window(window)
    if not win:
        return f"Could not find window '{window}'."

    ctrl = _find_control(win, description, ctrl_type)
    if not ctrl:
        return f"Could not find '{description}' in '{win.Name}'."

    try:
        text = ctrl.Name or ""
        if hasattr(ctrl, "GetValuePattern"):
            try:
                val = ctrl.GetValuePattern().Value
                if val:
                    text = val
            except Exception:
                pass
        return (f"Text of '{description}': {text[:500]}" if text
                else f"'{description}' has no text content.")
    except Exception as e:
        return f"Could not get text: {e}"


def _action_list_controls(window: str, max_items: int = 60) -> str:
    """
    List all visible controls in a window for debugging / discovery.
    Uses auto.WalkControl() for proper tree traversal — this uses
    GetFirstChildControl()/GetNextSiblingControl() at a lower level
    than GetChildren(), so it finds controls that the old _walk
    function missed.
    """
    win = _find_window(window, timeout=2.0)
    if not win:
        return f"Could not find window '{window}'."

    try:
        win.SetFocus()
        time.sleep(0.3)
    except Exception:
        pass

    lines: list[str] = []
    lines.append(f"── Controls in '{win.Name}' ──")

    count = 0
    try:
        for ctrl, depth in auto.WalkControl(win, maxDepth=16):
            if count >= max_items:
                lines.append("  ... (truncated, increase max_items to see more)")
                break
            name = (ctrl.Name or "").strip()
            ctype = ctrl.ControlTypeName or str(ctrl.ControlType)
            aid = ctrl.AutomationId or ""

            # Only show controls with a name or automation ID
            if not name and not aid:
                continue

            indent = "  " * depth
            extra = f"  [id={aid}]" if aid else ""
            lines.append(f"{indent}• {name[:60]}  ({ctype}){extra}")
            count += 1
    except Exception as e:
        lines.append(f"  (tree walk error: {e})")

    if count == 0:
        lines.append("(no named controls found - this app likely uses custom/web rendering)")

    return "\n".join(lines)


def _action_invoke(window: str,
                   description: str,
                   wait_before: float = 0.0) -> str:
    """Invoke the default action of a control (like clicking)."""
    if wait_before > 0:
        time.sleep(wait_before)

    win = _find_window(window)
    if not win:
        return f"Could not find window '{window}'."

    ctrl = _find_control(win, description)
    if not ctrl:
        return f"Could not find '{description}' in '{win.Name}'."

    try:
        ctrl.Invoke()
        return f"Invoked '{description}' in '{win.Name}'."
    except Exception as e:
        return f"Could not invoke '{description}': {e}"


def _action_screenshot(window: str, output_path: Optional[str] = None) -> str:
    """Capture a screenshot of a window's bounding rectangle."""
    win = _find_window(window)
    if not win:
        return f"Could not find window '{window}'."

    try:
        import pyautogui
    except ImportError:
        return "pyautogui required for screenshots."

    try:
        rect = win.BoundingRectangle
        if not rect or (rect.right - rect.left < 10):
            return "Window has no valid bounding rectangle."

        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        screenshot = pyautogui.screenshot(region=(left, top, right - left, bottom - top))

        if output_path:
            screenshot.save(output_path)
            return f"Screenshot saved to {output_path}."
        else:
            path = f"Desktop/JarvisVision/ui_{int(time.time())}.png"
            from pathlib import Path
            full_path = Path.home() / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(str(full_path))
            return f"Screenshot saved to {full_path}."
    except Exception as e:
        return f"Screenshot failed: {e}"


# ── Dispatcher ────────────────────────────────────────────────────────────

def ui_automation(parameters: dict,
                  response=None,
                  player=None,
                  session_memory=None) -> str:
    """
    Main entry point for UI Automation tool dispatch.

    Parameters:
        action (str, required):
            find_window | click | double_click | right_click |
            type_text | get_text | list_controls | invoke | screenshot
        window (str): Title or partial title of the target window
        description (str): Name/label of the UI element to interact with
        ctrl_type (str): Optional filter: button | edit | text | checkbox |
                         combobox | listitem | menuitem | tab | hyperlink |
                         slider | treeitem | toolbar | pane | group | custom
        automation_id (str): Optional automation ID for precise targeting
        text (str): Text to type (for type_text action)
        clear_first (bool): Clear field before typing (default: True)
        wait_before (float): Seconds to wait before action
        max_items (int): Max items for list_controls (default: 60)
        output_path (str): Save path for screenshot
    """
    _require_uia()

    params = parameters or {}
    action = params.get("action", "").lower().strip()
    window = params.get("window", "")
    desc   = params.get("description", "")

    if not action:
        return "No action specified. Use: find_window, click, double_click, right_click, type_text, get_text, list_controls, invoke, screenshot"

    if player:
        player.write_log(f"[UIA] {action}  window={window}  target={desc}")

    print(f"[UIAutomation] ▶ {action}  window='{window}'  target='{desc}'")

    try:
        if action == "find_window":
            return _action_find_window(window, float(params.get("timeout", 3.0)))

        elif action == "click":
            return _action_click(
                window, desc,
                ctrl_type=params.get("ctrl_type"),
                automation_id=params.get("automation_id"),
                wait_before=float(params.get("wait_before", 0.0)),
                player=player,
            )

        elif action == "double_click":
            return _action_double_click(
                window, desc,
                ctrl_type=params.get("ctrl_type"),
                wait_before=float(params.get("wait_before", 0.0)),
                player=player,
            )

        elif action == "right_click":
            return _action_right_click(
                window, desc,
                ctrl_type=params.get("ctrl_type"),
                wait_before=float(params.get("wait_before", 0.0)),
                player=player,
            )

        elif action == "type_text":
            text = params.get("text", "")
            if not text:
                return "No 'text' parameter provided for type_text."
            return _action_type_text(
                window, text,
                description=desc or None,
                clear_first=bool(params.get("clear_first", True)),
                wait_before=float(params.get("wait_before", 0.0)),
            )

        elif action == "get_text":
            if not desc:
                return "No 'description' parameter provided for get_text."
            return _action_get_text(window, desc, ctrl_type=params.get("ctrl_type"))

        elif action == "list_controls":
            return _action_list_controls(window, int(params.get("max_items", 60)))

        elif action == "invoke":
            return _action_invoke(
                window, desc,
                wait_before=float(params.get("wait_before", 0.0)),
            )

        elif action == "screenshot":
            return _action_screenshot(window, params.get("output_path"))

        else:
            return (f"Unknown action: '{action}'. "
                    f"Valid: find_window, click, double_click, right_click, "
                    f"type_text, get_text, list_controls, invoke, screenshot")

    except Exception as e:
        err = f"UIAutomation error ({action}): {e}"
        print(f"[UIAutomation] ❌ {err}")
        return err
