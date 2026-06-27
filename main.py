import asyncio
import re
import threading
import json
import sys
import traceback
from pathlib import Path

# Match any standard WebSocket close code (1000–1011) for session rotation detection
_WS_CLOSE_RE = re.compile(r"\b(100[0-9]|101[01])\b")

import sounddevice as sd
from google import genai
from google.genai import types, errors
from ui import JarvisUI
from memory.mem0_memory import Mem0Memory

from actions.file_processor    import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.image_generation  import JarvisImageEngine
from actions.content_studio   import content_studio
from actions.frontend_builder  import frontend_builder
from actions.prompt_optimizer  import prompt_optimizer
from actions.apk_builder       import apk_builder
from actions.extension_builder import extension_builder
from actions.mobile_control    import mobile_control
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.gesture_control   import gesture_control
from actions.composio_tools    import JarvisToolManager
from actions.video_editing     import video_editing
from actions.doc_creator       import doc_creator
from actions.ui_automation    import ui_automation
from actions.notebooklm       import notebooklm_controller
try:
    from actions.attention_monitor import AttentionMonitor, handle_call_action, read_event_preview
except ImportError:
    AttentionMonitor = None
    handle_call_action = None
    read_event_preview = None
try:
    from actions.meeting_analyzer import MeetingAssistant
except ImportError:
    MeetingAssistant = None


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-3.1-flash-live-preview"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on THIS COMPUTER (PC). "
            "Use this for WhatsApp Desktop, Chrome, Spotify, etc. "
            "DO NOT use for mobile/phone apps."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the PC application"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": (
            "Sends a text message or starts a voice call on THIS COMPUTER (PC) "
            "using apps like WhatsApp, Telegram, etc. Actions:\n"
            "- send: Text message (requires message_text).\n"
            "- call: Voice call (initiates search + call process)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Contact name on PC"},
                "message_text": {"type": "STRING", "description": "Text to send (omit for calls)"},
                "platform":     {"type": "STRING", "description": "whatsapp | telegram | signal"},
                "action":       {"type": "STRING", "description": "send (default) | call (voice call)"}
            },
            "required": ["receiver", "platform"]
        }
    },
    {
        "name": "generate_image",
        "description": "Generates high-fidelity static graphics using Pollinations FLUX. By DEFAULT always use aspect_ratio='1:1' (square). Only use 16:9 or 9:16 if the user EXPLICITLY asks for widescreen, cinematic, or mobile wallpaper.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {"type": "STRING", "description": "Detailed description of the image"},
                "aspect_ratio": {"type": "STRING", "description": "1:1 (default, square) | 3:4 | 4:3 | 16:9 (only if user asks) | 9:16 (only if user asks)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "content_studio",
        "description": "A specialized Multi-Agent Studio for social media content (YouTube, Instagram, LinkedIn).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING", "description": "What content needs to be created (e.g. 'Write a YouTube script about space')"},
                "image_path": {"type": "STRING", "description": "Optional path to a reference image/photo"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "frontend_builder",
        "description": "Builds immersive, beautiful, and fully functional web apps. Supports 3D, animations, and multi-view SPA interactivity.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":  {"type": "STRING", "description": "Detailed description of the UI (e.g. 'functional 3D dashboard')"},
                "theme": {"type": "STRING", "description": "dark | light | glassmorphism | neo-brutalism | modern"},
                "stack": {"type": "STRING", "description": "vanilla | tailwind | react-cdn (default: vanilla)"},
                "count": {"type": "INTEGER", "description": "Number of variations. Use 1 unless 'multiple' requested."}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "prompt_optimizer",
        "description": "Engineers and returns a highly detailed prompt string to the user. Use ONLY when the user explicitly asks for a 'prompt' to be generated or optimized.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "raw_request": {"type": "STRING", "description": "The user's original idea or multilingual request"},
                "target_tool": {"type": "STRING", "description": "image | frontend | code | general"}
            },
            "required": ["raw_request"]
        }
    },
    {
        "name": "apk_builder",
        "description": "Architects and generates the ENTIRE Kotlin source code and structure for a native Android application in one shot. REQUIRED for all mobile, Android, or APK requests. Once called, the task is considered finished.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Name of the app (e.g., 'FlashlightPro')"},
                "features": {"type": "STRING", "description": "Detailed description of the app's UI and logic"}
            },
            "required": ["app_name", "features"]
        }
    },
    {
        "name": "extension_builder",
        "description": "Architects and generates multi-file, production-ready browser extensions (Chrome/Edge).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "extension_name": {"type": "STRING", "description": "Name of the extension"},
                "features": {"type": "STRING", "description": "Detailed description of the features"}
            },
            "required": ["extension_name", "features"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls and analyzes videos from YouTube, Instagram, and more. Use for:\n"
            "- play: Search and watch a video.\n"
            "- summarize: Get a text summary from the transcript.\n"
            "- analyze: Perform deep visual analysis on frames (works for YouTube, Insta, etc.).\n"
            "- get_info: Extract metadata (views, likes, etc.).\n"
            "- trending: Show popular videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "play | summarize | analyze | get_info | trending"},
                "query":     {"type": "STRING", "description": "Search query or question about the video content"},
                "url":       {"type": "STRING", "description": "URL of the video (YouTube, Instagram, MP4, etc.)"},
                "timestamp": {"type": "STRING", "description": "Optional: Specific moment to analyze (MM:SS)"},
                "save":      {"type": "BOOLEAN", "description": "Save result to file (summarize only)"},
                "region":    {"type": "STRING", "description": "Country code for trending (default: TR)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, JARVIS will read the result aloud to the user."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | bave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors. Do NOT use this tool for building Android apps or APKs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": (
            "Coordinate-based and keyboard control. Actions:\n"
            "- click: Click by [x, y] coordinates only.\n"
            "- type / press / hotkey: Input text or keys.\n"
            "- scroll: Precise pixel-based scrolling (direction='up'|'down', amount=pixels).\n"
            "- focus_window: Bring a specific app to foreground by title.\n"
            "- screenshot: Capture the PC screen.\n"
            "- screen_click: Low-confidence vision fallback — uses AI to guess where an element is.\n"
            "\n"
            "IMPORTANT: For clicking buttons/menus/UI elements by their VISIBLE LABEL or NAME, "
            "use 'ui_automation' instead. This tool (computer_control) cannot find elements by name — "
            "it only clicks at raw coordinates or guesses via vision."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "click | type | press | hotkey | scroll | focus_window | screenshot | screen_click"},
                "description": {"type": "STRING", "description": "Element description for screen_click (low-confidence vision fallback)"},
                "text":        {"type": "STRING", "description": "Text to type"},
                "key":         {"type": "STRING", "description": "Key name (e.g. 'enter')"},
                "keys":        {"type": "STRING", "description": "Hotkey (e.g. 'ctrl+c')"},
                "direction":   {"type": "STRING", "description": "up | down"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "title":       {"type": "STRING", "description": "Window title to focus"},
                "x":           {"type": "INTEGER"},
                "y":           {"type": "INTEGER"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "video_editing",
        "description": (
            "Performs advanced video editing tasks. Available actions:\n"
            "- trim / cut: Slices video (use 'start' and 'end' parameters).\n"
            "- add_music / add_audio: Replaces/adds audio track.\n"
            "- animate / zoom / glow / fade / fade_in_out: Applies visual effects.\n"
            "- add_text / caption: Overlays text on video.\n"
            "- merge / stitch / combine: Joins multiple video clips.\n"
            "- beat_sync: Creates a hype edit synced to audio beats.\n"
            "Use this for ANY visual video modification request (glow, text, sync, etc.)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING", "description": "trim | add_music | animate | add_text | merge | beat_sync"},
                "video_path":   {"type": "STRING", "description": "Path to the video file"},
                "audio_path":   {"type": "STRING", "description": "Path to the audio/music file"},
                "video_paths":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "List of video paths for merge"},
                "video_folder": {"type": "STRING", "description": "Folder containing clips for beat_sync"},
                "output_path":  {"type": "STRING", "description": "Where to save the result"},
                "start":        {"type": "NUMBER", "description": "Start time in seconds for trim"},
                "end":          {"type": "NUMBER", "description": "End time in seconds for trim"},
                "volume":       {"type": "NUMBER", "description": "Volume scale for music (0.0 to 1.0)"},
                "text":         {"type": "STRING", "description": "Text to overlay"},
                "font":         {"type": "STRING", "description": "Font name (e.g. Arial, Verdana)"},
                "fontsize":     {"type": "INTEGER", "description": "Text size"},
                "color":        {"type": "STRING", "description": "Text color (e.g. white, red, #FF0000)"},
                "position":     {"type": "STRING", "description": "Position (e.g. center, top, bottom, (10, 10))"},
                "zoom":         {"type": "STRING", "description": "zoom 'in' or 'out'"},
                "glow":         {"type": "BOOLEAN", "description": "Enable glow effect"},
                "fade_in":      {"type": "NUMBER", "description": "Fade in duration in seconds"},
                "fade_out":     {"type": "NUMBER", "description": "Fade out duration in seconds"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "handle_call",
        "description": "Answers or declines an incoming call on apps like Zoom, Teams, Skype, WhatsApp, etc. Use this when the user says 'answer it', 'decline', 'pick up', 'hang up'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "accept | decline"},
                "app": {"type": "STRING", "description": "The name of the app the call is on (e.g., 'Zoom', 'Teams')"}
            },
            "required": ["action", "app"]
        }
    },
    {
        "name": "meeting_analyzer",
        "description": "Starts or stops continuous analysis of a meeting (screen and audio). Use this when the user asks to analyze a meeting, watch the screen during a meeting, or stop monitoring a meeting.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "start | stop | update_context"},
                "title":   {"type": "STRING", "description": "Optional: Title of the meeting (e.g., 'Weekly Sync', 'Project Alpha Kickoff')"},
                "context": {"type": "STRING", "description": "Optional: Any extra context for the meeting (e.g., 'Discuss Q3 goals', 'Competitor analysis')"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "mobile_control",
        "description": (
            "Full Control Mobile Agent. Use ONLY if the user says 'on my mobile', 'on my phone', or 'Android'. "
            "Controls a connected Android phone via UIAutomator2. Actions:\n"
            "- open_app / close_app: Launch or force-stop a mobile app.\n"
            "- direct_call: Make a regular cellular call by name or number.\n"
            "- whatsapp_message / whatsapp_call: Send a text or start a WhatsApp call.\n"
            "- youtube_play: Search and play a specific song/video on YouTube.\n"
            "- web_search: Search for a topic on Chrome or Google app.\n"
            "- scroll / swipe: Navigate the screen.\n"
            "- click / type: Interact with UI elements.\n"
            "- home / back / unlock: System navigation.\n"
            "- screenshot: Capture the mobile screen."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open_app | close_app | direct_call | whatsapp_message | whatsapp_call | youtube_play | web_search | scroll | swipe | click | type | home | back | unlock | screenshot | volume_up | volume_down | set_brightness"},
                "value":  {"type": "STRING", "description": "Target text, app name, search query, scroll direction, or swipe coordinates"},
                "text":   {"type": "STRING", "description": "Contact name or phone number"},
                "message": {"type": "STRING", "description": "The message content"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "composio_task",
        "description": (
            "Use ONLY for EXTERNAL CLOUD automation (GitHub, Google Sheets, Notion). "
            "NEVER use for local PC apps or mobile phone control."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {"type": "STRING", "description": "The cloud task instruction"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "gesture_control",
        "description": "Enables or disables controlling the computer via hand gestures using the webcam.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"}
            },
            "required": ["action"]
        }
    },

    {
        "name": "ui_automation",
        "description": (
            "PRIMARY tool for clicking or interacting with ANY desktop application's buttons, "
            "menus, text fields, and UI elements by their visible label/name. "
            "Uses Windows UIAutomation to read the actual UI element tree "
            "(the same API screen readers use).\n\n"
            "USE THIS INSTEAD OF 'computer_control' FOR:\n"
            "- Clicking 'New Project' in Filmora\n"
            "- Clicking 'Create Playlist' in Spotify\n"
            "- Clicking any button, menu, or item by its LABEL/TEXT\n"
            "- Typing text into input fields in any app\n"
            "- Reading text from UI elements\n"
            "- Discovering what buttons exist via list_controls\n\n"
            "ALWAYS call 'list_controls' FIRST to discover the exact element names, "
            "then use those names with 'click' or other actions.\n\n"
            "Automatically falls back to vision-based clicking if UIA cannot find the element.\n"
            "Actions:\n"
            "- click: Click a button/menu/item by its visible label text.\n"
            "- list_controls: Discover all interactable elements in a window.\n"
            "- find_window: Locate and focus an application window by title.\n"
            "- double_click / right_click: Alternative click types.\n"
            "- type_text: Type text into an input field (optionally clear first).\n"
            "- get_text: Read text from a UI element.\n"
            "- invoke: Trigger the default action of a control.\n"
            "- screenshot: Capture the window's appearance."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "click | list_controls | find_window | double_click | right_click | type_text | get_text | invoke | screenshot"
                },
                "window": {
                    "type": "STRING",
                    "description": "Title or partial title of the target application window (e.g. 'Filmora', 'WhatsApp', 'Notepad')"
                },
                "description": {
                    "type": "STRING",
                    "description": "Name/label/text of the UI element to interact with (e.g. 'New Project', 'OK', 'Open')"
                },
                "ctrl_type": {
                    "type": "STRING",
                    "description": "Optional filter: button | edit | text | checkbox | combobox | listitem | menuitem | tab | hyperlink | slider | pane | group"
                },
                "automation_id": {
                    "type": "STRING",
                    "description": "Optional automation ID for precise element targeting"
                },
                "text": {
                    "type": "STRING",
                    "description": "Text to type (for type_text action)"
                },
                "clear_first": {
                    "type": "BOOLEAN",
                    "description": "Clear field before typing (default: true)"
                },
                "wait_before": {
                    "type": "NUMBER",
                    "description": "Seconds to wait before the action (default: 0)"
                },
                "max_items": {
                    "type": "INTEGER",
                    "description": "Max items for list_controls (default: 60)"
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Save path for screenshot"
                },
                "timeout": {
                    "type": "NUMBER",
                    "description": "Seconds to wait for find_window (default: 3)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "notebooklm",
        "description": (
            "Integrates with Google NotebookLM for AI-powered research, "
            "content generation, and grounded knowledge management.\n\n"
            "REQUIRES: Run 'notebooklm login' in terminal once to authenticate.\n\n"
            "NOTEBOOK OPERATIONS:\n"
            "  - list_notebooks\n"
            "  - create_notebook (title)\n"
            "  - delete_notebook (notebook_id)\n"
            "  - get_notebook (notebook_id)\n\n"
            "SOURCE OPERATIONS:\n"
            "  - add_source_url (notebook_id, url)\n"
            "  - add_source_file (notebook_id, file_path)\n"
            "  - add_source_text (notebook_id, title, content)\n"
            "  - add_web_research (notebook_id, query, mode=fast|deep)\n"
            "  - list_sources (notebook_id)\n\n"
            "CHAT:\n"
            "  - ask (notebook_id, query)\n\n"
            "CONTENT GENERATION:\n"
            "  - generate_audio (notebook_id, instructions)\n"
            "  - generate_video (notebook_id, instructions, style)\n"
            "  - generate_cinematic_video (notebook_id, instructions)\n"
            "  - generate_quiz (notebook_id, difficulty, quantity)\n"
            "  - generate_flashcards (notebook_id, quantity)\n"
            "  - generate_slide_deck (notebook_id, instructions)\n"
            "  - generate_report (notebook_id, format, instructions)\n"
            "  - generate_infographic (notebook_id, orientation, detail)\n"
            "  - generate_data_table (notebook_id, instructions)\n"
            "  - generate_mind_map (notebook_id, kind)\n\n"
            "DOWNLOAD:\n"
            "  - download (notebook_id, artifact_type, output_path, format)\n\n"
            "UTILITIES:\n"
            "  - list_artifacts (notebook_id)\n"
            "  - status"
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "The NotebookLM operation to perform.\n"
                        "Notebooks: list_notebooks | create_notebook | delete_notebook | get_notebook\n"
                        "Sources: add_source_url | add_source_file | add_source_text | add_web_research | list_sources\n"
                        "Chat: ask\n"
                        "Generate: generate_audio | generate_video | generate_cinematic_video | "
                        "generate_quiz | generate_flashcards | generate_slide_deck | generate_report | "
                        "generate_infographic | generate_data_table | generate_mind_map\n"
                        "Download: download\n"
                        "Utility: list_artifacts | status"
                    )
                },
                "notebook_id": {
                    "type": "STRING",
                    "description": "ID of the NotebookLM notebook (returned by create_notebook or list_notebooks)"
                },
                "title": {
                    "type": "STRING",
                    "description": "Title for create_notebook or add_source_text"
                },
                "url": {
                    "type": "STRING",
                    "description": "URL to add as a source (for add_source_url)"
                },
                "file_path": {
                    "type": "STRING",
                    "description": "Path to a file to add as a source (PDF, text, etc.)"
                },
                "content": {
                    "type": "STRING",
                    "description": "Text content for add_source_text"
                },
                "query": {
                    "type": "STRING",
                    "description": "Question/research query for ask or add_web_research"
                },
                "instructions": {
                    "type": "STRING",
                    "description": "Instructions/prompt for content generation"
                },
                "mode": {
                    "type": "STRING",
                    "description": "Research mode: fast (quick) or deep (thorough)"
                },
                "style": {
                    "type": "STRING",
                    "description": "Video style: explainer | brief | cinematic"
                },
                "difficulty": {
                    "type": "STRING",
                    "description": "Quiz difficulty: easy | medium | hard"
                },
                "quantity": {
                    "type": "INTEGER",
                    "description": "Number of quiz questions or flashcards to generate"
                },
                "format": {
                    "type": "STRING",
                    "description": "Report format: briefing-doc | study-guide | blog-post | custom | For download: json | markdown | html"
                },
                "orientation": {
                    "type": "STRING",
                    "description": "Infographic orientation: landscape | portrait | square"
                },
                "detail": {
                    "type": "STRING",
                    "description": "Infographic detail level: low | medium | high"
                },
                "kind": {
                    "type": "STRING",
                    "description": "Mind map kind: interactive | note-backed"
                },
                "artifact_type": {
                    "type": "STRING",
                    "description": "Download type: audio | video | quiz | flashcards | slide-deck | infographic | report | mind-map | data-table"
                },
                "output_path": {
                    "type": "STRING",
                    "description": "File path to save the downloaded artifact"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_mute",
        "description": (
            "Mutes or unmutes the microphone. "
            "Call this when the user tells you to mute or unmute yourself "
            "(e.g. 'Jarvis mute yourself', 'Jarvis unmute', 'shut up', 'listen')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "muted": {
                    "type": "BOOLEAN",
                    "description": "True to mute the microphone, False to unmute and listen"
                }
            },
            "required": ["muted"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "NOTE: This tool does NOT convert documents (docx/txt) to PDF. "
        "For document-to-PDF conversion, creating PDFs, or generating any professional documents, "
        "use the 'doc_creator' tool instead (especially if the user mentions 'doc_creator' explicitly). "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "doc_creator",
        "description": (
            "Creates professional documents, presentations, spreadsheets, PDFs, posters, infographics, and logos. "
            "ALSO converts existing uploaded files (like .docx, .txt, .md) into PDF format. "
            "Supports: pptx (presentations), xlsx (spreadsheets), "
            "docx (Word documents), pdf (PDF from uploaded file or from scratch), "
            "poster (high-res images), infographic (data visualizations), "
            "logo (branded logos). Can use an image/file reference via image_path. "
            "Use this tool when the user explicitly asks for 'doc_creator', 'document creator', "
            "wants to convert a file to PDF, or create any document from scratch."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":    {"type": "STRING",  "description": "Describe what to create or convert (e.g. 'Convert this docx to PDF', 'Create a presentation about climate change')"},
                "doc_type":  {"type": "STRING",  "description": "pptx | xlsx | docx | pdf | poster | infographic | logo (optional, auto-detected from prompt)"},
                "image_path": {"type": "STRING", "description": "Path to an uploaded file to convert to PDF, or a reference image to include in the document"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class _GoAwayReceived(Exception):
    """Raised when the server signals a graceful session rotation."""


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

        # ─── Tool-response gate ─────────────────────────────────────────
        # During a tool call the server expects ONLY a tool_response.
        # Any other message (audio, client_content, realtime_input) sent
        # during that window triggers 1007 WEBSOCKET CLOSE.
        self._tool_response_pending = False
        self._tool_gate_lock = threading.Lock()
        self._pending_speak: list[str] = []     # queued speak() text
        self._pending_text: list[str] = []       # queued _on_text_command text

        # ─── Session resumption (graceful GoAway handling) ───────────
        self._session_handle: str | None = None

        # ─── Mem0AI Semantic Memory ─────────────────────────────────────
        self.mem0 = Mem0Memory()

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        # Queue text during tool-response window to avoid 1007
        with self._tool_gate_lock:
            if self._tool_response_pending:
                self._pending_text.append(text)
                return
        asyncio.run_coroutine_threadsafe(
            self.session.send_realtime_input(text=text),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        # Queue speech during tool-response window to avoid 1007
        with self._tool_gate_lock:
            if self._tool_response_pending:
                self._pending_speak.append(text)
                return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _store_mem0_turn(self, user_text: str, assistant_text: str):
        """Store a conversation turn in Mem0 semantic memory (runs in thread)."""
        threading.Thread(
            target=self.mem0.store_conversation,
            args=(user_text, assistant_text),
            daemon=True
        ).start()

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]

        # ─── Retrieve Mem0AI semantic memories (V2: multi-query for completeness) ──
        if self.mem0.enabled:
            try:
                # Query with multiple angles to catch more semantic matches
                queries = [
                    "user preferences, identity, projects, and personal information",
                    "user name, location, profession, skills, and interests",
                    "user family, friends, relationships, and daily life",
                    "user goals, wishes, future plans, and things to buy",
                    "the user's personal details and stored facts about them",
                ]
                all_mems: list[str] = []
                seen = set()
                for q in queries:
                    batch = self.mem0.get_relevant_memories(query=q)
                    for m in batch:
                        key = m.lower().strip()
                        if key not in seen:
                            seen.add(key)
                            all_mems.append(m)

                mem0_str = self.mem0.format_memories_for_prompt(all_mems)
                if mem0_str:
                    parts.append(mem0_str)
                    print(f"[Mem0] 📋 Injected {len(all_mems)} memory items into context")
            except Exception as e:
                print(f"[Mem0] ⚠️ Retrieval error in _build_config: {e}")

        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(handle=self._session_handle),

            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        # --- HITL SECURITY CHECK (Open-Source Roadmap) ---
        high_risk_tools = ["shutdown_jarvis", "file_controller", "computer_settings"]
        is_high_risk = False
        
        if name == "file_controller" and args.get("action") == "delete":
            is_high_risk = True
        elif name == "computer_settings" and args.get("action") in ["shutdown", "restart"]:
            is_high_risk = True
        elif name == "shutdown_jarvis":
            is_high_risk = True

        if is_high_risk:
            self.ui.write_log(f"⚠️ SECURITY: Confirm {name}?")
            # ponytail: Use the UI's existing wait_for_api_key logic or similar for confirmation
            # For simplicity in this CLI-focused UI, we will use a blocking call to a confirm method if available
            if hasattr(self.ui, "confirm_action"):
                confirmed = await asyncio.to_thread(self.ui.confirm_action, name, args)
                if not confirmed:
                    return types.FunctionResponse(id=fc.id, name=name, response={"result": "Action cancelled by user for security."})
        # ------------------------------------------------

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "save_memory":
                category = args.get("category", "notes")
                key      = args.get("key", "")
                value    = args.get("value", "")
                if key and value:
                    await loop.run_in_executor(
                        None,
                        lambda: self.mem0.store_fact(category, key, value)
                    )
                
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": "ok", "silent": True}
                )

            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message task attempted for {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(
                    None, 
                    lambda: youtube_video(parameters=args, response=None, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "screen_process":
                r = await loop.run_in_executor(
                    None,
                    lambda: screen_process(
                        parameters=args, response=None,
                        player=self.ui, session_memory=None,
                        speak=self.speak
                    )
                )
                result = r or "Vision analysis complete."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "gesture_control":
                r = await loop.run_in_executor(None, lambda: gesture_control(parameters=args, player=self.ui))
                result = r or "Done."



            elif name == "content_studio":
                if not args.get("image_path") and self.ui.current_file:
                    args["image_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None, 
                    lambda: content_studio(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Content generation started."

            elif name == "frontend_builder":
                r = await loop.run_in_executor(
                    None,
                    lambda: frontend_builder(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Frontend development complete."

            elif name == "prompt_optimizer":
                r = await loop.run_in_executor(
                    None,
                    lambda: prompt_optimizer(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Prompt optimized."

            elif name == "apk_builder":
                r = await loop.run_in_executor(
                    None,
                    lambda: apk_builder(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "APK build process complete."

            elif name == "extension_builder":
                r = await loop.run_in_executor(
                    None,
                    lambda: extension_builder(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Extension built successfully."

            elif name == "mobile_control":
                r = await loop.run_in_executor(
                    None,
                    lambda: mobile_control(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "video_editing":
                r = await loop.run_in_executor(
                    None,
                    lambda: video_editing(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Video editing task complete."

            elif name == "composio_task":
                r = await loop.run_in_executor(
                    None,
                    lambda: JarvisToolManager().execute_task(args.get("task", ""))
                )
                result = r or "Cloud task executed."

            elif name == "generate_image":
                prompt = args.get("prompt", "")
                aspect_ratio = args.get("aspect_ratio", "1:1")
                engine = JarvisImageEngine()
                r = await loop.run_in_executor(
                    None,
                    lambda: engine.generate(prompt=prompt, aspect_ratio=aspect_ratio)
                )
                result = r or "Image generated."

            elif name == "doc_creator":
                if not args.get("image_path") and self.ui.current_file:
                    args["image_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: doc_creator(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Document creation process finished."

            elif name == "handle_call":
                if handle_call_action:
                    r = await loop.run_in_executor(
                        None, 
                        lambda: handle_call_action({"app": args.get("app")}, args.get("action", "accept"))
                    )
                    result = r or "Action attempted."
                else:
                    result = "Attention monitor not active."

            elif name == "meeting_analyzer":
                if MeetingAssistant:
                    action = args.get("action", "start")
                    if action == "start":
                        self.meeting_assistant = MeetingAssistant(self.ui, self.speak)
                        self.meeting_assistant.start(args.get("title", "Meeting"), args.get("context", ""))
                        result = "Meeting analysis started."
                    else:
                        if hasattr(self, 'meeting_assistant'):
                            self.meeting_assistant.stop()
                            result = "Meeting analysis stopped."
                        else:
                            result = "No active meeting analysis to stop."
                else:
                    result = "Meeting analyzer module not loaded."

            elif name == "notebooklm":
                r = await loop.run_in_executor(
                    None,
                    lambda: notebooklm_controller(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "ui_automation":
                r = await loop.run_in_executor(
                    None,
                    lambda: ui_automation(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "set_mute":
                muted = args.get("muted", True)
                self.ui.set_mute(muted)
                result = "Microphone muted." if muted else "Microphone active."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()
                return types.FunctionResponse(id=fc.id, name=name, response={"result": "ok"})

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()

        finally:
            self.set_speaking(False)
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            # Poll with timeout instead of blocking get() so we can
            # skip audio chunks during tool-response windows
            try:
                msg = await asyncio.wait_for(
                    self.out_queue.get(),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                continue

            # Skip sending audio during tool-response window to avoid 1007
            with self._tool_gate_lock:
                if self._tool_response_pending:
                    continue  # drop this chunk (safe to lose)
            await self.session.send_realtime_input(
                audio=types.Blob(data=msg["data"], mime_type="audio/pcm")
            )

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                # Skip queuing audio during tool-response window to avoid QueueFull
                with self._tool_gate_lock:
                    if self._tool_response_pending:
                        return
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    # ─── Graceful session rotation ───────────────────────────
                    # Server sends go_away ~60s before terminating the session
                    if response.go_away:
                        print("[JARVIS] 🔄 Server GoAway — rotating session gracefully.")
                        raise _GoAwayReceived("GoAway")

                    # Store session resumption handle for seamless reconnect
                    sru = response.session_resumption_update
                    if sru and sru.resumable and sru.new_handle:
                        self._session_handle = sru.new_handle

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            # ─── Store conversation turn in Mem0 ──────
                            if full_in and self.mem0.enabled:
                                self._store_mem0_turn(full_in, full_out)

                    if response.tool_call:
                        # GATE OPEN: Prevent audio/speak/text during tool execution
                        with self._tool_gate_lock:
                            self._tool_response_pending = True

                        try:
                            fn_responses = []
                            for fc in response.tool_call.function_calls:
                                print(f"[JARVIS] 📞 {fc.name}")
                                fr = await self._execute_tool(fc)
                                fn_responses.append(fr)
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                        finally:
                            # GATE CLOSED: Always clear flag, even on exception
                            with self._tool_gate_lock:
                                self._tool_response_pending = False
                                pending_speak = list(self._pending_speak)
                                pending_text = list(self._pending_text)
                                self._pending_speak.clear()
                                self._pending_text.clear()

                        # Deliver queued speech via send_client_content
                        for text in pending_speak:
                            asyncio.run_coroutine_threadsafe(
                                self.session.send_client_content(
                                    turns={"parts": [{"text": text}]},
                                    turn_complete=True
                                ),
                                self._loop
                            )
                        # Deliver queued text commands via send_realtime_input
                        for text in pending_text:
                            asyncio.run_coroutine_threadsafe(
                                self.session.send_realtime_input(text=text),
                                self._loop
                            )
        except Exception as e:
            estr = str(e)
            # Suppress traceback for known session rotation signals (run() handles the message)
            if not _WS_CLOSE_RE.search(estr) and "GoAway" not in estr:
                print(f"[JARVIS] ❌ Recv: {e}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")
                    self.ui.write_log("HINT: Enable 'Install via USB' in Android Developer Options for full control.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except (errors.APIError, ExceptionGroup) as e:
                # ExceptionGroup's str() doesn't show nested errors, so check inner exceptions
                if isinstance(e, ExceptionGroup):
                    is_ws_close = any(_WS_CLOSE_RE.search(str(ex)) for ex in e.exceptions)
                else:
                    is_ws_close = bool(_WS_CLOSE_RE.search(str(e)))

                if is_ws_close or "GoAway" in str(e):
                    print("[JARVIS] 🔄 Session rotated gracefully.")
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()
            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()

        # Reset tool-response gate for clean reconnect
        with self._tool_gate_lock:
            self._tool_response_pending = False
            self._pending_speak.clear()
            self._pending_text.clear()

        # Mem0 keeps its state across reconnects (persisted to disk)

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
