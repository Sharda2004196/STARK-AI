import os
import time
import requests
import platform
import subprocess
from pathlib import Path
from urllib.parse import quote

class JarvisImageEngine:
    def __init__(self, key_file=None):
        """
        Pure Pollinations.ai (FLUX) Image Engine. 
        Reliable, free, and keyless.
        """
        print(f"[+] IMAGE ENGINE: Pollinations.ai (FLUX) Online.")

    def _get_save_path(self, filename: str) -> Path:
        save_dir = Path.home() / "Desktop" / "JarvisMedia"
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir / filename

    def _map_aspect_ratio(self, ratio: str) -> tuple[int, int]:
        """Maps aspect ratio strings to stable HD pixel dimensions (multiples of 64)."""
        mapping = {
            "1:1":  (1024, 1024),
            "16:9": (1280, 704),  # Closest stable HD to 16:9
            "9:16": (704, 1280),
            "4:3":  (1024, 768),
            "3:4":  (768, 1024)
        }
        return mapping.get(ratio, (1024, 1024))

    def generate(self, prompt: str, aspect_ratio: str = "1:1", return_path: bool = False) -> str | Path:
        """Generates stable HD images using Pollinations.ai (FLUX Free Tier)"""
        timestamp = int(time.time())
        filename = f"jarvis_image_{timestamp}.jpg"
        output_path = self._get_save_path(filename)
        width, height = self._map_aspect_ratio(aspect_ratio)
        
        try:
            # Clean prompt: Simple underscores for maximum stability
            clean_prompt = "_".join(prompt.split())
            encoded_prompt = quote(clean_prompt)
            
            # Using the GUARANTEED free subdomain
            url = (
                f"https://image.pollinations.ai/prompt/{encoded_prompt}?"
                f"width={width}&height={height}&seed={timestamp}&model=flux&nologo=true"
            )
            
            print(f"[JARVIS] 🎨 Sending blueprint to FLUX (Stable HD): '{prompt[:50]}...'")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=60)
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'image' not in content_type:
                    return f"❌ Server busy (Returned text). Sir, the engine might be cooking a large render."

                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                # Automatically open the image
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
                return f"Sir, the image has been rendered in Full HD and opened for you. Saved to Desktop/JarvisMedia/{output_path.name}."
            else:
                return f"❌ Engine error: {response.status_code}."
            
        except Exception as e:
            return f"❌ Critical failure in image pipeline: {str(e)}"
