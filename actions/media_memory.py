"""
media_memory.py — Save image, audio, and video descriptions to long-term memory.

Flow:
  1. User provides a file path (image, audio, or video)
  2. Upload the file via Gemini Files API
  3. Ask Gemini to describe/analyze the content
  4. Store the description as a text fact in mem0 memory
  5. Copy the file to memory/media_memories/ for future reference
  6. Return the description

Usage from JARVIS:
  "Jarvis, I uploaded a photo — save this in memory"
  → calls save_media_memory(file_path="C:/Users/.../photo.jpg")

  "Jarvis, save this audio recording to memory"
  → calls save_media_memory(file_path="C:/Users/.../recording.mp3")
"""

import json
import shutil
import time
from pathlib import Path


# ── Supported media types ─────────────────────────────────────────────────────

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tiff", "ico", "svg"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "aac", "flac", "wma", "opus"}
VIDEO_EXTS = {"mp4", "avi", "mov", "mkv", "wmv", "flv", "webm", "m4v", "3gp"}

# MIME type helpers
_MIME_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "bmp": "image/bmp", "gif": "image/gif",
    "tiff": "image/tiff", "svg": "image/svg+xml", "ico": "image/x-icon",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "m4a": "audio/mp4", "aac": "audio/aac", "flac": "audio/flac",
    "wma": "audio/x-ms-wma", "opus": "audio/opus",
    "mp4": "video/mp4", "avi": "video/x-msvideo", "mov": "video/quicktime",
    "mkv": "video/x-matroska", "wmv": "video/x-ms-wmv", "flv": "video/x-flv",
    "webm": "video/webm", "m4v": "video/x-m4v", "3gp": "video/3gpp",
}

# ── File helpers ──────────────────────────────────────────────────────────────


def _detect_media_type(path: Path) -> str | None:
    """Return 'image', 'audio', 'video', or None if unsupported."""
    ext = path.suffix.lower().lstrip(".")
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def _mime_for(path: Path) -> str:
    """Return MIME type for the file, defaulting to octet-stream."""
    ext = path.suffix.lower().lstrip(".")
    return _MIME_MAP.get(ext, "application/octet-stream")


def _file_size_str(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    if size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    return f"{size / 1024 ** 3:.2f} GB"


# ── Gemini client helper ──────────────────────────────────────────────────────


def _get_client():
    """Get the shared Gemini client from config."""
    from config.genai_client import get_client
    return get_client()


# ── Prompt builder ────────────────────────────────────────────────────────────


def _build_analysis_prompt(media_type: str, user_hint: str = "") -> str:
    """Build the right prompt for the media type."""
    hint = f"\nThe user also said: {user_hint}" if user_hint else ""

    if media_type == "image":
        return (
            "Analyze this image in detail. Describe:\n"
            "- The main subject(s) and objects visible\n"
            "- People, expressions, actions (if any)\n"
            "- Colors, lighting, composition, style\n"
            "- Any text visible in the image\n"
            "- The overall scene and context\n"
            "- Notable details or interesting elements"
            f"{hint}"
        )
    elif media_type == "audio":
        return (
            "Analyze this audio in detail. Describe:\n"
            "- If speech: transcribe what is said and who is speaking\n"
            "- If music: describe the genre, instruments, mood, tempo\n"
            "- Any notable sounds, background noise, or effects\n"
            "- The overall context and purpose of this audio"
            f"{hint}"
        )
    else:  # video
        return (
            "Analyze this video in detail. Describe:\n"
            "- The scene(s) and setting\n"
            "- People, actions, interactions (if any)\n"
            "- Key objects and visual elements\n"
            "- If audio track present: what is said or what music plays\n"
            "- The overall narrative, context, and purpose"
            f"{hint}"
        )


# ── Core logic ────────────────────────────────────────────────────────────────


def _save_media_memory(file_path: str, user_description: str = "",
                       category: str = "media_memory") -> str:
    """
    Analyze a media file, save its description to memory, and copy the file.

    Returns a human-readable result string.
    """
    path = Path(file_path)

    # ── 1. Validate file ──────────────────────────────────────────────
    if not path.exists():
        return f"File not found: {file_path}"
    if not path.is_file():
        return f"Not a file: {file_path}"

    media_type = _detect_media_type(path)
    if not media_type:
        return (
            f"Unsupported file type: {path.suffix}. "
            f"Supported: images ({', '.join(sorted(IMAGE_EXTS))}), "
            f"audio ({', '.join(sorted(AUDIO_EXTS))}), "
            f"video ({', '.join(sorted(VIDEO_EXTS))})"
        )

    size_str = _file_size_str(path)
    file_info = f"[{media_type.upper()}] {path.name} ({size_str})"
    print(f"[MediaMemory] Analyzing {file_info}")

    # ── 2. Upload to Gemini File API ──────────────────────────────────
    try:
        client = _get_client()
        uploaded = client.files.upload(file=str(path))
        # Wait briefly if processing is needed
        retries = 0
        while uploaded.state.name == "PROCESSING" and retries < 10:
            time.sleep(1)
            uploaded = client.files.get(name=uploaded.name)
            retries += 1
        if uploaded.state.name == "FAILED":
            return f"Gemini file processing failed: {uploaded.name}"
    except Exception as e:
        return f"File upload to Gemini failed: {e}"

    # ── 3. Ask Gemini to describe the content ─────────────────────────
    try:
        prompt = _build_analysis_prompt(media_type, user_description)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, uploaded],
        )
        description = response.text.strip()
    except Exception as e:
        # Clean up the uploaded file on error
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass
        return f"AI analysis failed: {e}"

    # Clean up the uploaded file from Gemini servers (it auto-deletes in 48h anyway)
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass

    if not description:
        return "AI returned an empty description."

    # ── 4. Copy file to memory/media_memories/ for future reference ───
    memories_dir = Path(__file__).resolve().parent.parent / "memory" / "media_memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Add a timestamp prefix to avoid name collisions
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{path.name}"
    dest_path = memories_dir / dest_name

    try:
        shutil.copy2(str(path), str(dest_path))
    except Exception as e:
        dest_path = None  # file copy failed, still save the text description
        print(f"[MediaMemory] ⚠️ File copy failed: {e}")

    # ── 5. Store the description as a text fact in memory ─────────────
    fact_key = f"{media_type}_memory_{timestamp}"
    fact_value = description

    if dest_path:
        fact_value += f"\n[File: {dest_path}]"

    try:
        from memory.mem0_memory import _FACTS_PATH, _read_json, _atomic_write_json
        # Append directly to the backup file (same thread-safe approach as store_fact)
        fact_record = {
            "category": category,
            "key": fact_key,
            "value": fact_value,
            "media_type": media_type,
            "source_file": str(path),
            "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        existing = _read_json(_FACTS_PATH)
        existing.append(fact_record)
        _atomic_write_json(_FACTS_PATH, existing)
        print(f"[MediaMemory] 💾 Saved {media_type} memory: {fact_key}")
    except Exception as e:
        return f"Description was generated but could not save to memory: {e}"

    # ── 6. Return summary ─────────────────────────────────────────────
    preview = description[:300] + "..." if len(description) > 300 else description
    lines = [
        f"✅ Saved {media_type.upper()} to memory:",
        f"   File: {path.name} ({size_str})",
        f"   Description: {preview}",
    ]
    if dest_path:
        lines.append(f"   Archived to: {dest_path}")
    return "\n".join(lines)


# ── Entry point for JARVIS tool routing ───────────────────────────────────────


def save_media_memory(parameters: dict, player=None, speak=None) -> str:
    """
    JARVIS tool entry point.

    Parameters:
        file_path (str, required): Full path to the media file
        description (str, optional): Brief user-provided description / hint
        category (str, optional): Memory category (default: media_memory)
    """
    file_path = (parameters.get("file_path") or "").strip()
    if not file_path:
        return "No file path provided. Usage: file_path=C:/path/to/media.jpg"

    user_desc = (parameters.get("description") or "").strip()
    category = (parameters.get("category") or "media_memory").strip()

    return _save_media_memory(
        file_path=file_path,
        user_description=user_desc,
        category=category,
    )
