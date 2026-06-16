import os
import re
import sys
import time
from pathlib import Path
from config.genai_client import generate_content

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
BUILDS_DIR = Path.home() / "Desktop" / "JarvisFrontends"

def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\r?\n?", "", text)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()

def frontend_builder(parameters: dict, player=None, speak=None) -> str:
    """
    Builds immersive, beautiful, and modern frontend UIs.
    Parameters:
        goal: description of the UI to build
        theme: "dark", "light", "glassmorphism", "neo-brutalism", etc. (optional)
        stack: "vanilla", "tailwind", "react-cdn" (optional, default: vanilla)
        count: number of variations to generate (optional, max: 5, default: 1)
        image_path: path to a reference image for inspiration (optional)
    """
    goal = parameters.get("goal", "")
    theme = parameters.get("theme", "modern")
    stack = parameters.get("stack", "vanilla")
    count = min(int(parameters.get("count", 1)), 5) # Safety cap
    image_path = parameters.get("image_path")
    
    if not goal:
        return "Please provide a goal for the frontend builder, sir."

    image_context = ""
    image_base64 = ""
    if image_path and os.path.exists(image_path):
        if player:
            player.write_log("Analyzing design reference...")
        
        try:
            import base64
            from PIL import Image
            
            # Prepare Base64 for injection later
            with open(image_path, "rb") as img_file:
                ext = os.path.splitext(image_path)[1].lower().replace(".", "")
                if ext == "jpg": ext = "jpeg"
                img_data = base64.b64encode(img_file.read()).decode("utf-8")
                image_base64 = f"data:image/{ext};base64,{img_data}"

            # Analyze image with Gemini Vision
            analysis_prompt = """Analyze this UI design reference image. 
Describe:
1. Color Palette (hex codes if possible)
2. Layout Structure (navigation, hero section, grid, etc.)
3. Typography Style (serif, sans-serif, bold, etc.)
4. Key UI Elements (buttons, cards, glassmorphism effects, etc.)
5. Overall Aesthetic (minimalist, futuristic, corporate, etc.)
Provide a concise summary to be used as a design prompt."""
            
            vision_response = generate_content(
                model="gemini-3.1-flash-lite", # Standardizing on 3.1 for all tasks
                contents=[analysis_prompt, Image.open(image_path)]
            )
            image_context = f"\n\nDESIGN REFERENCE FROM IMAGE:\n{vision_response}\n\nCRITICAL: The user has provided a specific image. If the goal implies using this image (e.g., as a background or hero image), use the EXACT string 'LOCAL_IMAGE_ASSET' as the source (url or src). Do NOT use placeholder URLs for the primary image."
            print(f"[FrontendBuilder] 🖼️ Image Analysis: {vision_response[:100]}...")
        except Exception as e:
            print(f"[FrontendBuilder] ⚠️ Image analysis failed: {e}")

    if player:
        variation_text = f"{count} variations" if count > 1 else f"a {theme} interface"
        inspiration_text = " inspired by your image" if image_path else ""
        player.write_log(f"Building {variation_text}{inspiration_text}...")

    # Specialized UI/UX System Prompt
    system_instruction = f"""You are a World-Class UI/UX Designer and Frontend Architect.
Your goal is to create "immersive, beautiful, polished, and fully functional" web applications.{image_context}

DESIGN PRINCIPLES:
- Visual Impact: Use stunning gradients, crisp typography, and generous whitespace.
- Modern Styles: Favor {theme} aesthetics unless the image reference dictates otherwise.
- Advanced Motion: Use GSAP for high-end scroll-triggers and entrance animations.
- 3D & Immersive: Use Three.js for interactive backgrounds or objects.

INTERACTIVITY & FUNCTIONALITY (CRITICAL):
- DO NOT create "dead" buttons. Every button must be functional using a SPA approach.
- Implement internal "routing" to swap views or reveal content sections.

TECHNICAL RULES:
- Output a SINGLE, complete, and self-contained HTML file.
- All CSS must be in <style>. All JS must be in <script>.
- Use Tailwind CSS v4, GSAP, and Three.js via CDN as needed.
- Return ONLY the raw HTML code. No explanation, no markdown fences.

PROJECT GOAL: {goal}
STACK: {stack}
THEME: {theme}
"""

    results = []
    try:
        for i in range(count):
            response = generate_content(
                model="gemini-3.1-flash-lite", 
                contents=f"Create a unique variation for: {goal}. Ensure this variation is distinct from previous ones.",
                config={"system_instruction": system_instruction}
            )
            
            code = _strip_fences(response)
            
            # Inject real image if placeholder was used
            if image_base64 and "LOCAL_IMAGE_ASSET" in code:
                code = code.replace("LOCAL_IMAGE_ASSET", image_base64)
            
            # Save to Desktop
            BUILDS_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^\w\-]", "_", goal[:30]).lower() or "ui_build"
            file_path = BUILDS_DIR / f"{safe_name}_{int(time.time())}_{i+1}.html"
            
            file_path.write_text(code, encoding="utf-8")
            
            # Auto-open in browser if possible
            try:
                import webbrowser
                webbrowser.open(f"file:///{file_path.absolute()}")
            except Exception:
                pass
            
            results.append(str(file_path))

        if count > 1:
            msg = f"I've generated {count} distinct variations for you, sir. They are all open in your browser. Saved to: {BUILDS_DIR}"
        else:
            msg = f"Front-end build complete, sir. I've designed a {theme} interface and opened it in your browser. Saved to: {results[0]}"
        
        return msg

    except Exception as e:
        error_msg = f"Frontend builder failed: {e}"
        print(f"[FrontendBuilder] {error_msg}")
        return error_msg
