from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from typing import Callable

import mss
import mss.tools
import sounddevice as sd
from google import genai
from google.genai import types

try:
    import PIL.Image
    _PIL_OK = True
except Exception:
    PIL = None
    _PIL_OK = False


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
IMG_MAX_W = 1280
IMG_MAX_H = 720
JPEG_Q = 72
AUD_SAMPLE_RATE = 16000
ANALYSIS_INTERVAL = 5.0


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        keys = json.load(f)
    key = keys.get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found")
    return key


def _capture_screen() -> bytes:
    """Capture the primary monitor as a JPEG byte string (1280x720 max)."""
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)
    if not _PIL_OK:
        return png_bytes
    img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
    img.thumbnail([IMG_MAX_W, IMG_MAX_H], PIL.Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_Q, optimize=False)
    return buf.getvalue()


def _audio_input_source() -> dict:
    """Find the best system audio loopback device (Stereo Mix / WASAPI)."""
    try:
        devices = sd.query_devices()
    except Exception:
        devices = []

    for idx, dev in enumerate(devices):
        name = (dev.get("name") or "").lower()
        max_in = int(dev.get("max_input_channels") or 0)
        if ("stereo mix" in name or "what u hear" in name or "what you hear" in name) and max_in > 0:
            return {
                "device": idx,
                "channels": min(2, max_in),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": False,
                "label": dev.get("name") or f"Device {idx}",
            }

    try:
        hostapis = sd.query_hostapis()
        for api_idx, api in enumerate(hostapis):
            if "wasapi" not in (api.get("name") or "").lower():
                continue
            out_dev = api.get("default_output_device")
            if out_dev is None or out_dev < 0:
                continue
            dev = devices[out_dev]
            return {
                "device": out_dev,
                "channels": max(1, min(2, int(dev.get("max_output_channels") or 2))),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": True,
                "label": dev.get("name") or f"WASAPI device {out_dev}",
            }
    except Exception:
        pass

    try:
        default_output = sd.default.device[1]
        if isinstance(default_output, int) and default_output >= 0:
            dev = devices[default_output]
            return {
                "device": default_output,
                "channels": max(1, min(2, int(dev.get("max_output_channels") or 2))),
                "samplerate": int(dev.get("default_samplerate") or AUD_SAMPLE_RATE),
                "loopback": True,
                "label": dev.get("name") or f"Default output {default_output}",
            }
    except Exception:
        pass

    return {}


def _clean_response(text: str) -> tuple[str, str]:
    """Parse the model's response into (summary, answer).
    Accumulates ALL lines between section labels into each field,
    so multi-line visual descriptions are preserved in full."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "", ""
    summary = ""
    answer = ""
    current_section: str | None = None

    LABELS = {
        "summary:", "meeting:", "topic:",
        "answer:", "response:", "reply:",
    }

    for ln in lines:
        low = ln.lower()
        # Detect a section label
        matched_label: str | None = None
        for label in LABELS:
            if low.startswith(label):
                matched_label = label
                break

        if matched_label:
            # Determine which field this label belongs to
            if matched_label in ("summary:", "meeting:", "topic:"):
                current_section = "summary"
            else:
                current_section = "answer"
            content = ln.split(":", 1)[-1].strip()
            if content:
                if current_section == "summary":
                    summary = content
                else:
                    answer = content
        elif current_section == "summary":
            summary += " " + ln if summary else ln
        elif current_section == "answer":
            answer += " " + ln if answer else ln

    if not summary:
        summary = lines[0]
    if not answer and len(lines) > 1:
        answer = lines[1]
    return summary, answer


class MeetingAssistant:
    """Meeting monitor using Gemini REST API (generate_content).

    Avoids the Live API (WebSocket) to prevent dual-session conflicts
    with JARVIS's main voice session. Captures screen and system audio
    via threads, then sends them to Gemini 3.1 Flash Lite via REST API
    for high-frequency background analysis.
    """

    def __init__(
        self,
        on_update: Callable[[dict], None] | None = None,
        on_state: Callable[[str], None] | None = None,
        client: genai.Client | None = None,
    ):
        self._on_update = on_update
        self._on_state = on_state
        self._running = False
        self._stop_event = threading.Event()
        self._title = "Meeting mode"
        self._context = ""
        self._last_answer = ""



        # Audio capture state (thread-based)
        self._audio_buf = bytearray()
        self._audio_lock = threading.Lock()
        self._audio_source: dict = {}
        self._audio_samplerate = AUD_SAMPLE_RATE
        self._audio_channels = 1
        self._audio_thread: threading.Thread | None = None

        # Analysis thread
        self._analysis_thread: threading.Thread | None = None

        # Transcriber client — reuse shared client from JarvisLive if provided,
        # otherwise create one on start. Sharing avoids creating a second
        # genai.Client (and its underlying HTTPX connection pool) which could
        # interfere with the Live API WebSocket session.
        self._transcriber_client = client

    # ── Public API ──────────────────────────────────────────────────────

    def start(self, *, title: str = "Meeting mode", context: str = "") -> None:
        self._title = title or "Meeting mode"
        self._context = context or ""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        # Initialize transcriber client (only create if not shared from JarvisLive)
        if self._transcriber_client is None:
            try:
                self._transcriber_client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"},
                )
            except Exception as exc:
                self._safe_on_update({
                    "active": False, "title": self._title,
                    "summary": "Meeting mode could not start.",
                    "answer": str(exc)[:200], "status": "error",
                })
                self.stop()
                return

        # Start audio capture thread
        self._audio_source = _audio_input_source() or {}
        if self._audio_source.get("device") is not None:
            self._audio_samplerate = int(self._audio_source.get("samplerate", AUD_SAMPLE_RATE))
            self._audio_channels = int(self._audio_source.get("channels", 1))
            self._audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
            self._audio_thread.start()

        # Start analysis thread
        self._analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self._analysis_thread.start()

        self._safe_on_state("MEETING")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self._safe_on_state("LISTENING")

    def update_context(self, title: str | None = None, context: str | None = None) -> None:
        if title:
            self._title = title
        if context is not None:
            self._context = context

    def latest_speech(self) -> str:
        return self._last_answer

    # ── Analysis loop (runs in a thread) ────────────────────────────────

    def _analysis_loop(self):
        """Thread: polls screen and audio, sends both in ONE Gemini REST API call.
        Runs every ANALYSIS_INTERVAL seconds. Sends image + audio + text prompt
        in a single generate_content call (1 API call per cycle = 12 RPM),
        staying well within the 15 RPM limit of gemini-3.1-flash-lite.
        On API failure: prints error to console but keeps last good state."""
        client = self._transcriber_client
        if not client:
            return

        while self._running and not self._stop_event.is_set():
            try:
                image_bytes = _capture_screen()

                # Grab buffered audio and convert to WAV (synchronized)
                audio_part = None
                with self._audio_lock:
                    if len(self._audio_buf) >= 16000:
                        pcm = bytes(self._audio_buf)
                        self._audio_buf.clear()
                    else:
                        pcm = None
                if pcm:
                    import wave
                    wav_buf = io.BytesIO()
                    with wave.open(wav_buf, "wb") as wf:
                        wf.setnchannels(self._audio_channels)
                        wf.setsampwidth(2)
                        wf.setframerate(self._audio_samplerate)
                        wf.writeframes(pcm)
                    audio_part = types.Part.from_bytes(
                        data=wav_buf.getvalue(), mime_type="audio/wav"
                    )

                # Build contents list — image + optional audio + text prompt
                contents = [
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                ]
                if audio_part:
                    contents.append(audio_part)
                contents.append(
                    "You are a meeting/video monitoring assistant. "
                    "Your job is to analyze BOTH the screen VISUALS and any AUDIO speech.\n\n"
                    "VISUAL ANALYSIS — Look carefully at the screen image and report:\n"
                    "- What application or website is open (YouTube, Zoom, browser, IDE, etc.)\n"
                    "- Read and report ALL visible text: titles, channel names, prices, numbers, labels, URLs, buttons, code, timestamps\n"
                    "- Describe visual elements: UI layout, images, charts, people, products, branding/logos\n"
                    "- If a video is playing, note the video title and channel name\n"
                    "- Report specific numbers, prices, names, or any data visible on screen\n\n"
                    "AUDIO ANALYSIS:\n"
                    "- Transcribe key points from any speech heard in the audio\n"
                    "- Identify the speaker's main topic or argument\n\n"
                    "Provide a COMPREHENSIVE analysis covering specific visual details AND audio content. "
                    "Do NOT summarize briefly — describe what is actually on screen with as much detail as possible. "
                    f"Meeting title: {self._title}\n"
                    f"Context: {self._context}\n\n"
                    "Return in this format:\n"
                    "Summary: [comprehensive description of what is VISUALLY on screen and what is being discussed]\n"
                    "Answer: [any additional details, questions, or observations]"
                )

                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=contents,
                    config={"temperature": 0.2},
                )

                text = self._extract_text(response)
                summary, answer = _clean_response(text)
                self._last_answer = answer or summary

                self._safe_on_update({
                    "active": True,
                    "title": self._title,
                    "summary": summary or "Watching the meeting screen.",
                    "answer": answer or summary or "No question detected.",
                    "speech": "",
                    "status": "live",
                })

            except Exception as exc:
                # Print error to console but do NOT overwrite _meeting_analysis
                print(f"[MeetingAssistant] \u26a0\ufe0f Analysis error: {exc}")

            time.sleep(ANALYSIS_INTERVAL)

    @staticmethod
    def _extract_text(response) -> str:
        parts: list[str] = []
        try:
            for candidate in getattr(response, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", []) or []:
                    txt = getattr(part, "text", None)
                    if txt:
                        parts.append(txt)
        except Exception:
            pass
        if parts:
            return "".join(parts).strip()
        return (getattr(response, "text", "") or "").strip()

    # ── Audio capture thread ────────────────────────────────────────────

    def _audio_capture_loop(self):
        """Daemon thread: captures system audio via sounddevice callback."""
        source = self._audio_source
        device = source.get("device")
        channels = int(source.get("channels", 2))
        samplerate = int(source.get("samplerate", AUD_SAMPLE_RATE))
        loopback = bool(source.get("loopback", False))
        label = source.get("label", "audio source")
        print(f"[MeetingAssistant] \U0001f3a4 Audio source: {label}")

        extra = None
        if loopback:
            try:
                extra = sd.WasapiSettings(loopback=True)
            except Exception:
                extra = None

        def callback(indata, frames, time_info, status):
            if self._stop_event.is_set():
                return
            with self._audio_lock:
                self._audio_buf.extend(indata.tobytes())

        try:
            with sd.InputStream(
                device=device, samplerate=samplerate, channels=channels,
                dtype="int16", blocksize=max(1024, int(samplerate * 0.25)),
                callback=callback, extra_settings=extra,
            ):
                while self._running and not self._stop_event.is_set():
                    time.sleep(0.35)
        except Exception as exc:
            print(f"[MeetingAssistant] Audio loop error: {exc}")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _safe_on_update(self, payload: dict) -> None:
        if self._on_update is None:
            return
        try:
            self._on_update(payload)
        except Exception as exc:
            print(f"[MeetingAssistant] on_update callback error: {exc}")

    def _safe_on_state(self, state: str) -> None:
        if self._on_state is None:
            return
        try:
            self._on_state(state)
        except Exception as exc:
            print(f"[MeetingAssistant] on_state callback error: {exc}")
