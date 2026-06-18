import os
import time
import requests
import platform
import subprocess
from pathlib import Path
from urllib.parse import quote
from PIL import Image

_MAX_RETRIES = 4
_RETRY_DELAY = 3

# ── Prompt enrichment prefix for FLUX photorealism ─────────────────────────
# FLUX has an incredibly powerful text encoder. Photography language produces much better results.
_FLUX_QUALITY_PREFIX = (
    "A crisp, detailed candid photograph, shot on 35mm lens, f/2.8, film grain, "
    "natural skin textures, soft realistic ambient lighting, highly detailed, "
)


def _enrich_prompt(raw_prompt: str) -> str:
    """Prepend quality photography language for better FLUX output."""
    return f"{_FLUX_QUALITY_PREFIX}{raw_prompt}"


class JarvisImageEngine:
    def __init__(self, key_file=None):
        """
        Pollinations.ai FLUX image generator. Reliable, free, and keyless.
        """
        print("[+] IMAGE ENGINE: Pollinations.ai (FLUX) Online.")

    def _get_save_path(self, filename: str) -> Path:
        save_dir = Path.home() / "Desktop" / "JarvisMedia"
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir / filename

    def _map_aspect_ratio(self, ratio: str) -> tuple[int, int]:
        """Maps aspect ratio strings to reliable dimensions that Pollinations.ai actually respects."""
        mapping = {
            "1:1":  (1024, 1024),
            "16:9": (1024, 576),
            "9:16": (576, 1024),
            "4:3":  (768, 576),
            "3:4":  (576, 768),
        }
        return mapping.get(ratio, (1024, 1024))

    def generate(self, prompt: str, aspect_ratio: str = "1:1", return_path: bool = False) -> str | Path:
        """Generates HD images using Pollinations.ai FLUX Free Tier."""
        timestamp = int(time.time())
        filename = f"jarvis_image_{timestamp}.jpg"
        output_path = self._get_save_path(filename)
        width, height = self._map_aspect_ratio(aspect_ratio)

        # Enrich prompt with quality photography language for better FLUX results
        enriched = _enrich_prompt(prompt)
        clean_prompt = "_".join(enriched.split())
        encoded_prompt = quote(clean_prompt)

        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}?"
            f"width={width}&height={height}&seed={timestamp}&model=flux&nologo=true"
        )

        print(f"[JARVIS] 🎨 Sending to FLUX: '{prompt[:50]}...'")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = requests.get(url, headers=headers, timeout=120)

                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '').lower()
                    if 'image' not in content_type:
                        return "❌ Server busy. The Pollinations engine might be congested."

                    with open(output_path, "wb") as f:
                        f.write(response.content)

                    # Read actual image dimensions from the returned file
                    try:
                        with Image.open(output_path) as img:
                            actual_w, actual_h = img.size
                    except Exception:
                        actual_w, actual_h = width, height

                    # Auto-open the image
                    try:
                        if platform.system() == "Windows":
                            os.startfile(output_path)
                        elif platform.system() == "Darwin":
                            subprocess.run(["open", str(output_path)])
                        else:
                            subprocess.run(["xdg-open", str(output_path)])
                    except Exception as open_err:
                        print(f"[!] Could not auto-open image: {open_err}")

                    if return_path:
                        return output_path
                    return f"Sir, the image has been rendered at {actual_w}x{actual_h} via FLUX (Pollinations.ai). Saved to Desktop/JarvisMedia/{output_path.name}."
                else:
                    last_exc = RuntimeError(f"HTTP {response.status_code}")
                    if attempt < _MAX_RETRIES - 1:
                        delay = _RETRY_DELAY * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    return f"❌ Pollinations HTTP error: {response.status_code}."

            except Exception as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_DELAY * (2 ** attempt)
                    time.sleep(delay)
                else:
                    break

        return f"❌ Image generation failed: {last_exc}"
