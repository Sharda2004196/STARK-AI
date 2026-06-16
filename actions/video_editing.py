# actions/video_editing.py
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Advanced Video Editing with MoviePy and Librosa
try:
    from moviepy import (
        VideoFileClip, AudioFileClip, concatenate_videoclips, 
        TextClip, CompositeVideoClip, ColorClip
    )
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut, MultiplyColor
    _MOVIEPY = True
except ImportError:
    _MOVIEPY = False

try:
    import librosa
    import numpy as np
    _LIBROSA = True
except ImportError:
    _LIBROSA = False

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False


def _get_output_path(input_path: str, suffix: str = "_edited") -> str:
    path = Path(input_path)
    return str(path.parent / f"{path.stem}{suffix}{path.suffix}")


def trim_video(video_path: str, start_time: float, end_time: float, output_path: str = None) -> str:
    """Cuts a video to a specific timeframe."""
    if not _MOVIEPY: return "MoviePy not installed."
    if not os.path.exists(video_path): return f"Video not found: {video_path}"
    output_path = output_path or _get_output_path(video_path, "_trimmed")
    
    try:
        with VideoFileClip(video_path) as clip:
            new_clip = clip.subclipped(start_time, end_time)
            new_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        return f"Video trimmed successfully: {output_path}"
    except Exception as e:
        return f"Trim failed: {e}"


def add_background_music(video_path: str, audio_path: str, output_path: str = None, volume: float = 1.0) -> str:
    """Replaces or adds background music to a video."""
    if not _MOVIEPY: return "MoviePy not installed."
    if not os.path.exists(video_path): return f"Video not found: {video_path}"
    if not os.path.exists(audio_path): return f"Audio not found: {audio_path}"
    output_path = output_path or _get_output_path(video_path, "_with_music")

    try:
        with VideoFileClip(video_path) as video:
            with AudioFileClip(audio_path) as audio:
                if audio.duration > video.duration:
                    audio = audio.subclipped(0, video.duration)
                final_audio = audio.with_volume_scaled(volume)
                final_video = video.with_audio(final_audio)
                final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
        return f"Audio added successfully: {output_path}"
    except Exception as e:
        return f"Failed to add audio: {e}"


def merge_videos(video_paths: List[str], output_path: str) -> str:
    """Stitches multiple video clips together."""
    if not _MOVIEPY: return "MoviePy not installed."
    valid_paths = [p for p in video_paths if os.path.exists(p)]
    if not valid_paths: return "No valid video files provided."

    try:
        clips = [VideoFileClip(p) for p in valid_paths]
        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        for c in clips: c.close()
        return f"Merged {len(valid_paths)} videos into {output_path}"
    except Exception as e:
        return f"Merge failed: {e}"


def _apply_zoom(clip, zoom_ratio=0.04):
    """Internal helper for smooth zoom animation."""
    def effect(get_frame, t):
        frame = get_frame(t)
        h, w = frame.shape[:2]
        # Calculate new size based on time and ratio
        # ratio is per second
        current_zoom = 1 + (zoom_ratio * t)
        new_h = int(h * current_zoom)
        new_w = int(w * current_zoom)
        # Center crop and resize
        resized = cv2.resize(frame, (new_w, new_h))
        top = (new_h - h) // 2
        left = (new_w - w) // 2
        return resized[top:top+h, left:left+w]
    return clip.transform(effect)

def _apply_glow(clip, intensity=1.5):
    """Internal helper for glow effect."""
    def effect(get_frame, t):
        frame = get_frame(t)
        # Ensure intensity is a float
        val = float(intensity)
        blur = cv2.GaussianBlur(frame, (0, 0), 10)
        return cv2.addWeighted(frame, 1.0, blur, val, 0)
    return clip.transform(effect)


def apply_effects(video_path: str, output_path: str = None, 
                 zoom: str = None, zoom_amount: float = 0.04,
                 glow: bool = False, glow_intensity: float = 1.5,
                 fade_in: float = 0, fade_out: float = 0) -> str:
    """Applies animations and visual effects with precise control."""
    if not _MOVIEPY or not _CV2: return "MoviePy or OpenCV not installed."
    if not os.path.exists(video_path): return f"Video not found: {video_path}"
    output_path = output_path or _get_output_path(video_path, "_effects")

    try:
        from moviepy.video.fx import FadeIn, FadeOut
        
        with VideoFileClip(video_path) as clip:
            processed = clip
            
            # 1. Apply Zoom
            if zoom == "in":
                processed = _apply_zoom(processed, abs(float(zoom_amount)))
            elif zoom == "out":
                processed = _apply_zoom(processed, -abs(float(zoom_amount)))
            
            # 2. Apply Glow
            if glow:
                processed = _apply_glow(processed, intensity=float(glow_intensity))
                
            # 3. Apply Fades
            if fade_in > 0:
                processed = processed.with_effects([FadeIn(float(fade_in))])
            if fade_out > 0:
                processed = processed.with_effects([FadeOut(float(fade_out))])
                
            processed.write_videofile(output_path, codec="libx264", audio_codec="aac")
            
        return f"Effects applied successfully: {output_path}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Effects failed: {e}"


def add_text_to_video(video_path: str, text: str, output_path: str = None, 
                     font: str = "Arial", fontsize: int = 50, color: str = "white",
                     position: str = "center", duration: float = None) -> str:
    """Adds text overlay to a video."""
    if not _MOVIEPY: return "MoviePy not installed."
    if not os.path.exists(video_path): return f"Video not found: {video_path}"
    output_path = output_path or _get_output_path(video_path, "_with_text")

    try:
        with VideoFileClip(video_path) as video:
            duration = duration or video.duration
            
            # Create text clip
            txt_clip = TextClip(
                text=text, 
                font=font, 
                font_size=fontsize, 
                color=color,
                method='label' # Uses ImageMagick or built-in depending on config
            ).with_duration(duration).with_position(position)
            
            # Combine
            final_video = CompositeVideoClip([video, txt_clip])
            final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
            
        return f"Text added successfully: {output_path}"
    except Exception as e:
        return f"Failed to add text: {e}. (Ensure ImageMagick is installed for complex text)"


def beat_sync_edit(video_folder: str, audio_path: str, output_path: str, 
                   apply_vfx: bool = True) -> str:
    """Creates a 'hype edit' with beat-synced cuts and optional effects."""
    if not _MOVIEPY or not _LIBROSA: return "MoviePy/Librosa not installed."
    if not os.path.exists(audio_path): return f"Audio not found: {audio_path}"

    try:
        y, sr = librosa.load(audio_path)
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        
        video_exts = ('.mp4', '.mov', '.avi', '.mkv')
        video_files = [str(p) for p in Path(video_folder).glob("*") if p.suffix.lower() in video_exts]
        if not video_files: return "No video clips found."

        final_clips = []
        current_beat_idx = 0
        
        for vid_path in video_files:
            if current_beat_idx >= len(beat_times) - 1: break
            duration = beat_times[current_beat_idx + 1] - beat_times[current_beat_idx]
            
            with VideoFileClip(vid_path) as clip:
                if clip.duration > duration:
                    slice_clip = clip.subclipped(0, duration).without_audio()
                    
                    if apply_vfx:
                        # Alternate zoom in/out on beats
                        z = 0.1 if current_beat_idx % 2 == 0 else -0.1
                        slice_clip = _apply_zoom(slice_clip, z)
                        # Add slight glow to every 4th beat (the 'drop')
                        if current_beat_idx % 4 == 0:
                            slice_clip = _apply_glow(slice_clip)
                    
                    final_clips.append(slice_clip)
                    current_beat_idx += 1

        final_video = concatenate_videoclips(final_clips, method="compose")
        with AudioFileClip(audio_path) as audio:
            if audio.duration > final_video.duration:
                audio = audio.subclipped(0, final_video.duration)
            final_video = final_video.with_audio(audio)
            final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")

        return f"Beat-synced hype edit created: {output_path}"
    except Exception as e:
        return f"Beat sync failed: {e}"


def video_editing(parameters: dict = None, player=None, speak=None) -> str:
    """Main tool entry point for Jarvis."""
    params = parameters or {}
    action = params.get("action", "").lower()
    
    if player: player.write_log(f"[VideoEditor] Action: {action}")

    try:
        if action in ("trim", "cut", "crop"):
            return trim_video(
                video_path = params.get("video_path"),
                start_time = float(params.get("start", 0)),
                end_time   = float(params.get("end", 10)),
                output_path= params.get("output_path")
            )
        
        elif action in ("add_music", "add_audio", "background_music"):
            return add_background_music(
                video_path = params.get("video_path"),
                audio_path = params.get("audio_path"),
                output_path= params.get("output_path"),
                volume     = float(params.get("volume", 1.0))
            )
        
        elif action in ("merge", "stitch", "combine"):
            return merge_videos(
                video_paths = params.get("video_paths", []),
                output_path = params.get("output_path")
            )
        
        elif action in ("animate", "effects", "zoom", "glow", "fade", "fade_in_out"):
            return apply_effects(
                video_path    = params.get("video_path"),
                output_path   = params.get("output_path"),
                zoom          = params.get("zoom"), # "in" or "out"
                zoom_amount   = float(params.get("zoom_amount", 0.04)),
                glow          = bool(params.get("glow") or action == "glow"),
                glow_intensity= float(params.get("glow_intensity", 1.5)),
                fade_in       = float(params.get("fade_in", 2.0 if "fade" in action else 0)),
                fade_out      = float(params.get("fade_out", 2.0 if "fade" in action else 0))
            )

        elif action in ("add_text", "text_overlay", "caption"):
            return add_text_to_video(
                video_path = params.get("video_path"),
                text       = params.get("text"),
                output_path= params.get("output_path"),
                font       = params.get("font", "Arial"),
                fontsize   = int(params.get("fontsize", 50)),
                color      = params.get("color", "white"),
                position   = params.get("position", "center")
            )
        
        elif action == "beat_sync":
            return beat_sync_edit(
                video_folder = params.get("video_folder"),
                audio_path   = params.get("audio_path"),
                output_path  = params.get("output_path"),
                apply_vfx    = bool(params.get("apply_vfx", True))
            )
        
        return f"Unknown video editing action: {action}"
    except Exception as e:
        return f"Video task failed: {e}"
