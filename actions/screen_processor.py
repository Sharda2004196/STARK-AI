from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    from PIL import ImageEnhance
    _PIL = True
except ImportError:
    _PIL = False

from google import genai
from google.genai import types as gtypes

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config.")
    return key

def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()

# Using 2.5 Flash for state-of-the-art high-precision snapshot reasoning
_ANALYSIS_MODEL = "gemini-3.1-flash-lite"
_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q    = 95

_SYSTEM_PROMPT = (
    "You are JARVIS, Tony Stark's advanced AI. "
    "You are analyzing a high-resolution snapshot from the user's camera or screen. "
    "MANDATORY: Describe only what is VISIBLY present. If you see a bottle, do not say it is an electronic device. "
    "Identify materials (plastic, metal, glass) and shapes first. "
    "If the image is too blurry to identify, say so. Do NOT guess."
)

def _compress(img_bytes: bytes) -> bytes:
    if not _PIL: return img_bytes
    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img = ImageEnhance.Sharpness(img).enhance(1.4)
        img = ImageEnhance.Contrast(img).enhance(1.1)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=True)
        return buf.getvalue()
    except Exception:
        return img_bytes

def _capture_screen() -> bytes:
    if not _MSS: raise RuntimeError("mss not installed")
    with mss.mss() as sct:
        monitors = sct.monitors
        target = monitors[1] if len(monitors) > 1 else monitors[0]
        shot = sct.grab(target)
        png = mss.tools.to_png(shot.rgb, shot.size)
    return _compress(png)

def _capture_camera() -> bytes:
    if not _CV2: raise RuntimeError("cv2 not installed")
    cfg = _load_config()
    index = int(cfg.get("camera_index", 0))
    backend = cv2.CAP_DSHOW if _get_os() == "windows" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Camera {index} failed")
    for _ in range(30): cap.read() # Warmup
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None: raise RuntimeError("No camera frame")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = PIL.Image.fromarray(rgb)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    return _compress(img_bytes.getvalue())

def screen_process(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    set_speaking_cb: Optional[Callable[[bool], None]] = None,
    speak: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    SIMPLE HIGH-PRECISION VERSION:
    Captures a high-quality snapshot and uses standard Gemini reasoning.
    """
    user_text = (parameters.get("text") or parameters.get("user_text") or "What do you see?").strip()
    angle = parameters.get("angle", "screen").lower().strip()

    try:
        # 1. Capture based on angle
        if player: player.write_log(f"Vision: Capturing {angle} snapshot...")
        if angle == "camera":
            img_data = _capture_camera()
        else:
            img_data = _capture_screen()

        # 2. Analyze using standard High-Reasoning API
        if player: player.write_log("Vision: Analyzing with high precision...")
        client = genai.Client(api_key=_get_api_key())
        
        response = client.models.generate_content(
            model=_ANALYSIS_MODEL,
            contents=[
                gtypes.Part.from_bytes(data=img_data, mime_type="image/jpeg"),
                user_text
            ],
            config=gtypes.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.2
            )
        )

        analysis = response.text.strip()
        
        # 3. Log the full analysis (visible in terminal/logs)
        if player: 
            player.write_log(f"Jarvis: {analysis}")
        print(f"[Vision] Result: {analysis}")
        
        # 4. Extract a brief spoken summary (first sentence, capped for speech)
        brief = analysis.split('.')[0].strip()
        if len(brief) < 10:  # if first sentence is too short, take more
            brief = analysis[:200].rsplit('.', 1)[0].strip()
        # Truncate at word boundary only if we exceed 150 chars
        if len(brief) > 150:
            brief = brief[:150].rsplit(' ', 1)[0]
        
        # Return only the brief summary for Gemini to speak
        return brief

    except Exception as e:
        err = f"Vision analysis failed: {str(e)}"
        if player: player.write_log(f"ERR: {err}")
        return err

def warmup_session(player=None) -> None:
    pass # No websocket session to warmup in this simple version
