#youtube_video.py
import os
import json
import re
import sys
import time
import subprocess
import shutil
import cv2
import tempfile
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

import pyautogui
import numpy as np
import yt_dlp
from google import genai
from google.genai import types as gtypes

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

from config import get_os, is_windows, is_mac, is_linux


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] ⚠️ open_url failed: {e}")

def _scrape_first_video_url(query: str) -> str | None:

    if not _REQUESTS_OK:
        return None

    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )

    try:
        r    = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text

        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)

        seen = set()
        for vid in video_ids:
            if vid in seen:
                continue
            seen.add(vid)

            if f'/shorts/{vid}' in html:
                continue
            return f"https://www.youtube.com/watch?v={vid}"

    except Exception as e:
        print(f"[YouTube] ⚠️ scrape_first_video_url failed: {e}")

    return None

def _extract_video_id(url: str) -> str | None:
    match = re.search(
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url
    )
    return match.group(1) if match else None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _ask_for_url(prompt_text: str = "YouTube video URL:") -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring("J.A.R.V.I.S", prompt_text, parent=root)
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL dialog failed: {e}")
        return None


def _get_transcript(video_id: str) -> str | None:
    if not _TRANSCRIPT_OK:
        return None
    try:
        # User's version requires instantiating the class
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        transcript      = None

        lang_priority = ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]

        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return None

        fetched = transcript.fetch()
        parts = []
        for entry in fetched:
            if isinstance(entry, dict):
                parts.append(entry.get("text", ""))
            else:
                parts.append(getattr(entry, "text", ""))
        return " ".join(parts).strip()

    except Exception as e:
        print(f"[YouTube] ⚠️ Transcript fetch failed: {e}")
        return None


def _summarize_with_gemini(transcript: str, video_url: str) -> str:
    from config.genai_client import generate_content

    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    
    response = generate_content(
        model="gemini-2.5-flash",
        contents=f"Please summarize this YouTube video transcript:\n\n{truncated}",
        config={"system_instruction": (
            "You are JARVIS, an AI assistant. "
            "Summarize YouTube video transcripts clearly and concisely. "
            "Structure: 1-sentence overview, then 3-5 key points. "
            "Be direct. Address the user as 'sir'. "
            "Match the language of the transcript."
        )}
    )
    return response


def _save_summary(content: str, video_url: str) -> str:
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop  = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    header = (
        f"JARVIS — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] ⚠️ Could not open text editor: {e}")

    return str(filepath)


def _scrape_video_info(video_id: str) -> dict:
    if not _REQUESTS_OK:
        return {}
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        info = {}

        for key, pattern in [
            ("title",    r'"title":\{"runs":\[\{"text":"([^"]+)"'),
            ("channel",  r'"ownerChannelName":"([^"]+)"'),
            ("views",    r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes",    r'"label":"([0-9,]+ likes)"'),
        ]:
            match = re.search(pattern, html)
            if match:
                raw = match.group(1)
                if key == "views":
                    info[key] = f"{int(raw):,}"
                elif key == "duration":
                    secs = int(raw)
                    info[key] = f"{secs // 60}:{secs % 60:02d}"
                else:
                    info[key] = raw

        return info
    except Exception as e:
        print(f"[YouTube] ⚠️ Info scrape failed: {e}")
        return {}


def _scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict]:
    if not _REQUESTS_OK:
        return []
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text

        titles   = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            results.append({"rank": len(results) + 1, "title": title, "channel": channel})
            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"[YouTube] ⚠️ Trending scrape failed: {e}")
        return []

def _handle_play(parameters: dict, player) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Please tell me what you'd like to watch, sir."

    if player:
        player.write_log(f"[YouTube] Searching: {query}")

    video_url = _scrape_first_video_url(query)

    if video_url:
        _open_url(video_url)
        return f"Playing: {query}"

    fallback_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    _open_url(fallback_url)
    return f"Opened YouTube search for: {query} (manual selection required)"


def _handle_summarize(parameters: dict, player) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"

    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
        
    if not url:
        return "No URL provided, sir. Summary cancelled."
    if not _is_valid_youtube_url(url):
        return "That doesn't appear to be a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID from that URL, sir."

    if player:
        player.write_log(f"[YouTube] Fetching transcript: {url}")

    transcript_text = _get_transcript(video_id)
    if not transcript_text:
        return "I couldn't retrieve a transcript for that video, sir."

    if player:
        player.write_log("[YouTube] Generating summary...")

    try:
        summary = _summarize_with_gemini(transcript_text, url)
    except Exception as e:
        return f"Summary generation failed, sir: {e}"

    if parameters.get("save", False):
        saved_path = _save_summary(summary, url)
        return f"{summary}\n\n[FILE SAVED: {saved_path}]"

    return summary


def _handle_get_info(parameters: dict, player) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
        
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID, sir."

    if player:
        player.write_log(f"[YouTube] Getting info: {url}")

    info = _scrape_video_info(video_id)
    if not info:
        return "Could not retrieve video information, sir."

    lines = [
        f"{key.capitalize()}: {info[key]}"
        for key in ("title", "channel", "views", "duration", "likes")
        if key in info
    ]
    return "\n".join(lines)


def _handle_trending(parameters: dict, player) -> str:
    region = parameters.get("region", "TR").upper()

    if player:
        player.write_log(f"[YouTube] Trending: {region}")

    trending = _scrape_trending(region=region, max_results=8)
    if not trending:
        return f"Could not fetch trending videos for region {region}, sir."

    lines  = [f"Top trending videos in {region}:"]
    lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
    return "\n".join(lines)

def _timestamp_to_seconds(ts: str) -> float:
    """Converts MM:SS or HH:MM:SS to seconds."""
    if not ts: return 0.0
    parts = str(ts).split(':')
    try:
        if len(parts) == 2: # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3: # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return float(ts)
    except Exception:
        return 0.0

def _download_video_stream(url: str, output_dir: str) -> str:
    """Downloads a version of the video using yt-dlp with flexible format selection."""
    ydl_opts = {
        # Try to find a balanced low-res format, but fall back to 'best' if needed
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]/best',
        'outtmpl': os.path.join(output_dir, 'video.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        # Add a common user agent to help with platform-specific checks
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def _extract_frame(video_path: str, seconds: float) -> bytes:
    """Extracts a frame at a specific second and returns as JPEG bytes."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Could not extract frame at {seconds}s")
    _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return buffer.tobytes()

def _handle_analyze(parameters: dict, player) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the video URL (YouTube, Insta, etc.):")
    if not url:
        return "No URL provided, sir."

    query = parameters.get("query", "What is happening in this video?").strip()
    timestamp = parameters.get("timestamp")

    temp_dir = tempfile.mkdtemp()
    try:
        if player: player.write_log(f"[Video] Downloading: {url}")
        video_path = _download_video_stream(url, temp_dir)
        
        frames_to_send = []
        if timestamp:
            seconds = _timestamp_to_seconds(str(timestamp))
            if player: player.write_log(f"[Video] Extracting frame at {timestamp}...")
            frames_to_send.append(_extract_frame(video_path, seconds))
            prompt_context = f"This is a frame from the video at {timestamp}."
        else:
            cap = cv2.VideoCapture(video_path)
            total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / (fps or 30)
            cap.release()
            
            if player: player.write_log("[Video] Analyzing key moments...")
            times = [1.0, duration / 2, max(1.0, duration - 1.0)]
            for t in times:
                try: frames_to_send.append(_extract_frame(video_path, t))
                except: continue
            prompt_context = "These are sequential frames from the video (Start, Middle, End)."

        if player: player.write_log("[Video] Reasoning with Gemini 2.5 Flash...")
        client = genai.Client(api_key=_get_api_key())
        
        contents = []
        for fb in frames_to_send:
            contents.append(gtypes.Part.from_bytes(data=fb, mime_type="image/jpeg"))
        contents.append(f"{prompt_context}\n\nQuestion: {query}")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=gtypes.GenerateContentConfig(
                system_instruction="You are JARVIS, an expert video analyst. Analyze the frames to answer accurately. Address user as 'sir'.",
                temperature=0.2
            )
        )
        
        result = response.text.strip()
        return result

    except Exception as e:
        err = f"Video analysis failed: {e}"
        if player: player.write_log(f"Error: {err}")
        return err
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

_ACTION_MAP = {
    "play":      _handle_play,
    "summarize": _handle_summarize,
    "get_info":  _handle_get_info,
    "trending":  _handle_trending,
    "analyze":   _handle_analyze,
}


def youtube_video(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[YouTube] Action: {action}")
    print(f"[YouTube] ▶️  Action: {action}  Params: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        return (
            f"Unknown YouTube action: '{action}'. "
            "Available: play, summarize, get_info, trending, analyze."
        )

    try:
        if action == "play":
            return handler(params, player) or "Done."
        # Note: We NO LONGER pass 'speak' to handlers to prevent recursive feedback loops.
        # The main JARVIS brain will handle speaking the final result returned here.
        return handler(params, player) or "Done."
    except Exception as e:
        print(f"[YouTube] ❌ Error in {action}: {e}")
        return f"YouTube {action} failed, sir: {e}"
